from __future__ import annotations

import json
import re
import uuid
from datetime import datetime
from difflib import SequenceMatcher

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.openedx_ids import normalize_openedx_course_id, openedx_course_id_candidates
from app.models.course import CourseSyncState
from app.models.question import Question
from app.models.question_bank import (
    BankReleaseQuestion,
    CourseQuizInstance,
    Department,
    EdxCourseChapterMapping,
    EdxCourseMapping,
    QuestionBankRelease,
    QuizBlueprint,
    Subject,
    SubjectChapter,
    SubjectOffering,
)
from app.modules.openedx_connector.factory import get_openedx_connector
from app.services.openedx_exporter import _build_problem_display_name, is_manually_authored_question
from app.services.bank_operation_jobs import bank_operation_error_code, bank_operation_user_message
from app.services.question_family import normalize_difficulty
from app.services.question_bank.helpers import (
    _ui_notice,
    extract_chapter_number,
    normalize_code,
    normalize_title_match,
    parse_openedx_course_id,
)


def _difficulty_summary(counts: dict[str, int]) -> str:
    labels = (('easy', 'Dễ'), ('medium', 'Trung bình'), ('hard', 'Khó'))
    return ', '.join(f'{label}: {int(counts.get(key, 0) or 0)}' for key, label in labels)


class QuestionBankQuizCreationWorkflowService:
    """Course quiz auto-map and native Problem Bank creation workflow.

    Split from VersionedQuestionBankService to isolate the Open edX course
    mapping/quiz creation flow. Public parent-service methods still delegate here
    so route/API behavior stays compatible while the large service is reduced one
    workflow at a time. Low-level helpers that are still owned by the parent
    are delegated through __getattr__.
    """

    def __init__(self, service):
        self._service = service

    @property
    def db(self) -> Session:
        return self._service.db

    def __getattr__(self, name):
        return getattr(self._service, name)

    def _latest_published_release_for_chapter(self, chapter_id: str) -> QuestionBankRelease | None:
        return self.db.query(QuestionBankRelease).filter(
            QuestionBankRelease.chapter_id == chapter_id,
            QuestionBankRelease.status == 'published',
            QuestionBankRelease.openedx_library_key.isnot(None),
        ).order_by(QuestionBankRelease.published_at.desc().nullslast(), QuestionBankRelease.created_at.desc()).first()

    def _release_component_ready(self, release: QuestionBankRelease | None) -> tuple[bool, int, int]:
        if not release:
            return False, 0, 0
        rows = self.db.query(BankReleaseQuestion).filter(BankReleaseQuestion.bank_release_id == release.id).all()
        total = len(rows)
        ready = len([row for row in rows if str(row.openedx_library_problem_id or '').strip()])
        verification_complete = bool((release.metadata_json or {}).get('verification_complete'))
        return bool(total and ready == total and verification_complete), total, ready

    def _offering_published_release_status(self, offering: SubjectOffering) -> dict:
        chapters = self.db.query(SubjectChapter).filter(
            SubjectChapter.subject_offering_id == offering.id,
            SubjectChapter.status == 'active',
        ).order_by(SubjectChapter.sort_order.asc(), SubjectChapter.chapter_no.asc()).all()
        details: list[dict] = []
        missing: list[str] = []
        ready_count = 0
        for chapter in chapters:
            release = self._latest_published_release_for_chapter(chapter.id)
            component_ready, component_total, component_ready_count = self._release_component_ready(release)
            ready = bool(release and component_ready)
            if ready:
                ready_count += 1
            else:
                missing.append(self._chapter_display_name(chapter))
            details.append({
                'chapter_id': chapter.id,
                'chapter_title': self._chapter_display_name(chapter),
                'release_id': release.id if release else None,
                'release_code': release.release_code if release else None,
                'openedx_library_key': release.openedx_library_key if release else None,
                'question_count': component_total,
                'component_ready_count': component_ready_count,
                'ready': ready,
            })
        all_ready = bool(chapters) and ready_count == len(chapters)
        return {
            'all_ready': all_ready,
            'chapter_count': len(chapters),
            'ready_chapter_count': ready_count,
            'missing_chapters': missing,
            'details': details,
        }

    @staticmethod
    def _quiz_action_for_chapter_title(title: str | None) -> str:
        text = normalize_title_match(title)
        if re.search(r'\bassignment\b|\basm\b|bai tap|do an|nop bai', text):
            return 'assignment'
        if re.search(r'\bfinal\b|final test|thi cuoi|cuoi ky|thi ket thuc|thi cuoi mon', text):
            return 'final_test'
        return 'quiz'

    @staticmethod
    def _normalize_quiz_chapter_plan(chapter_plan: list[dict] | None) -> dict[str, str]:
        allowed = {'quiz', 'skip', 'assignment', 'final_test'}
        plan: dict[str, str] = {}
        for item in chapter_plan or []:
            chapter_id = str((item or {}).get('chapter_id') or '').strip()
            action = str((item or {}).get('action') or 'quiz').strip().lower()
            if chapter_id and action in allowed:
                plan[chapter_id] = action
        return plan

    @staticmethod
    def _quiz_action_requires_release(action: str | None) -> bool:
        return str(action or '').lower() in {'quiz', 'final_test'}

    def _final_test_release_info_for_plan(
        self,
        *,
        chapters: list[SubjectChapter],
        chapter_actions: dict[str, str],
        release_by_chapter: dict[str, dict],
    ) -> dict:
        """Resolve Final test input from every chapter currently configured as Quiz.

        Final test is not backed by a dedicated Bank Release. Its question pool is
        the union of the published, verified Releases of the normal Quiz chapters.
        One source Release is kept as an API/mapping anchor for backward-compatible
        routes; source_release_ids is the authoritative aggregate membership.
        """
        sources: list[dict] = []
        missing: list[str] = []
        for chapter in chapters:
            if str(chapter_actions.get(chapter.id) or '').lower() != 'quiz':
                continue
            info = release_by_chapter.get(chapter.id) or {}
            title = self._chapter_display_name(chapter)
            if not info.get('ready'):
                missing.append(title)
                continue
            sources.append({
                'chapter_id': chapter.id,
                'chapter_title': title,
                'release_id': info.get('release_id'),
                'release_code': info.get('release_code'),
                'openedx_library_key': info.get('openedx_library_key'),
                'question_count': int(info.get('question_count') or 0),
                'component_ready_count': int(info.get('component_ready_count') or 0),
            })
        anchor = sources[0] if sources else {}
        ready = bool(sources) and not missing
        return {
            'aggregate': True,
            'ready': ready,
            'release_id': anchor.get('release_id'),
            'release_code': anchor.get('release_code'),
            'openedx_library_key': anchor.get('openedx_library_key'),
            'question_count': sum(int(item.get('question_count') or 0) for item in sources),
            'component_ready_count': sum(int(item.get('component_ready_count') or 0) for item in sources),
            'source_release_ids': [str(item['release_id']) for item in sources if item.get('release_id')],
            'source_release_codes': [str(item['release_code']) for item in sources if item.get('release_code')],
            'source_chapter_ids': [str(item['chapter_id']) for item in sources],
            'source_chapter_titles': [str(item['chapter_title']) for item in sources],
            'missing_chapters': missing,
            'source_release_count': len(sources),
        }

    @staticmethod
    def _quiz_action_label(action: str | None) -> str:
        labels = {
            'quiz': 'Tạo Quiz',
            'final_test': 'Tạo Final test',
            'assignment': 'Không tạo',
            'skip': 'Không tạo',
        }
        return labels.get(str(action or '').lower(), 'Tạo Quiz')

    @staticmethod
    def _quiz_production_status_for_mapping(
        *,
        action: str | None,
        section: dict | None,
        release_info: dict | None,
    ) -> dict:
        normalized_action = str(action or '').lower()
        requires_release = QuestionBankQuizCreationWorkflowService._quiz_action_requires_release(normalized_action)
        missing: list[str] = []
        if requires_release and not section:
            missing.append('SECTION')
        if requires_release and not (release_info or {}).get('ready'):
            missing.append('RELEASE')
        if not requires_release:
            return {
                'status_code': 'SKIPPED_NO_CREATE',
                'status_label': 'Không tạo',
                'severity': 'info',
                'missing_requirements': [],
                'production_ready': True,
                'can_save_configuration': True,
                'recommended_action': 'Không tạo bài kiểm tra cho dòng này.',
            }
        if not missing:
            return {
                'status_code': 'READY_TO_CREATE',
                'status_label': 'Sẵn sàng tạo',
                'severity': 'success',
                'missing_requirements': [],
                'production_ready': True,
                'can_save_configuration': True,
                'recommended_action': 'Có thể lưu cấu hình và tạo bài kiểm tra.',
            }
        if missing == ['SECTION']:
            message = 'Thiếu Section Course CMS/Open edX cùng tên.'
        elif missing == ['RELEASE']:
            message = 'Thiếu Release đã đưa lên CMS/Open edX Library.'
        else:
            message = 'Thiếu Section và Release.'
        return {
            'status_code': 'MISSING_' + '_AND_'.join(missing),
            'status_label': message,
            'severity': 'danger',
            'missing_requirements': missing,
            'production_ready': False,
            'can_save_configuration': False,
            'recommended_action': 'Đổi dòng sang Không tạo nếu không cần bài kiểm tra, hoặc xử lý Section/Release trước khi lưu cấu hình.',
        }

    @staticmethod
    def _course_tree_error_summary(exc: Exception) -> tuple[str, str]:
        text = str(exc or '').strip()
        status_match = re.search(r'HTTP\s+(\d{3})', text, flags=re.IGNORECASE)
        code = f'OPENEDX_COURSE_TREE_HTTP_{status_match.group(1)}' if status_match else 'OPENEDX_COURSE_TREE_UNAVAILABLE'
        if status_match:
            message = f'Open edX trả HTTP {status_match.group(1)} khi đọc cây course.'
        else:
            message = 'Không kết nối được dịch vụ đọc cây course của Open edX.'
        return code, message

    async def _load_openedx_sections_for_quiz_detailed(self, course_id: str) -> tuple[list[dict], list[str], dict]:
        canonical_course_id = normalize_openedx_course_id(course_id, required=True)
        warnings: list[str] = []
        blocks: list[dict] = []
        diagnostics = {
            'source': 'direct',
            'course_id': canonical_course_id,
            'error_code': None,
            'direct_error': None,
            'cached_block_count': 0,
        }
        try:
            blocks = await get_openedx_connector().get_course_blocks(canonical_course_id)
        except Exception as exc:
            error_code, safe_message = self._course_tree_error_summary(exc)
            diagnostics.update({'source': 'unavailable', 'error_code': error_code, 'direct_error': safe_message})
            warnings.append(f'{safe_message} Hệ thống đã kiểm tra dữ liệu course sync gần nhất trong AI Server. [{error_code}]')
        if not blocks:
            candidates = openedx_course_id_candidates(canonical_course_id)
            rows = self.db.query(CourseSyncState).filter(CourseSyncState.course_id.in_(candidates)).all() if candidates else []
            diagnostics['cached_block_count'] = len(rows)
            if rows:
                diagnostics['source'] = 'cached'
                blocks = [
                    {
                        'block_id': row.block_id,
                        'type': row.block_type,
                        'display_name': row.display_name,
                        'parent_block_id': row.parent_block_id,
                        'children': row.children or [],
                    }
                    for row in rows
                ]
                warnings.append('Đang dùng cây course đã sync trong AI Server vì không đọc được dữ liệu trực tiếp từ Open edX.')
        sections = [block for block in blocks if str(block.get('type') or '').lower() == 'chapter']
        if not sections:
            sections = [block for block in blocks if str(block.get('type') or '').lower() == 'sequential']
            if sections:
                warnings.append('Course chưa trả về Section/chapter rõ ràng; hệ thống tạm dùng Subsection để map. Nên sync lại course nếu tên chưa đúng.')
        if not blocks:
            diagnostics['source'] = 'unavailable'
        return sections, warnings, diagnostics

    async def _load_openedx_sections_for_quiz(self, course_id: str) -> tuple[list[dict], list[str]]:
        sections, warnings, _diagnostics = await self._load_openedx_sections_for_quiz_detailed(course_id)
        return sections, warnings

    def _match_chapter_to_section(self, chapter: SubjectChapter, sections: list[dict], used_section_ids: set[str]) -> tuple[dict | None, float, str]:
        bank_title = self._chapter_display_name(chapter)
        bank_key = normalize_title_match(bank_title)
        bank_no = extract_chapter_number(bank_title)
        best: tuple[dict | None, float, str] = (None, 0.0, 'no_match')
        for section in sections:
            section_id = str(section.get('block_id') or '')
            if section_id in used_section_ids:
                continue
            section_title = str(section.get('display_name') or '')
            section_key = normalize_title_match(section_title)
            section_no = extract_chapter_number(section_title)
            score = SequenceMatcher(None, bank_key, section_key).ratio() if bank_key and section_key else 0.0
            reason = f'Tên giống {score:.0%}'
            if bank_key and section_key and bank_key == section_key:
                score = 1.0
                reason = 'Trùng tên Section/Bài'
            elif bank_no and section_no and bank_no == section_no:
                score = max(score, 0.86)
                reason = f'Trùng số bài {bank_no}'
            if score > best[1]:
                best = (section, score, reason)
        if best[1] < 0.45:
            return None, best[1], 'Không tìm thấy Section cùng tên hoặc cùng số bài'
        return best

    def _format_offering_candidate(self, item: dict) -> dict:
        missing = item.get('missing_chapters') or []
        return {
            'offering_id': item.get('offering_id'),
            'offering_code': item.get('offering_code'),
            'name': item.get('name'),
            'term': item.get('term'),
            'version_code': item.get('version_code'),
            'status': item.get('status'),
            'score': item.get('score', 0),
            'course_run_match': bool(item.get('course_run_match')),
            'all_ready': bool(item.get('all_ready')),
            'chapter_count': item.get('chapter_count', 0),
            'ready_chapter_count': item.get('ready_chapter_count', 0),
            'missing_chapters': missing,
            'disabled_reason': None,
            'selection_note': 'Có thể chọn; chỉ những bài đánh dấu tạo Quiz/Final test mới cần Release published.',
        }

    def _select_offering_for_course(
        self,
        *,
        course_id: str,
        subject: Subject,
        selected_subject_offering_id: str | None = None,
    ) -> tuple[SubjectOffering | None, list[dict], list[str]]:
        parsed = parse_openedx_course_id(course_id)
        run = parsed.get('run') if parsed.get('ok') else None
        offerings = self.db.query(SubjectOffering).filter(
            SubjectOffering.subject_id == subject.id,
            SubjectOffering.status.in_(['active', 'draft', 'published', 'approved']),
        ).order_by(SubjectOffering.created_at.desc()).all()
        candidates: list[dict] = []
        warnings: list[str] = []
        for offering in offerings:
            release_status = self._offering_published_release_status(offering)
            code_match = bool(run and normalize_code(offering.code) == normalize_code(f'{subject.code}_{run}'))
            term_match = bool(run and normalize_code(offering.term) == normalize_code(run))
            contains_run = bool(run and normalize_code(run) in normalize_code(offering.code))
            score = (100 if code_match else 0) + (40 if term_match else 0) + (20 if contains_run else 0) + (10 * release_status['ready_chapter_count'])
            candidates.append({
                'offering': offering,
                'offering_id': offering.id,
                'offering_code': offering.code,
                'name': offering.name,
                'term': offering.term,
                'version_code': offering.version_code,
                'status': offering.status,
                'score': score,
                'course_run_match': code_match or term_match or contains_run,
                **release_status,
            })
        candidates.sort(key=lambda item: (item['course_run_match'], item['score'], item['ready_chapter_count']), reverse=True)
        selected = None
        explicit_selection = bool(selected_subject_offering_id)
        if selected_subject_offering_id:
            selected_item = next((item for item in candidates if item.get('offering_id') == selected_subject_offering_id), None)
            if not selected_item:
                warnings.append('Version môn được chọn không thuộc môn trong Course ID.')
            else:
                if not selected_item.get('all_ready'):
                    warnings.append('Version môn được chọn chưa publish đủ tất cả bài. Hệ thống vẫn cho chọn; các bài không tạo Quiz/Final test sẽ không chặn luồng.')
                selected = selected_item['offering']
        if not selected and not explicit_selection and candidates:
            selected = candidates[0]['offering']
            if not candidates[0].get('all_ready'):
                warnings.append('Version môn được tự chọn chưa publish đủ tất cả bài. Hệ thống sẽ chỉ yêu cầu Release cho các bài được đánh dấu tạo Quiz/Final test.')
        if not selected and candidates:
            warnings.append('Không chọn được version môn phù hợp.')
        return selected, candidates, warnings

    async def preview_quiz_auto_map(self, *, openedx_course_id: str, selected_subject_offering_id: str | None = None, chapter_plan: list[dict] | None = None) -> dict:
        parsed = parse_openedx_course_id(openedx_course_id)
        course_id = str(parsed.get('normalized_course_id') or (openedx_course_id or '').strip())
        blocking_errors: list[str] = []
        warnings: list[str] = []
        plan_by_chapter = self._normalize_quiz_chapter_plan(chapter_plan)
        if not parsed.get('ok'):
            return {'ok': False, 'openedx_course_id': course_id, 'mode': 'preview', 'subject': None, 'offering': None, 'course_mapping': None, 'summary': {}, 'sections': [], 'mappings': [], 'warnings': [], 'blocking_errors': ['Course ID phải có dạng course-v1:ORG+COURSE+RUN.'], 'can_apply': False, 'message': 'Course ID không hợp lệ.', **_ui_notice('error', 'Course ID không hợp lệ.')}
        subject = self.db.query(Subject).filter(func.lower(Subject.code) == str(parsed.get('course_code')).lower()).first()
        if not subject:
            # Case-insensitive + punctuation-insensitive fallback.
            all_subjects = self.db.query(Subject).all()
            subject = next((item for item in all_subjects if normalize_code(item.code) == normalize_code(parsed.get('course_code'))), None)
        if not subject:
            return {'ok': False, 'openedx_course_id': course_id, 'mode': 'preview', 'subject': None, 'offering': None, 'course_mapping': None, 'summary': {'course_code': parsed.get('course_code'), 'course_run': parsed.get('run')}, 'sections': [], 'mappings': [], 'warnings': [], 'blocking_errors': [f'Không tìm thấy môn có mã {parsed.get("course_code")}.'], 'can_apply': False, 'message': 'Không tìm thấy môn phù hợp với Course ID.', **_ui_notice('error', 'Không tìm thấy môn phù hợp với Course ID.')}
        department = self.db.get(Department, subject.department_id) if subject.department_id else None
        offering, candidates, candidate_warnings = self._select_offering_for_course(course_id=course_id, subject=subject, selected_subject_offering_id=selected_subject_offering_id)
        warnings.extend(candidate_warnings)
        if not offering:
            blocking_errors.append('Chưa có phiên bản môn phù hợp với Course ID. Hãy chọn version môn thủ công nếu hệ thống gợi ý chưa đúng.')
            return {
                'ok': False,
                'openedx_course_id': course_id,
                'mode': 'preview',
                'subject': {'id': subject.id, 'code': subject.code, 'name': subject.name, 'department_id': subject.department_id, 'department_name': department.name if department else None},
                'offering': None,
                'course_mapping': None,
                'summary': {'course_code': parsed.get('course_code'), 'course_run': parsed.get('run'), 'candidates': [self._format_offering_candidate(item) for item in candidates]},
                'sections': [],
                'mappings': [],
                'warnings': warnings,
                'blocking_errors': blocking_errors,
                'can_apply': False,
                'message': 'Chưa chọn được version môn để map course.',
                **_ui_notice('warning', 'Chưa chọn được version môn để map course.'),
            }
        release_status = self._offering_published_release_status(offering)
        sections, section_warnings, course_tree = await self._load_openedx_sections_for_quiz_detailed(course_id)
        warnings.extend(section_warnings)
        tree_unavailable = course_tree.get('source') == 'unavailable'
        if tree_unavailable:
            blocking_errors.append('Không đọc được cây Course CMS/Open edX và chưa có dữ liệu sync cũ. Hãy đồng bộ course hoặc kiểm tra connector trước khi lưu cấu hình.')
        elif not sections:
            blocking_errors.append('Course chưa có Section/Chapter có thể map. Hãy kiểm tra cấu trúc Course CMS/Open edX.')
        course_id_candidates = openedx_course_id_candidates(course_id)
        existing = self.db.query(EdxCourseMapping).filter(
            EdxCourseMapping.openedx_course_id.in_(course_id_candidates)
        ).order_by(EdxCourseMapping.openedx_course_id.asc()).first() if course_id_candidates else None
        saved_sections: dict[str, str] = {}
        if existing:
            saved_sections = {
                str(item.subject_chapter_id): str(item.openedx_parent_node_id or '')
                for item in self.db.query(EdxCourseChapterMapping).filter(
                    EdxCourseChapterMapping.course_mapping_id == existing.id
                ).all()
                if item.openedx_parent_node_id
            }
        section_by_id = {str(item.get('block_id') or ''): item for item in sections}
        used_sections: set[str] = set()
        mappings: list[dict] = []
        release_by_chapter = {item['chapter_id']: item for item in release_status['details']}
        chapters = self.db.query(SubjectChapter).filter(
            SubjectChapter.subject_offering_id == offering.id,
            SubjectChapter.status == 'active',
        ).order_by(SubjectChapter.sort_order.asc(), SubjectChapter.chapter_no.asc()).all()
        chapter_actions = {
            chapter.id: plan_by_chapter.get(chapter.id) or self._quiz_action_for_chapter_title(self._chapter_display_name(chapter))
            for chapter in chapters
        }
        final_release_info = self._final_test_release_info_for_plan(
            chapters=chapters,
            chapter_actions=chapter_actions,
            release_by_chapter=release_by_chapter,
        )
        for chapter in chapters:
            chapter_title = self._chapter_display_name(chapter)
            action = chapter_actions[chapter.id]
            requires_release = self._quiz_action_requires_release(action)
            saved_section_id = saved_sections.get(chapter.id)
            section = section_by_id.get(saved_section_id or '') if saved_section_id not in used_sections else None
            if section:
                score, reason = 1.0, 'Dùng mapping Course CMS đã lưu'
            else:
                section, score, reason = self._match_chapter_to_section(chapter, sections, used_sections)
            if section:
                used_sections.add(str(section.get('block_id') or ''))
            release_info = final_release_info if action == 'final_test' else (release_by_chapter.get(chapter.id) or {})
            ready = bool(requires_release and section and release_info.get('ready'))
            production_status = self._quiz_production_status_for_mapping(action=action, section=section, release_info=release_info)
            if tree_unavailable and requires_release:
                missing_requirements = ['COURSE_TREE']
                if not release_info.get('ready'):
                    missing_requirements.append('RELEASE')
                production_status = {
                    'status_code': 'COURSE_TREE_UNAVAILABLE',
                    'status_label': 'Chưa đọc được cây Course CMS',
                    'severity': 'danger',
                    'missing_requirements': missing_requirements,
                    'production_ready': False,
                    'can_save_configuration': False,
                    'recommended_action': 'Đồng bộ lại course hoặc kiểm tra Open edX connector trước khi lưu cấu hình.',
                }
            if requires_release and not section and not tree_unavailable:
                blocking_errors.append(f'{chapter_title} đang chọn {self._quiz_action_label(action)} nhưng chưa tìm thấy Section cùng tên trong course.')
            if requires_release and not release_info.get('ready'):
                if action == 'final_test':
                    missing_source_chapters = list(release_info.get('missing_chapters') or [])
                    if missing_source_chapters:
                        blocking_errors.append(
                            f'{chapter_title} cần Release published của tất cả Bài đang chọn Tạo Quiz. '
                            f'Thiếu: {", ".join(missing_source_chapters)}.'
                        )
                    else:
                        blocking_errors.append(
                            f'{chapter_title} chưa có Bài nào chọn Tạo Quiz với Release published để làm nguồn.'
                        )
                else:
                    blocking_errors.append(f'{chapter_title} đang chọn {self._quiz_action_label(action)} nhưng chưa có Release published đủ component.')
            if not requires_release and not section and not tree_unavailable:
                warnings.append(f'{chapter_title} đang để Không tạo; chưa tìm thấy Section cùng tên nên chỉ lưu course/version, không lưu mapping tạo bài kiểm tra.')
            mappings.append({
                'chapter_id': chapter.id,
                'chapter_title': chapter_title,
                'release_id': release_info.get('release_id'),
                'release_code': release_info.get('release_code'),
                'openedx_library_key': release_info.get('openedx_library_key'),
                'openedx_section_id': section.get('block_id') if section else None,
                'openedx_section_title': section.get('display_name') if section else None,
                'match_score': round(float(score or 0), 4),
                'match_reason': reason,
                'action': action,
                'action_label': self._quiz_action_label(action),
                'assessment_type': 'final_test' if action == 'final_test' else 'quiz' if action == 'quiz' else 'skip',
                'requires_quiz': requires_release,
                'requires_release': requires_release,
                'requires_section': requires_release,
                'skipped': not requires_release,
                'ready': ready,
                'can_create': ready,
                'production_ready': bool(production_status.get('production_ready')),
                'status_code': production_status.get('status_code'),
                'status_label': production_status.get('status_label'),
                'status_severity': production_status.get('severity'),
                'missing_requirements': production_status.get('missing_requirements') or [],
                'recommended_action': production_status.get('recommended_action'),
                'source_release_ids': list(release_info.get('source_release_ids') or []),
                'source_release_codes': list(release_info.get('source_release_codes') or []),
                'source_chapter_ids': list(release_info.get('source_chapter_ids') or []),
                'source_chapter_titles': list(release_info.get('source_chapter_titles') or []),
                'course_chapter_mapping_id': None,
                'recommended_quiz_title': 'Final test' if action == 'final_test' else f'Quiz {self._chapter_quiz_suffix(chapter)}'.strip(),
                'recommended_unit_title': 'Final test' if action == 'final_test' else 'Quiz',
            })
        if existing and existing.subject_id != subject.id:
            blocking_errors.append('Course này đã được map sang môn khác. Không tự ghi đè để tránh gắn nhầm đề.')
        selected_quiz_count = len([item for item in mappings if item.get('requires_quiz')])
        final_test_count = len([item for item in mappings if item.get('action') == 'final_test'])
        regular_quiz_count = len([item for item in mappings if item.get('action') == 'quiz'])
        ready_quiz_count = len([item for item in mappings if item.get('can_create')])
        skipped_chapter_count = len([item for item in mappings if item.get('skipped')])
        missing_section_count = len([item for item in mappings if 'SECTION' in (item.get('missing_requirements') or [])])
        missing_release_count = len([item for item in mappings if 'RELEASE' in (item.get('missing_requirements') or [])])
        can_apply = not blocking_errors and bool(chapters)
        production_gate = {
            'status': 'ready' if can_apply else 'blocked',
            'can_apply': can_apply,
            'can_create_all_selected': bool(selected_quiz_count and ready_quiz_count == selected_quiz_count),
            'selected_quiz_count': selected_quiz_count,
            'regular_quiz_count': regular_quiz_count,
            'final_test_count': final_test_count,
            'ready_quiz_count': ready_quiz_count,
            'skipped_chapter_count': skipped_chapter_count,
            'missing_section_count': missing_section_count,
            'missing_release_count': missing_release_count,
            'blocking_count': len(dict.fromkeys(blocking_errors)),
            'warning_count': len(dict.fromkeys(warnings)),
            'next_action': 'Lưu cấu hình rồi tạo bài kiểm tra.' if can_apply else 'Sửa dòng bị chặn hoặc đổi sang Không tạo trước khi lưu.',
        }
        ui_message = f'Đã tự tìm được version môn. Có thể lưu cấu hình: {ready_quiz_count}/{selected_quiz_count} bài kiểm tra sẵn sàng, {skipped_chapter_count} bài Không tạo.' if can_apply else 'Chưa thể lưu cấu hình. Hãy xử lý các lỗi bên dưới hoặc đổi trạng thái dòng sang Không tạo.'
        if tree_unavailable:
            ui_message = 'Chưa thể lưu cấu hình vì không đọc được cây Course CMS/Open edX và chưa có dữ liệu sync cũ.'
        if can_apply and selected_quiz_count == 0:
            ui_message = 'Đã tự tìm được version môn. Tất cả dòng đang Không tạo; có thể lưu course/version mà không tạo bài kiểm tra.'
        ui_status = 'success' if can_apply else 'warning'
        return {
            'ok': can_apply,
            'openedx_course_id': course_id,
            'mode': 'preview',
            'subject': {'id': subject.id, 'code': subject.code, 'name': subject.name, 'department_id': subject.department_id, 'department_name': department.name if department else None},
            'offering': {'id': offering.id, 'code': offering.code, 'name': offering.name, 'term': offering.term, 'version_code': offering.version_code},
            'course_mapping': {'id': existing.id, 'openedx_course_id': existing.openedx_course_id, 'status': existing.status} if existing else None,
            'summary': {
                'course_code': parsed.get('course_code'),
                'course_run': parsed.get('run'),
                'chapter_count': len(chapters),
                'published_release_count': release_status['ready_chapter_count'],
                'selected_quiz_count': selected_quiz_count,
                'regular_quiz_count': regular_quiz_count,
                'final_test_count': final_test_count,
                'ready_quiz_count': ready_quiz_count,
                'skipped_chapter_count': skipped_chapter_count,
                'missing_section_count': missing_section_count,
                'missing_release_count': missing_release_count,
                'production_gate': production_gate,
                'section_count': len(sections),
                'matched_count': len([item for item in mappings if item.get('openedx_section_id')]),
                'candidates': [self._format_offering_candidate(item) for item in candidates],
                'selected_subject_offering_id': offering.id if offering else None,
                'course_tree': course_tree,
            },
            'course_tree': course_tree,
            'sections': [{'openedx_section_id': str(item.get('block_id') or ''), 'title': str(item.get('display_name') or ''), 'type': str(item.get('type') or '')} for item in sections],
            'mappings': mappings,
            'warnings': list(dict.fromkeys(warnings)),
            'blocking_errors': list(dict.fromkeys(blocking_errors)),
            'can_apply': can_apply,
            'message': ui_message,
            **_ui_notice(ui_status, ui_message),
        }

    async def apply_quiz_auto_map(self, *, openedx_course_id: str, selected_subject_offering_id: str | None = None, chapter_plan: list[dict] | None = None, actor: str | None = None) -> dict:
        preview = await self.preview_quiz_auto_map(openedx_course_id=openedx_course_id, selected_subject_offering_id=selected_subject_offering_id, chapter_plan=chapter_plan)
        if not preview.get('can_apply'):
            raise ValueError(preview.get('message') or 'Chưa đủ điều kiện tự map course.')
        subject = preview.get('subject') or {}
        offering = preview.get('offering') or {}
        course_id = preview['openedx_course_id']
        parsed = parse_openedx_course_id(course_id)
        mapping_candidates = openedx_course_id_candidates(course_id)
        mapping = self.db.query(EdxCourseMapping).filter(
            EdxCourseMapping.openedx_course_id.in_(mapping_candidates)
        ).first() if mapping_candidates else None
        if mapping:
            if mapping.openedx_course_id != course_id:
                canonical_conflict = self.db.query(EdxCourseMapping).filter(
                    EdxCourseMapping.openedx_course_id == course_id,
                    EdxCourseMapping.id != mapping.id,
                ).first()
                if canonical_conflict:
                    raise ValueError('Course có nhiều mapping legacy. Hãy xử lý mapping trùng trước khi lưu.')
                mapping.openedx_course_id = course_id
            if mapping.subject_id != subject.get('id'):
                raise ValueError('Course này đã map sang môn khác. Không ghi đè mapping cũ.')
            mapping.subject_offering_id = offering.get('id')
            mapping.department_id = subject.get('department_id')
            mapping.term = offering.get('term') or parsed.get('run')
            mapping.validation_status = 'low'
            mapping.validation_json = {'auto_mapped': True, 'source': 'quiz_auto_map', 'preview': {'summary': preview.get('summary')}}
            mapping.validated_at = datetime.utcnow()
            mapping.updated_at = datetime.utcnow()
        else:
            mapping = EdxCourseMapping(
                id=str(uuid.uuid4()),
                openedx_course_id=course_id,
                subject_id=subject['id'],
                subject_offering_id=offering['id'],
                department_id=subject.get('department_id'),
                term=offering.get('term') or parsed.get('run'),
                created_by=actor,
                validation_status='low',
                validation_json={'auto_mapped': True, 'source': 'quiz_auto_map', 'preview': {'summary': preview.get('summary')}},
                validated_at=datetime.utcnow(),
            )
            self.db.add(mapping)
            self.db.flush()
        saved_mappings: list[dict] = []
        for item in preview.get('mappings') or []:
            if not item.get('requires_quiz'):
                stale = self.db.query(EdxCourseChapterMapping).filter(
                    EdxCourseChapterMapping.course_mapping_id == mapping.id,
                    EdxCourseChapterMapping.subject_chapter_id == item['chapter_id'],
                ).first()
                if stale:
                    stale.enabled = False
                    stale.validation_json = {
                        **(stale.validation_json or {}),
                        'auto_map_action': item.get('action') or 'skip',
                        'disabled_by_quiz_auto_map': True,
                    }
                    stale.updated_at = datetime.utcnow()
                    self.db.add(stale)
                saved_mappings.append({**item, 'course_chapter_mapping_id': None, 'mapping_status': 'skipped_no_quiz'})
                continue
            if not item.get('ready'):
                raise ValueError(f'{item.get("chapter_title") or "Bài"} chưa sẵn sàng để tạo Quiz/Final test.')
            existing = self.db.query(EdxCourseChapterMapping).filter(
                EdxCourseChapterMapping.course_mapping_id == mapping.id,
                EdxCourseChapterMapping.subject_chapter_id == item['chapter_id'],
            ).first()
            if item.get('action') == 'final_test':
                source_release_ids = list(item.get('source_release_ids') or [])
                if not source_release_ids:
                    raise ValueError('Final test chưa có Release nguồn từ các Bài Quiz.')
                validation = {
                    'ok': True,
                    'risk_level': 'low',
                    'can_create_mapping': True,
                    'message': 'Final test dùng bundle Release của các Bài Quiz; Release trên mapping chỉ là anchor tương thích API.',
                    'checks': [{
                        'code': 'final_test_release_bundle',
                        'status': 'pass',
                        'blocking': False,
                        'message': f'Final test dùng {len(source_release_ids)} Release nguồn.',
                        'detail': {
                            'source_release_ids': source_release_ids,
                            'source_chapter_ids': list(item.get('source_chapter_ids') or []),
                        },
                    }],
                    'auto_map_action': 'final_test',
                    'source_release_ids': source_release_ids,
                    'source_chapter_ids': list(item.get('source_chapter_ids') or []),
                }
            else:
                validation = self._chapter_mapping_validation(
                    course_mapping_id=mapping.id,
                    subject_chapter_id=item['chapter_id'],
                    bank_release_id=item['release_id'],
                    openedx_parent_node_id=item['openedx_section_id'],
                    openedx_node_title=item.get('openedx_section_title'),
                )
                validation = {**validation, 'auto_map_action': item.get('action') or 'quiz'}
            # The validation method flags existing mapping as fail. For idempotent auto-map,
            # ignore only that specific check when we are updating the same row.
            blocking = [check for check in validation.get('checks', []) if check.get('status') == 'fail' and check.get('code') != 'existing_chapter_mapping']
            if blocking:
                raise ValueError(blocking[0].get('message') or 'Chapter mapping không an toàn.')
            if existing:
                existing.bank_release_id = item['release_id']
                existing.openedx_parent_node_id = item['openedx_section_id']
                existing.enabled = True
                existing.validation_status = 'low'
                existing.validation_json = validation
                existing.validated_at = datetime.utcnow()
                existing.updated_at = datetime.utcnow()
                chapter_mapping = existing
            else:
                chapter_mapping = EdxCourseChapterMapping(
                    id=str(uuid.uuid4()),
                    course_mapping_id=mapping.id,
                    subject_chapter_id=item['chapter_id'],
                    bank_release_id=item['release_id'],
                    openedx_parent_node_id=item['openedx_section_id'],
                    enabled=True,
                    validation_status='low',
                    validation_json=validation,
                    validated_at=datetime.utcnow(),
                )
                self.db.add(chapter_mapping)
            self.db.flush()
            saved_mappings.append({**item, 'course_chapter_mapping_id': chapter_mapping.id})
        self.db.commit()
        saved_message = f'Đã lưu cấu hình version {offering.get("code")}: {len([item for item in saved_mappings if item.get("requires_quiz")])} bài có thể tạo Quiz/Final test, {len([item for item in saved_mappings if item.get("skipped")])} bài không tạo Quiz.'
        return {
            **preview,
            'ok': True,
            'mode': 'applied',
            'course_mapping': {'id': mapping.id, 'openedx_course_id': mapping.openedx_course_id, 'status': mapping.status},
            'mappings': saved_mappings,
            'can_apply': True,
            'message': saved_message,
            **_ui_notice('success', saved_message),
        }

    def _validation_result(self, checks: list[dict]) -> dict:
        blocking = [c for c in checks if c.get('status') == 'fail' and c.get('blocking', True)]
        warnings = [c for c in checks if c.get('status') == 'warn']
        if blocking:
            risk = 'high'
            ok = False
            message = blocking[0]['message']
        elif warnings:
            risk = 'medium'
            ok = True
            message = 'Có cảnh báo, cần kiểm tra trước khi lưu mapping.'
        else:
            risk = 'low'
            ok = True
            message = 'An toàn để map.'
        return {'ok': ok, 'risk_level': risk, 'checks': checks, 'can_create_mapping': ok, 'message': message}


    @staticmethod
    def _target_counts_for_quiz(total_questions: int, easy: int, medium: int, hard: int) -> dict[str, int]:
        total = max(int(total_questions or 0), 1)
        weights = {'easy': max(easy, 0), 'medium': max(medium, 0), 'hard': max(hard, 0)}
        if sum(weights.values()) <= 0:
            weights = {'easy': 50, 'medium': 30, 'hard': 20}
        raw = {key: total * weights[key] / sum(weights.values()) for key in weights}
        counts = {key: int(raw[key]) for key in weights}
        remaining = total - sum(counts.values())
        for key in sorted(weights, key=lambda item: (raw[item] - counts[item], {'easy': 0, 'medium': 1, 'hard': 2}[item]), reverse=True):
            if remaining <= 0:
                break
            counts[key] += 1
            remaining -= 1
        return counts

    @staticmethod
    def _difficulty_capacity_matrix(
        *,
        difficulty_targets: dict[str, int],
        classified_capacity: dict[str, int],
        flexible_capacity: int = 0,
        label: str = 'Release',
    ) -> tuple[dict[tuple[str, str], int], dict[tuple[str, str], int]]:
        """Allocate only by difficulty; response types remain whatever the Release contains.

        The synthetic ``auto`` column is retained only for rolling compatibility
        with the Open edX slot shape. The planner never inspects or constrains
        ``Question.question_type``.
        """
        order = ('easy', 'medium', 'hard')
        remaining_flexible = max(0, int(flexible_capacity or 0))
        flexible_by_difficulty = {diff: 0 for diff in order}
        shortages: dict[str, int] = {}
        for diff in order:
            target = max(0, int(difficulty_targets.get(diff, 0) or 0))
            available = max(0, int(classified_capacity.get(diff, 0) or 0))
            shortage = max(0, target - available)
            allocated = min(shortage, remaining_flexible)
            flexible_by_difficulty[diff] = allocated
            remaining_flexible -= allocated
            if allocated < shortage:
                shortages[diff] = shortage - allocated
        if shortages:
            available_summary = {
                diff: max(0, int(classified_capacity.get(diff, 0) or 0))
                for diff in order
            }
            raise ValueError(
                f'{label} không đủ câu theo độ khó để đáp ứng cấu hình. '
                f'Cần {_difficulty_summary(difficulty_targets)}. '
                f'Hiện có {_difficulty_summary(available_summary)}; '
                f'chưa phân loại: {max(0, int(flexible_capacity or 0))}. '
                'Hãy điều chỉnh tỷ lệ độ khó hoặc bổ sung câu hỏi.'
            )
        matrix = {
            (diff, 'auto'): max(0, int(difficulty_targets.get(diff, 0) or 0))
            for diff in order
        }
        flexible_matrix = {
            (diff, 'auto'): flexible_by_difficulty[diff]
            for diff in order
        }
        return matrix, flexible_matrix

    def _resolve_quiz_blueprint_config(
        self,
        *,
        release: QuestionBankRelease,
        quiz_blueprint_id: str | None,
        total_questions: int,
        difficulty_easy: int,
        difficulty_medium: int,
        difficulty_hard: int,
        max_families_per_bank: int,
    ) -> dict:
        config = {
            'total_questions': int(total_questions),
            'difficulty_easy': int(difficulty_easy),
            'difficulty_medium': int(difficulty_medium),
            'difficulty_hard': int(difficulty_hard),
            'max_families_per_bank': int(max_families_per_bank),
            'quiz_blueprint_id': None,
        }
        if not quiz_blueprint_id:
            return config
        blueprint = self.db.get(QuizBlueprint, quiz_blueprint_id)
        if not blueprint:
            raise ValueError('Không tìm thấy Quiz Blueprint.')
        if blueprint.status != 'active':
            raise ValueError(
                f'Quiz Blueprint hiện là {blueprint.status}; chỉ dùng Blueprint active.'
            )
        if (
            str(blueprint.subject_id) != str(release.subject_id)
            or str(blueprint.chapter_id) != str(release.chapter_id)
        ):
            raise ValueError('Quiz Blueprint không thuộc Subject/Chapter của Release.')
        if (
            blueprint.subject_offering_id
            and release.subject_offering_id
            and str(blueprint.subject_offering_id) != str(release.subject_offering_id)
        ):
            raise ValueError('Quiz Blueprint không thuộc version/offering của Release.')
        if int(blueprint.pick_count_per_slot or 1) != 1:
            raise ValueError(
                'Quiz Blueprint yêu cầu pick_count_per_slot=1 để giữ đúng tổng số câu.'
            )
        return {
            'total_questions': int(blueprint.total_questions),
            'difficulty_easy': int(blueprint.difficulty_easy),
            'difficulty_medium': int(blueprint.difficulty_medium),
            'difficulty_hard': int(blueprint.difficulty_hard),
            'max_families_per_bank': int(blueprint.max_families_per_bank),
            'quiz_blueprint_id': blueprint.id,
        }

    def _final_test_source_releases(
        self,
        *,
        course_mapping_id: str,
        final_chapter_id: str,
    ) -> tuple[list[QuestionBankRelease], list[dict]]:
        rows = self.db.query(EdxCourseChapterMapping).filter(
            EdxCourseChapterMapping.course_mapping_id == course_mapping_id,
            EdxCourseChapterMapping.enabled.is_(True),
            EdxCourseChapterMapping.subject_chapter_id != final_chapter_id,
        ).all()
        sources: list[tuple[int, int, SubjectChapter, QuestionBankRelease]] = []
        errors: list[str] = []
        for row in rows:
            chapter = self.db.get(SubjectChapter, row.subject_chapter_id)
            if not chapter:
                continue
            validation_json = row.validation_json or {}
            action = str(validation_json.get('auto_map_action') or '').lower()
            if not action:
                action = self._quiz_action_for_chapter_title(self._chapter_display_name(chapter))
            if action != 'quiz':
                continue
            release = self.db.get(QuestionBankRelease, row.bank_release_id) if row.bank_release_id else None
            title = self._chapter_display_name(chapter)
            component_ready, _component_total, _component_ready_count = self._release_component_ready(release)
            if not release:
                errors.append(f'{title}: chưa gắn Release')
                continue
            if release.status != 'published' or not release.openedx_library_key or not component_ready:
                errors.append(f'{title}: Release chưa published/verify đủ component')
                continue
            sources.append((int(chapter.sort_order or 0), int(chapter.chapter_no or 0), chapter, release))
        if errors:
            raise ValueError('Final test cần Release hợp lệ của tất cả Bài Quiz. ' + '; '.join(errors[:20]))
        sources.sort(key=lambda item: (item[0], item[1], str(item[2].id)))
        releases: list[QuestionBankRelease] = []
        details: list[dict] = []
        seen: set[str] = set()
        for _sort_order, _chapter_no, chapter, release in sources:
            if str(release.id) in seen:
                continue
            seen.add(str(release.id))
            releases.append(release)
            details.append({
                'chapter_id': chapter.id,
                'chapter_title': self._chapter_display_name(chapter),
                'release_id': release.id,
                'release_code': release.release_code,
                'openedx_library_key': release.openedx_library_key,
            })
        if not releases:
            raise ValueError('Final test chưa có Bài Quiz nào với Release published để làm nguồn câu hỏi.')
        return releases, details

    @staticmethod
    def _legacy_final_difficulty_is_unclassified(question: Question) -> bool:
        if str(getattr(question, 'source_type', '') or '').strip().lower() != 'legacy_quiz_excel':
            return False
        flags = {str(item or '').strip().lower() for item in (getattr(question, 'quality_flags', None) or [])}
        if 'legacy_import_unclassified_difficulty' in flags:
            return True
        try:
            evidence = json.loads(str(getattr(question, 'source_evidence', '') or '{}'))
        except (TypeError, ValueError):
            evidence = {}
        if isinstance(evidence, dict):
            classified = evidence.get('difficulty_classified')
            if isinstance(classified, bool):
                return not classified
            if 'threshold_raw' in evidence or 'difficulty_raw' in evidence:
                return not bool(str(evidence.get('threshold_raw') or '').strip() or str(evidence.get('difficulty_raw') or '').strip())
        return True

    def _build_final_test_plan(
        self,
        *,
        source_releases: list[QuestionBankRelease],
        source_details: list[dict] | None,
        total_questions: int,
        difficulty_easy: int,
        difficulty_medium: int,
        difficulty_hard: int,
        max_families_per_bank: int = 2,
    ) -> dict:
        del max_families_per_bank  # Final groups by source Library to satisfy native ItemBank boundaries.
        if not source_releases:
            raise ValueError('Final test chưa có Release nguồn.')
        if int(total_questions or 0) < len(source_releases):
            raise ValueError(
                f'Final test cần ít nhất {len(source_releases)} câu để mỗi Bài nguồn đóng góp ít nhất 1 câu; '
                f'hiện cấu hình {int(total_questions or 0)} câu.'
            )

        requested = self._target_counts_for_quiz(total_questions, difficulty_easy, difficulty_medium, difficulty_hard)
        requested_original = dict(requested)
        requested_types = {'auto': int(total_questions)}
        release_by_id = {str(item.id): item for item in source_releases}
        grouped: dict[tuple[str, str], list[dict]] = {}
        flexible: dict[str, list[dict]] = {}
        seen_questions: set[str] = set()
        seen_components: set[str] = set()
        invalid_details: list[str] = []
        source_question_counts: dict[str, int] = {str(item.id): 0 for item in source_releases}

        for release in source_releases:
            if release.status != 'published' or not release.openedx_library_key:
                raise ValueError(f'Release {release.release_code or release.id} chưa published đầy đủ cho Final test.')
            if not bool((release.metadata_json or {}).get('verification_complete')):
                raise ValueError(f'Release {release.release_code or release.id} chưa verify đầy đủ trên Open edX.')
            rows, questions = self._published_release_question_rows(release)
            for row in rows:
                question = questions[row.question_id]
                reasons: list[str] = []
                if question.status not in {'approved', 'published'}:
                    reasons.append(f'status={question.status}')
                if bool(question.is_retired):
                    reasons.append('retired')
                if bool(question.is_duplicate):
                    reasons.append('duplicate')
                if reasons:
                    preview = re.sub(r'\s+', ' ', str(question.question_text or '')).strip()[:100]
                    invalid_details.append(f'{question.id} · {preview} · {", ".join(reasons)}')
                    continue
                component = str(row.openedx_library_problem_id or '').strip().strip('"\'')
                if not component:
                    raise ValueError(f'Release question {row.question_id} chưa có Open edX Library component.')
                if str(question.id) in seen_questions or component in seen_components:
                    continue
                seen_questions.add(str(question.id))
                seen_components.add(component)
                source_question_counts[str(release.id)] = source_question_counts.get(str(release.id), 0) + 1
                qtype = 'auto'
                entry = {'release_id': str(release.id), 'row': row, 'question': question, 'component': component}
                if self._legacy_final_difficulty_is_unclassified(question):
                    flexible.setdefault(qtype, []).append(entry)
                else:
                    diff = normalize_difficulty(row.difficulty or question.difficulty)
                    grouped.setdefault((diff, qtype), []).append(entry)

        if invalid_details:
            sample = ' | '.join(invalid_details[:20])
            suffix = ' | ...' if len(invalid_details) > 20 else ''
            raise ValueError(
                f'Final test gặp {len(invalid_details)} câu không còn hợp lệ trong các Release nguồn. '
                f'Câu cần xử lý: {sample}{suffix}'
            )
        empty_sources = [rid for rid, count in source_question_counts.items() if count <= 0]
        if empty_sources:
            labels = [
                str(next((item.get('chapter_title') for item in (source_details or []) if str(item.get('release_id')) == rid), rid))
                for rid in empty_sources
            ]
            raise ValueError(f'Final test có Bài nguồn không còn câu hợp lệ: {", ".join(labels)}.')

        legacy_rebalanced = False
        legacy_entries = [entry for values in grouped.values() for entry in values] + [entry for values in flexible.values() for entry in values]
        manual_mode = bool(legacy_entries) and all(
            is_manually_authored_question(entry['question'])
            for entry in legacy_entries
        )
        if manual_mode or int(total_questions) == len(legacy_entries):
            order = ('easy', 'medium', 'hard')
            weights = {'easy': max(int(difficulty_easy or 0), 0), 'medium': max(int(difficulty_medium or 0), 0), 'hard': max(int(difficulty_hard or 0), 0)}
            classified_capacity = {diff: len(grouped.get((diff, 'auto'), [])) for diff in order}
            flex_left = len(flexible.get('auto', []))
            effective = {diff: min(int(requested.get(diff, 0) or 0), classified_capacity[diff]) for diff in order}
            for diff in order:
                missing = max(0, int(requested.get(diff, 0) or 0) - effective[diff])
                used = min(missing, flex_left)
                effective[diff] += used
                flex_left -= used
            remaining = int(total_questions) - sum(effective.values())
            while remaining > 0:
                candidates = [diff for diff in order if classified_capacity[diff] > effective[diff]]
                if candidates:
                    target_diff = min(candidates, key=lambda diff: (0 if weights[diff] > 0 else 1, effective[diff] / max(weights[diff], 1), order.index(diff)))
                    effective[target_diff] += 1
                    remaining -= 1
                    continue
                if flex_left > 0:
                    target_diff = min(order, key=lambda diff: (0 if weights[diff] > 0 else 1, effective[diff] / max(weights[diff], 1), order.index(diff)))
                    effective[target_diff] += 1
                    flex_left -= 1
                    remaining -= 1
                    continue
                break
            if sum(effective.values()) != int(total_questions):
                raise ValueError(
                    f'Bộ đề không đủ {int(total_questions)} câu để tạo Final test. '
                    f'Hiện có {_difficulty_summary(classified_capacity)}; '
                    f'chưa phân loại: {len(flexible.get("auto", []))}.'
                )
            legacy_rebalanced = effective != requested_original
            requested = effective
        matrix, flexible_matrix = self._difficulty_capacity_matrix(
            difficulty_targets=requested,
            classified_capacity={
                diff: len(grouped.get((diff, 'auto'), []))
                for diff in ('easy', 'medium', 'hard')
            },
            flexible_capacity=len(flexible.get('auto', [])),
            label='Final test',
        )

        allocated_flexible: dict[tuple[str, str], list[dict]] = {
            (diff, qtype): [] for diff in ('easy', 'medium', 'hard') for qtype in requested_types
        }
        for qtype in requested_types:
            candidates = sorted(
                flexible.get(qtype, []),
                key=lambda item: (str(getattr(item['question'], 'created_at', '') or ''), str(item['question'].id)),
            )
            offset = 0
            for diff in ('easy', 'medium', 'hard'):
                count = int(flexible_matrix.get((diff, qtype), 0) or 0)
                allocated_flexible[(diff, qtype)] = candidates[offset:offset + count]
                offset += count
            eligible = [diff for diff in ('easy', 'medium', 'hard') if int(matrix.get((diff, qtype), 0) or 0) > 0]
            for entry in candidates[offset:]:
                if not eligible:
                    break
                target_diff = min(
                    eligible,
                    key=lambda diff: (
                        len(grouped.get((diff, qtype), [])) + len(allocated_flexible[(diff, qtype)]),
                        ('easy', 'medium', 'hard').index(diff),
                    ),
                )
                allocated_flexible[(target_diff, qtype)].append(entry)

        cell_data: list[dict] = []
        release_pick_totals = {str(item.id): 0 for item in source_releases}
        for diff in ('easy', 'medium', 'hard'):
            for qtype in requested_types:
                target = int(matrix.get((diff, qtype), 0) or 0)
                if target <= 0:
                    continue
                entries = [*(grouped.get((diff, qtype), [])), *(allocated_flexible.get((diff, qtype), []))]
                by_release: dict[str, list[dict]] = {}
                for entry in entries:
                    by_release.setdefault(entry['release_id'], []).append(entry)
                allocation = {rid: 0 for rid in by_release}
                for _ in range(target):
                    candidates = [rid for rid, items in by_release.items() if allocation[rid] < len(items)]
                    if not candidates:
                        raise ValueError(f'Final test không đủ câu {diff.upper()} cho cấu hình {target} câu.')
                    rid = min(
                        candidates,
                        key=lambda value: (
                            release_pick_totals.get(value, 0),
                            allocation[value],
                            -len(by_release[value]),
                            value,
                        ),
                    )
                    allocation[rid] += 1
                    release_pick_totals[rid] = release_pick_totals.get(rid, 0) + 1
                cell_data.append({
                    'difficulty': diff,
                    'question_type': qtype,
                    'target': target,
                    'by_release': by_release,
                    'allocation': allocation,
                })

        # Guarantee that every source lesson contributes at least one visible Final question.
        for missing_rid in [rid for rid, count in release_pick_totals.items() if count <= 0]:
            repaired = False
            for cell in cell_data:
                missing_items = cell['by_release'].get(missing_rid) or []
                if not missing_items or int(cell['allocation'].get(missing_rid, 0)) >= len(missing_items):
                    continue
                donors = [
                    rid for rid, count in cell['allocation'].items()
                    if rid != missing_rid and count > 0 and release_pick_totals.get(rid, 0) > 1
                ]
                if not donors:
                    continue
                donor = max(donors, key=lambda rid: (release_pick_totals.get(rid, 0), cell['allocation'][rid], rid))
                cell['allocation'][donor] -= 1
                cell['allocation'][missing_rid] = int(cell['allocation'].get(missing_rid, 0)) + 1
                release_pick_totals[donor] -= 1
                release_pick_totals[missing_rid] += 1
                repaired = True
                break
            if not repaired:
                label = next((item.get('chapter_title') for item in (source_details or []) if str(item.get('release_id')) == missing_rid), missing_rid)
                raise ValueError(
                    f'Không thể đưa câu của {label} vào Final test với cấu hình độ khó hiện tại. '
                    'Hãy tăng số câu Final hoặc điều chỉnh tỷ lệ độ khó.'
                )

        slots: list[dict] = []
        assigned_questions: set[str] = set()
        assigned_components: set[str] = set()
        slot_no = 1
        coverage: list[dict] = []
        for cell in cell_data:
            cell_slot_count = 0
            candidate_count = 0
            for rid, pick_count in sorted(cell['allocation'].items()):
                if int(pick_count or 0) <= 0:
                    continue
                release = release_by_id[rid]
                entries = sorted(
                    cell['by_release'][rid],
                    key=lambda entry: (str(getattr(entry['question'], 'created_at', '') or ''), str(entry['question'].id)),
                )
                question_ids = [str(entry['question'].id) for entry in entries]
                problem_ids = [str(entry['component']) for entry in entries]
                if int(pick_count) > len(problem_ids):
                    raise ValueError(
                        f'Release {release.release_code or release.id} chỉ có {len(problem_ids)} ứng viên '
                        f'cho {cell["difficulty"].upper()}, cần pick {pick_count}.'
                    )
                assigned_questions.update(question_ids)
                assigned_components.update(problem_ids)
                candidate_count += len(problem_ids)
                cell_slot_count += 1
                detail = next((item for item in (source_details or []) if str(item.get('release_id')) == rid), {})
                chapter_title = str(detail.get('chapter_title') or release.release_code or rid)
                slots.append({
                    'slot_no': slot_no,
                    'difficulty': cell['difficulty'].upper(),
                    'question_type': cell['question_type'],
                    'pick_count': int(pick_count),
                    'max_count': int(pick_count),
                    'library_key': release.openedx_library_key,
                    'openedx_problem_ids': problem_ids,
                    'problem_display_names': {
                        entry['component']: _build_problem_display_name(entry['question'])
                        for entry in entries if is_manually_authored_question(entry['question'])
                    },
                    'question_ids': question_ids,
                    'family_names': [chapter_title],
                    'variant_count': len(question_ids),
                    'sampling_strategy': 'difficulty_pool',
                    'source_release_id': release.id,
                    'source_release_code': release.release_code,
                    'source_chapter_id': detail.get('chapter_id'),
                    'source_chapter_title': chapter_title,
                    'rule': f'random {int(pick_count)}/{len(question_ids)} từ {chapter_title}',
                })
                slot_no += 1
            coverage.append({
                'difficulty': cell['difficulty'].upper(),
                'question_type': cell['question_type'],
                'target_questions': int(cell['target']),
                'candidate_questions': candidate_count,
                'source_library_slots': cell_slot_count,
            })

        actual_total = sum(int(slot.get('pick_count') or 0) for slot in slots)
        if actual_total != int(total_questions):
            raise ValueError(f'Final test planner tạo {actual_total}/{int(total_questions)} câu; từ chối tạo cấu hình lệch số câu.')
        warnings: list[str] = []
        if legacy_rebalanced:
            warnings.append(
                f'Số câu khả dụng khác tỷ lệ đã chọn. Hệ thống tự cân lại độ khó '
                f'cho Final test thành {_difficulty_summary(requested)}, tổng cộng {int(total_questions)} câu.'
            )
        unclassified_count = sum(len(items) for items in flexible.values())
        if unclassified_count:
            warnings.append(
                f'{unclassified_count} câu CMS cũ chưa có NGƯỠNG/độ khó được phân bổ linh hoạt vào cấu hình độ khó Final test.'
            )
        source_ids = [str(item.id) for item in source_releases]
        return {
            'ok': True,
            'planner_engine': 'final_test_all_chapter_releases_itembank_v1',
            'uses_llm': False,
            'release_id': source_ids[0],
            'release_code': source_releases[0].release_code,
            'openedx_library_key': source_releases[0].openedx_library_key,
            'source_release_ids': source_ids,
            'source_release_codes': [str(item.release_code or '') for item in source_releases],
            'source_release_count': len(source_releases),
            'source_chapters': list(source_details or []),
            'requested_total_questions': int(total_questions),
            'total_questions': int(total_questions),
            'target_counts': {key.upper(): value for key, value in requested_original.items()},
            'effective_target_counts': {key.upper(): requested[key] for key in requested},
            'matrix_target_counts': {diff.upper(): int(requested.get(diff, 0) or 0) for diff in ('easy', 'medium', 'hard')},
            'coverage': coverage,
            'slots': slots,
            'warnings': warnings,
            'assigned_question_count': len(assigned_questions),
            'assigned_component_count': len(assigned_components),
            'unclassified_difficulty_question_count': unclassified_count,
            'flexibly_assigned_question_count': sum(len(items) for items in allocated_flexible.values()),
            'source_release_pick_counts': release_pick_totals,
            'classification_policy': 'legacy_flexible_fallback' if unclassified_count else 'strict',
            'hard_guard': {
                'valid': True,
                'summary': 'Final test dùng toàn bộ Release nguồn làm candidate pool theo cấu hình độ khó; mỗi ItemBank chỉ chứa component của đúng một Library.',
            },
            'message': (
                f'Final test tổng hợp {len(assigned_questions)} câu ứng viên từ {len(source_releases)} Bài/Release; '
                f'learner nhận đúng {int(total_questions)} câu theo cấu hình.'
            ),
            **_ui_notice(
                'success',
                f'Final test dùng {len(source_releases)} Release nguồn và {len(assigned_questions)} câu ứng viên.',
            ),
        }

    def _published_release_question_rows(self, release: QuestionBankRelease) -> tuple[list[BankReleaseQuestion], dict[str, Question]]:
        rows = self.db.query(BankReleaseQuestion).filter(BankReleaseQuestion.bank_release_id == release.id).all()
        if not rows:
            raise ValueError('Release chưa có câu hỏi nào. Hãy publish release sang Open edX Library trước.')
        question_ids = [row.question_id for row in rows]
        questions = {question.id: question for question in self.db.query(Question).filter(Question.id.in_(question_ids)).all()}
        missing_questions = [row.question_id for row in rows if row.question_id not in questions]
        if missing_questions:
            raise ValueError(f'Release có {len(missing_questions)} câu hỏi không còn tồn tại trong AI Server.')
        return rows, questions

    def _build_release_quiz_plan(
        self,
        *,
        release: QuestionBankRelease,
        total_questions: int,
        difficulty_easy: int,
        difficulty_medium: int,
        difficulty_hard: int,
        max_families_per_bank: int = 2,
    ) -> dict:
        if release.status != 'published':
            raise ValueError(f'Release hiện là {release.status}; chỉ tạo quiz từ Release đã published.')
        if not release.openedx_library_key:
            raise ValueError('Release chưa có Open edX Library key. Hãy publish Library trước khi tạo quiz.')
        if not bool((release.metadata_json or {}).get('verification_complete')):
            raise ValueError('Release chưa có bằng chứng verify đầy đủ từ Open edX. Hãy publish/re-verify Release trước khi tạo Quiz.')
        rows, questions = self._published_release_question_rows(release)
        manual_mode = bool(rows) and all(is_manually_authored_question(questions[row.question_id]) for row in rows)
        by_component: dict[str, BankReleaseQuestion] = {}
        duplicate_components: list[str] = []
        for row in rows:
            component = str(row.openedx_library_problem_id or '').strip().strip('"\'')
            if not component:
                raise ValueError(f'Release question {row.question_id} chưa có Open edX Library component. Hãy publish/re-publish Release.')
            if component in by_component:
                duplicate_components.append(component)
            by_component[component] = row
        if duplicate_components:
            raise ValueError(f'Release chứa component Open edX bị trùng: {duplicate_components[:5]}')

        # Shared-library slot planner v4:
        # - learner-visible question count is exact per difficulty (one ItemBank slot = one visible question)
        # - a Library component/question is assigned to exactly one slot
        # - a concept/family stays in exactly one slot when there are enough concepts
        # - when concepts/families are more than slots, whole concepts are bin-packed so slot candidate counts are balanced
        # - when concepts/families are fewer than slots, the planner splits large concepts only as a last-resort soft mode
        #   to still satisfy the requested EASY/MEDIUM/HARD counts.
        def is_legacy_quiz_question(question: Question) -> bool:
            return str(getattr(question, 'source_type', '') or '').strip().lower() == 'legacy_quiz_excel'

        def legacy_difficulty_is_unclassified(question: Question) -> bool:
            if not is_legacy_quiz_question(question):
                return False
            flags = {
                str(item or '').strip().lower()
                for item in (getattr(question, 'quality_flags', None) or [])
            }
            if 'legacy_import_unclassified_difficulty' in flags:
                return True
            try:
                evidence = json.loads(str(getattr(question, 'source_evidence', '') or '{}'))
            except (TypeError, ValueError):
                evidence = {}
            if isinstance(evidence, dict):
                classified = evidence.get('difficulty_classified')
                if isinstance(classified, bool):
                    return not classified
                if 'threshold_raw' in evidence or 'difficulty_raw' in evidence:
                    return not bool(
                        str(evidence.get('threshold_raw') or '').strip()
                        or str(evidence.get('difficulty_raw') or '').strip()
                    )
            # A legacy row without provenance must not pretend that the model
            # default is a teacher-supplied difficulty.
            return True

        def legacy_concept_is_unclassified(question: Question) -> bool:
            if not is_legacy_quiz_question(question):
                return False
            return not any(
                str(value or '').strip()
                for value in (
                    getattr(question, 'concept_id', None),
                    getattr(question, 'concept_key', None),
                    getattr(question, 'concept_title', None),
                    getattr(question, 'learning_objective', None),
                )
            )

        grouped_rows: dict[tuple[str, str], list[BankReleaseQuestion]] = {}
        flexible_rows: dict[str, list[BankReleaseQuestion]] = {}
        unclassified_concept_question_ids: set[str] = set()
        for row in rows:
            question = questions[row.question_id]
            qtype = 'auto'
            if legacy_difficulty_is_unclassified(question):
                flexible_rows.setdefault(qtype, []).append(row)
            else:
                diff = normalize_difficulty(row.difficulty or question.difficulty)
                grouped_rows.setdefault((diff, qtype), []).append(row)
            if legacy_concept_is_unclassified(question):
                unclassified_concept_question_ids.add(question.id)

        def concept_key_for(row: BankReleaseQuestion) -> str:
            question = questions[row.question_id]
            if legacy_concept_is_unclassified(question):
                return f'legacy-unclassified-{question.id}'
            key = (
                getattr(question, 'concept_id', None)
                or row.question_family_id
                or getattr(question, 'question_family_id', None)
                or getattr(question, 'concept_title', None)
                or getattr(question, 'topic', None)
                or f'question-{question.id}'
            )
            return str(key).strip() or f'question-{question.id}'

        def concept_name_for(row: BankReleaseQuestion, key: str) -> str:
            question = questions[row.question_id]
            if legacy_concept_is_unclassified(question):
                return f'Câu CMS cũ chưa phân loại {str(question.id)[:8]}'
            return str(
                getattr(question, 'concept_title', None)
                or getattr(question, 'topic', None)
                or row.question_family_id
                or getattr(question, 'question_family_id', None)
                or key
            ).strip() or key

        def add_row_to_bucket(bucket: dict, row: BankReleaseQuestion, *, split: bool = False) -> None:
            key = concept_key_for(row)
            name = concept_name_for(row, key)
            question = questions[row.question_id]
            payload = bucket['families'].setdefault(key, {
                'family_id': key,
                'family_name': name,
                'concept_id': getattr(question, 'concept_id', None),
                'concept_title': getattr(question, 'concept_title', None),
                'unclassified_concept': legacy_concept_is_unclassified(question),
                'variant_count': 0,
                'question_ids': [],
                'split_across_slots': bool(split),
            })
            payload['variant_count'] += 1
            payload['question_ids'].append(question.id)
            payload['split_across_slots'] = bool(payload.get('split_across_slots') or split)
            bucket['rows'].append(row)
            bucket['load'] += 1

        def remove_one_row_from_bucket(bucket: dict, family_key: str) -> BankReleaseQuestion | None:
            for idx in range(len(bucket['rows']) - 1, -1, -1):
                row = bucket['rows'][idx]
                if concept_key_for(row) != family_key:
                    continue
                bucket['rows'].pop(idx)
                bucket['load'] -= 1
                payload = bucket['families'].get(family_key)
                question = questions[row.question_id]
                if payload:
                    payload['question_ids'] = [qid for qid in payload.get('question_ids', []) if qid != question.id]
                    payload['variant_count'] = max(0, int(payload.get('variant_count') or 0) - 1)
                    if not payload['question_ids']:
                        bucket['families'].pop(family_key, None)
                return row
            return None

        def build_balanced_slots_for_cell(diff: str, qtype: str, diff_rows: list[BankReleaseQuestion], target_count: int) -> tuple[list[dict], dict, list[str]]:
            diff_warnings: list[str] = []
            available_count = len(diff_rows)
            if target_count <= 0:
                return [], {
                    'difficulty': diff.upper(),
                    'question_type': qtype,
                    'target_questions': 0,
                    'available_questions': available_count,
                    'selected_slots': 0,
                    'status': 'not_requested',
                }, []
            if available_count <= 0:
                raise ValueError(f'Release chưa có câu {diff.upper()} · {qtype} để tạo Problem Bank.')
            if available_count < target_count:
                raise ValueError(
                    f'Release không đủ câu {diff.upper()} · {qtype}: cần {target_count}, hiện có {available_count}. '
                    'Hãy tạo/publish thêm câu hoặc giảm tỷ lệ/số câu Quiz.'
                )

            if manual_mode:
                ordered_rows = sorted(diff_rows, key=lambda row: str(row.question_id))
                question_ids = [row.question_id for row in ordered_rows]
                problem_ids = [str(row.openedx_library_problem_id).strip().strip('\"\'') for row in ordered_rows]
                difficulty_label = {'easy': 'Dễ', 'medium': 'Trung bình', 'hard': 'Khó'}[diff]
                return [{
                    'difficulty': diff.upper(),
                    'question_type': qtype,
                    'pick_count': target_count,
                    'max_count': target_count,
                    'library_key': release.openedx_library_key,
                    'openedx_problem_ids': problem_ids,
                    'problem_display_names': {
                        component: _build_problem_display_name(questions[question_id])
                        for component, question_id in zip(problem_ids, question_ids)
                    },
                    'question_ids': question_ids,
                    'families': [],
                    'family_names': [],
                    'variant_count': available_count,
                    'sampling_strategy': 'difficulty_pool',
                    'rule': f'Lấy {target_count}/{available_count} câu {difficulty_label}',
                }], {
                    'difficulty': diff.upper(), 'question_type': qtype,
                    'target_questions': target_count, 'available_questions': available_count,
                    'selected_slots': 1, 'status': 'difficulty_pool',
                }, []

            # Group by concept/family. The planner keeps a group whole unless it is impossible
            # to satisfy the exact requested slot count without splitting.
            group_map: dict[str, dict] = {}
            for row in sorted(diff_rows, key=lambda item: (
                concept_key_for(item),
                str(getattr(questions[item.question_id], 'created_at', '') or ''),
                str(item.question_id),
            )):
                key = concept_key_for(row)
                group = group_map.setdefault(key, {
                    'key': key,
                    'name': concept_name_for(row, key),
                    'rows': [],
                })
                group['rows'].append(row)
            groups = list(group_map.values())
            groups.sort(key=lambda group: (-len(group['rows']), str(group['name']).casefold(), str(group['key'])))

            buckets = [{'rows': [], 'families': {}, 'load': 0} for _ in range(target_count)]
            split_family_keys: set[str] = set()

            if len(groups) >= target_count:
                # Enough concepts: never split a concept. Put whole concepts into the currently lightest slot.
                for group in groups:
                    index = min(range(target_count), key=lambda idx: (buckets[idx]['load'], len(buckets[idx]['families']), idx))
                    for row in group['rows']:
                        add_row_to_bucket(buckets[index], row, split=False)
            else:
                # Not enough concepts for the required number of visible questions. Soft mode:
                # split only the minimum needed to make every slot non-empty, then balance loads.
                diff_warnings.append(
                    f'{diff.upper()} · {qtype} chỉ có {len(groups)} concept/family cho {target_count} slot; '
                    'hệ thống phải tách một số concept sang nhiều slot để đủ số câu hiển thị.'
                )
                for idx, group in enumerate(groups):
                    for row in group['rows']:
                        add_row_to_bucket(buckets[idx], row, split=False)

                def donor_choice() -> tuple[int | None, str | None]:
                    best_idx: int | None = None
                    best_key: str | None = None
                    best_score = (-1, '')
                    for idx, bucket in enumerate(buckets):
                        if bucket['load'] <= 1:
                            continue
                        family_counts: dict[str, int] = {}
                        for row in bucket['rows']:
                            key = concept_key_for(row)
                            family_counts[key] = family_counts.get(key, 0) + 1
                        for key, count in family_counts.items():
                            if count <= 1:
                                continue
                            score = (count, str(key))
                            if score > best_score:
                                best_score = score
                                best_idx = idx
                                best_key = key
                    return best_idx, best_key

                for empty_idx, bucket in enumerate(buckets):
                    if bucket['load'] > 0:
                        continue
                    donor_idx, donor_key = donor_choice()
                    if donor_idx is None or donor_key is None:
                        raise ValueError(f'Không thể chia đủ {target_count} slot {diff.upper()} mà vẫn có câu trong mỗi slot.')
                    moved = remove_one_row_from_bucket(buckets[donor_idx], donor_key)
                    if moved is None:
                        raise ValueError(f'Không thể tách concept {donor_key} để tạo slot {diff.upper()}.')
                    split_family_keys.add(donor_key)
                    add_row_to_bucket(bucket, moved, split=True)

                # Balance candidate counts so slots are not extremely uneven.
                guard = 0
                while guard < 1000:
                    guard += 1
                    max_idx = max(range(target_count), key=lambda idx: (buckets[idx]['load'], -idx))
                    min_idx = min(range(target_count), key=lambda idx: (buckets[idx]['load'], idx))
                    if buckets[max_idx]['load'] - buckets[min_idx]['load'] <= 1:
                        break
                    donor_idx, donor_key = donor_choice()
                    if donor_idx is None or donor_key is None or donor_idx == min_idx:
                        break
                    moved = remove_one_row_from_bucket(buckets[donor_idx], donor_key)
                    if moved is None:
                        break
                    split_family_keys.add(donor_key)
                    add_row_to_bucket(buckets[min_idx], moved, split=True)

            result_slots: list[dict] = []
            loads = []
            for bucket_index, bucket in enumerate(buckets, start=1):
                if bucket['load'] <= 0:
                    raise ValueError(f'Slot {bucket_index} {diff.upper()} không có câu hỏi nào; từ chối tạo Quiz rỗng.')
                family_payloads = list(bucket['families'].values())
                question_ids: list[str] = []
                problem_ids: list[str] = []
                for row in bucket['rows']:
                    question = questions[row.question_id]
                    component = str(row.openedx_library_problem_id or '').strip().strip('"\'')
                    if not component:
                        raise ValueError(f'Release question {row.question_id} chưa có Open edX Library component. Hãy publish/re-publish Release.')
                    question_ids.append(question.id)
                    problem_ids.append(component)
                loads.append(len(problem_ids))
                result_slots.append({
                    'difficulty': diff.upper(),
                    'question_type': qtype,
                    'pick_count': 1,
                    'max_count': 1,
                    'library_key': release.openedx_library_key,
                    'openedx_problem_ids': problem_ids,
                    'question_ids': question_ids,
                    'families': family_payloads,
                    'family_names': [item['family_name'] for item in family_payloads],
                    'variant_count': len(question_ids),
                    'repeated_family': bool(split_family_keys),
                    'split_family_keys': sorted(split_family_keys),
                    'rule': f'random 1/{max(len(question_ids), 1)} {diff.upper()} · {qtype} variants',
                    'warning': 'Có concept bị tách do thiếu concept/family.' if split_family_keys else '',
                })

            coverage = {
                'difficulty': diff.upper(),
                'question_type': qtype,
                'target_questions': target_count,
                'available_questions': available_count,
                'selected_slots': len(result_slots),
                'concept_count': len(groups),
                'split_concept_count': len(split_family_keys),
                'slot_candidate_loads': loads,
                'status': 'balanced_no_concept_split' if not split_family_keys else 'balanced_soft_split_due_to_insufficient_concepts',
            }
            return result_slots, coverage, diff_warnings

        requested = self._target_counts_for_quiz(total_questions, difficulty_easy, difficulty_medium, difficulty_hard)
        requested_original = dict(requested)
        requested_types = {'auto': int(total_questions)}
        legacy_rebalanced = False
        if manual_mode or int(total_questions) == len(rows):
            order = ('easy', 'medium', 'hard')
            weights = {'easy': max(int(difficulty_easy or 0), 0), 'medium': max(int(difficulty_medium or 0), 0), 'hard': max(int(difficulty_hard or 0), 0)}
            classified_capacity = {diff: len(grouped_rows.get((diff, 'auto'), [])) for diff in order}
            flex_left = len(flexible_rows.get('auto', []))
            effective = {diff: min(int(requested.get(diff, 0) or 0), classified_capacity[diff]) for diff in order}
            for diff in order:
                missing = max(0, int(requested.get(diff, 0) or 0) - effective[diff])
                used = min(missing, flex_left)
                effective[diff] += used
                flex_left -= used
            remaining = int(total_questions) - sum(effective.values())
            while remaining > 0:
                candidates = [diff for diff in order if classified_capacity[diff] > effective[diff]]
                if candidates:
                    target_diff = min(candidates, key=lambda diff: (0 if weights[diff] > 0 else 1, effective[diff] / max(weights[diff], 1), order.index(diff)))
                    effective[target_diff] += 1
                    remaining -= 1
                    continue
                if flex_left > 0:
                    target_diff = min(order, key=lambda diff: (0 if weights[diff] > 0 else 1, effective[diff] / max(weights[diff], 1), order.index(diff)))
                    effective[target_diff] += 1
                    flex_left -= 1
                    remaining -= 1
                    continue
                break
            if sum(effective.values()) != int(total_questions):
                raise ValueError(
                    f'Bộ đề không đủ {int(total_questions)} câu để tạo Quiz. '
                    f'Hiện có {_difficulty_summary(classified_capacity)}; '
                    f'chưa phân loại: {len(flexible_rows.get("auto", []))}.'
                )
            legacy_rebalanced = effective != requested_original
            requested = effective
        matrix, flexible_matrix = self._difficulty_capacity_matrix(
            difficulty_targets=requested,
            classified_capacity={
                diff: len(grouped_rows.get((diff, 'auto'), []))
                for diff in ('easy', 'medium', 'hard')
            },
            flexible_capacity=len(flexible_rows.get('auto', [])),
            label='Release',
        )
        allocated_flexible_rows: dict[tuple[str, str], list[BankReleaseQuestion]] = {}
        for qtype in requested_types:
            candidates = sorted(
                flexible_rows.get(qtype, []),
                key=lambda item: (
                    str(getattr(questions[item.question_id], 'created_at', '') or ''),
                    str(item.question_id),
                ),
            )
            offset = 0
            for diff in ('easy', 'medium', 'hard'):
                count = int(flexible_matrix.get((diff, qtype), 0) or 0)
                allocated_flexible_rows[(diff, qtype)] = candidates[offset:offset + count]
                offset += count
            eligible_difficulties = [
                diff
                for diff in ('easy', 'medium', 'hard')
                if int(matrix.get((diff, qtype), 0) or 0) > 0
            ]
            for row in candidates[offset:]:
                if not eligible_difficulties:
                    break
                target_diff = min(
                    eligible_difficulties,
                    key=lambda diff: (
                        len(grouped_rows.get((diff, qtype), []))
                        + len(allocated_flexible_rows.get((diff, qtype), [])),
                        ('easy', 'medium', 'hard').index(diff),
                    ),
                )
                allocated_flexible_rows[(target_diff, qtype)].append(row)
        slots: list[dict] = []
        coverage: list[dict] = []
        warnings: list[str] = []
        if legacy_rebalanced:
            warnings.append(
                f'Số câu khả dụng khác tỷ lệ đã chọn. Hệ thống tự cân lại độ khó '
                f'thành {_difficulty_summary(requested)}, tổng cộng {int(total_questions)} câu.'
            )
        unclassified_difficulty_count = sum(len(items) for items in flexible_rows.values())
        flexibly_assigned_count = sum(len(items) for items in allocated_flexible_rows.values())
        if unclassified_difficulty_count:
            warnings.append(
                f'{unclassified_difficulty_count} câu CMS cũ chưa có NGƯỠNG/độ khó; '
                f'{flexibly_assigned_count} câu được phân bổ linh hoạt vào các mức Dễ, Trung bình và Khó.'
            )
        assigned_question_ids: set[str] = set()
        assigned_components: set[str] = set()
        slot_no = 1
        for diff in ('easy', 'medium', 'hard'):
            for qtype in requested_types:
                target_count = int(matrix.get((diff, qtype), 0) or 0)
                cell_rows = [
                    *(grouped_rows.get((diff, qtype)) or []),
                    *(allocated_flexible_rows.get((diff, qtype)) or []),
                ]
                cell_slots, cell_coverage, cell_warnings = build_balanced_slots_for_cell(
                    diff, qtype, cell_rows, target_count
                )
                cell_coverage['flexibly_assigned_questions'] = len(
                    allocated_flexible_rows.get((diff, qtype)) or []
                )
                warnings.extend(cell_warnings)
                for slot in cell_slots:
                    slot['slot_no'] = slot_no
                    slot_no += 1
                    unique_questions = []
                    unique_components = []
                    for question_id, component in zip(slot.get('question_ids') or [], slot.get('openedx_problem_ids') or []):
                        if question_id in assigned_question_ids:
                            raise ValueError(f'Câu hỏi {question_id} bị đưa vào nhiều Problem Bank; hệ thống từ chối tạo quiz.')
                        if component in assigned_components:
                            raise ValueError(f'Open edX component {component} bị đưa vào nhiều Problem Bank; hệ thống từ chối tạo quiz.')
                        assigned_question_ids.add(question_id)
                        assigned_components.add(component)
                        unique_questions.append(question_id)
                        unique_components.append(component)
                    slot['question_ids'] = unique_questions
                    slot['openedx_problem_ids'] = unique_components
                    slots.append(slot)
                coverage.append(cell_coverage)
        if not slots:
            raise ValueError('Không có mức độ nào được chọn để tạo Problem Bank.')
        if sum(int(slot.get('pick_count') or 0) for slot in slots) != int(total_questions):
            warnings.append(
                f'Tổng pick_count thực tế {sum(int(slot.get("pick_count") or 0) for slot in slots)} khác yêu cầu {total_questions}; hãy kiểm tra tỷ lệ difficulty.'
            )
        plan = {
            'ok': True,
            'planner_engine': 'bank_release_difficulty_pool_v6' if manual_mode else 'bank_release_difficulty_itembank_v5',
            'sampling_strategy': 'difficulty_pool' if manual_mode else 'concept_slots',
            'uses_llm': False,
            'release_id': release.id,
            'release_code': release.release_code,
            'openedx_library_key': release.openedx_library_key,
            'requested_total_questions': int(total_questions),
            'total_questions': int(total_questions),
            'target_counts': {k.upper(): v for k, v in requested_original.items()},
            'effective_target_counts': {k.upper(): requested[k] for k in requested},
            'matrix_target_counts': {diff.upper(): int(requested.get(diff, 0) or 0) for diff in ('easy', 'medium', 'hard')},
            'coverage': coverage,
            'slots': slots,
            'warnings': list(dict.fromkeys(warnings)),
            'assigned_question_count': len(assigned_question_ids),
            'assigned_component_count': len(assigned_components),
            'classification_policy': 'legacy_flexible_fallback' if unclassified_difficulty_count or unclassified_concept_question_ids else 'strict',
            'unclassified_difficulty_question_count': unclassified_difficulty_count,
            'unclassified_concept_question_count': len(unclassified_concept_question_ids),
            'flexibly_assigned_question_count': flexibly_assigned_count,
            'hard_guard': {'valid': True, 'summary': 'Release plan hợp lệ: đúng số câu theo độ khó hiệu lực; không trùng question_id hoặc Open edX component giữa các bank.'},
            'message': f'Tạo kế hoạch {len(slots)} Problem Bank theo cấu hình độ khó, learner thấy {int(total_questions)} câu.',
            **_ui_notice('success', f'Tạo kế hoạch {len(slots)} Problem Bank theo cấu hình độ khó, learner thấy {int(total_questions)} câu.'),
        }
        return plan

    def preview_quiz_from_release(
        self,
        *,
        bank_release_id: str,
        total_questions: int = 15,
        difficulty_easy: int = 50,
        difficulty_medium: int = 30,
        difficulty_hard: int = 20,
        max_families_per_bank: int = 2,
        quiz_blueprint_id: str | None = None,
    ) -> dict:
        release = self.db.get(QuestionBankRelease, bank_release_id)
        if not release:
            raise ValueError('Không tìm thấy Bank Release')
        config = self._resolve_quiz_blueprint_config(
            release=release,
            quiz_blueprint_id=quiz_blueprint_id,
            total_questions=total_questions,
            difficulty_easy=difficulty_easy,
            difficulty_medium=difficulty_medium,
            difficulty_hard=difficulty_hard,
            max_families_per_bank=max_families_per_bank,
        )
        plan = self._build_release_quiz_plan(
            release=release,
            **{key: value for key, value in config.items() if key != 'quiz_blueprint_id'},
        )
        plan['quiz_blueprint_id'] = config.get('quiz_blueprint_id')
        return plan

    async def create_quiz_from_release(
        self,
        *,
        course_chapter_mapping_id: str,
        quiz_title: str,
        unit_title: str = 'Quiz tự luyện',
        total_questions: int = 15,
        difficulty_easy: int = 50,
        difficulty_medium: int = 30,
        difficulty_hard: int = 20,
        max_families_per_bank: int = 2,
        quiz_blueprint_id: str | None = None,
        custom_timer_enabled: bool = True,
        time_limit_minutes: int = 15,
        retake_cooldown_minutes: int = 5,
        auto_submit_on_timeout: bool = True,
        lock_after_timeout: bool = True,
        native_timed_exam: bool = False,
        assessment_type: str = 'quiz',
        actor: str | None = None,
        expected_bank_release_id: str | None = None,
    ) -> dict:
        chapter_mapping = self.db.get(EdxCourseChapterMapping, course_chapter_mapping_id)
        if not chapter_mapping:
            raise ValueError('Không tìm thấy chapter mapping')
        course_mapping = self.db.get(EdxCourseMapping, chapter_mapping.course_mapping_id)
        if not course_mapping:
            raise ValueError('Không tìm thấy course mapping')
        assessment_type = 'final_test' if str(assessment_type or '').lower() == 'final_test' else 'quiz'
        release_id = chapter_mapping.bank_release_id
        if expected_bank_release_id and release_id != expected_bank_release_id:
            raise ValueError('Release trên URL không khớp với chapter mapping. Hãy chọn lại mapping đúng Release.')
        if not release_id:
            raise ValueError('Chapter mapping chưa gắn Bank Release')
        release = self.db.get(QuestionBankRelease, release_id)
        if not release:
            raise ValueError('Không tìm thấy Bank Release')
        if release.status != 'published':
            raise ValueError('Chỉ tạo Quiz từ Release đã published sang Open edX Library')
        if not bool((release.metadata_json or {}).get('verification_complete')):
            raise ValueError('Release chưa được Open edX verify đầy đủ; không tạo Quiz từ component chưa xác nhận.')
        if not chapter_mapping.openedx_parent_node_id:
            raise ValueError('Chapter mapping chưa có node Open edX để đặt Quiz')
        final_source_releases: list[QuestionBankRelease] = []
        final_source_details: list[dict] = []
        if assessment_type == 'final_test':
            if quiz_blueprint_id:
                raise ValueError('Final test dùng cấu hình Final test tổng hợp, không dùng Blueprint của một Bài đơn lẻ.')
            final_source_releases, final_source_details = self._final_test_source_releases(
                course_mapping_id=chapter_mapping.course_mapping_id,
                final_chapter_id=chapter_mapping.subject_chapter_id,
            )
            anchor_release = final_source_releases[0]
            if str(release.id) != str(anchor_release.id):
                raise ValueError('Anchor Release của Final test đã cũ. Hãy bấm Lưu cấu hình lại trước khi tạo Final test.')
            resolved_quiz_config = {
                'total_questions': int(total_questions),
                'difficulty_easy': int(difficulty_easy),
                'difficulty_medium': int(difficulty_medium),
                'difficulty_hard': int(difficulty_hard),
                'max_families_per_bank': int(max_families_per_bank),
                'quiz_blueprint_id': None,
            }
            quiz_blueprint_id = None
            validation = {
                **(chapter_mapping.validation_json or {}),
                'ok': True,
                'risk_level': 'low',
                'can_create_mapping': True,
                'auto_map_action': 'final_test',
                'source_release_ids': [str(item.id) for item in final_source_releases],
                'message': f'Final test dùng {len(final_source_releases)} Release nguồn đã verify.',
                'checks': [{
                    'code': 'final_test_release_bundle',
                    'status': 'pass',
                    'blocking': False,
                    'message': f'Đã xác minh {len(final_source_releases)} Release nguồn cho Final test.',
                    'detail': {'source_release_ids': [str(item.id) for item in final_source_releases]},
                }],
            }
        else:
            resolved_quiz_config=self._resolve_quiz_blueprint_config(release=release,quiz_blueprint_id=quiz_blueprint_id,total_questions=total_questions,difficulty_easy=difficulty_easy,difficulty_medium=difficulty_medium,difficulty_hard=difficulty_hard,max_families_per_bank=max_families_per_bank)
            quiz_blueprint_id=resolved_quiz_config.get('quiz_blueprint_id')
            validation = self._chapter_mapping_validation(
                course_mapping_id=chapter_mapping.course_mapping_id,
                subject_chapter_id=chapter_mapping.subject_chapter_id,
                bank_release_id=release.id,
                openedx_parent_node_id=chapter_mapping.openedx_parent_node_id,
            )
        # _chapter_mapping_validation is also used before creating a new mapping,
        # so it intentionally flags an existing chapter mapping as a duplicate.
        # At quiz creation time we already receive a concrete
        # course_chapter_mapping_id. Reusing that exact row is valid and must not
        # block quiz creation. Still block if the duplicate check points to a
        # different mapping row.
        blocking_checks = []
        for check in validation.get('checks', []):
            if check.get('status') != 'fail':
                continue
            if check.get('code') == 'existing_chapter_mapping' and str((check.get('detail') or {}).get('mapping_id')) == str(chapter_mapping.id):
                continue
            blocking_checks.append(check)
        if blocking_checks:
            raise ValueError(f'Mapping không an toàn để tạo Quiz: {blocking_checks[0].get("message") or validation.get("message")}')
        if assessment_type == 'final_test':
            plan = self._build_final_test_plan(
                source_releases=final_source_releases,
                source_details=final_source_details,
                **{key: value for key, value in resolved_quiz_config.items() if key != 'quiz_blueprint_id'},
            )
        else:
            plan=self._build_release_quiz_plan(release=release,**{key:value for key,value in resolved_quiz_config.items() if key!='quiz_blueprint_id'})
        plan['quiz_blueprint_id']=quiz_blueprint_id
        subject = self.db.get(Subject, course_mapping.subject_id or release.subject_id)
        chapter = self.db.get(SubjectChapter, chapter_mapping.subject_chapter_id)
        connector = get_openedx_connector()
        course_id = normalize_openedx_course_id(course_mapping.openedx_course_id, required=True)
        if course_mapping.openedx_course_id != course_id:
            course_mapping.openedx_course_id = course_id
            course_mapping.updated_at = datetime.utcnow()
            self.db.add(course_mapping)
        quiz_suffix = self._chapter_quiz_suffix(chapter)
        default_quiz_title = 'Final test' if assessment_type == 'final_test' else f'Quiz {quiz_suffix}'.strip()
        default_unit_title = 'Final test' if assessment_type == 'final_test' else 'Quiz'
        final_quiz_title = (quiz_title or default_quiz_title).strip() or default_quiz_title
        final_unit_title = (unit_title or default_unit_title).strip() or default_unit_title
        grade_as = 'Final Exam' if assessment_type == 'final_test' else 'Quiz'
        timer_config = {
            'custom_timer_enabled': bool(custom_timer_enabled),
            'time_limit_minutes': int(time_limit_minutes or 15),
            'duration_seconds': int(time_limit_minutes or 15) * 60,
            'retake_cooldown_minutes': int(retake_cooldown_minutes or 0),
            'cooldown_seconds': int(retake_cooldown_minutes or 0) * 60,
            'auto_submit_on_timeout': bool(auto_submit_on_timeout),
            'lock_after_timeout': bool(lock_after_timeout),
            'native_timed_exam': bool(native_timed_exam),
        }
        if timer_config['native_timed_exam']:
            raise ValueError('Quiz tự luyện không dùng native Timed Exam. Hãy dùng custom timer.')

        quiz_idempotency_key = f'course_quiz:{chapter_mapping.id}:{assessment_type}'

        # One active AI-managed assessment per Course + chapter mapping + type.
        # Without this guard, pressing Create repeatedly appends another Quiz
        # subsection to the same lesson, so 5 questions can become 10, 15, ...
        # The existing instance must be rolled back from Quiz History first.
        active_instances = (
            self.db.query(CourseQuizInstance)
            .filter(
                CourseQuizInstance.openedx_course_id == course_id,
                CourseQuizInstance.chapter_id == chapter.id,
                CourseQuizInstance.status.in_(['creating', 'created', 'published', 'rollback_manual_required']),
            )
            .order_by(CourseQuizInstance.created_at.desc())
            .limit(100)
            .all()
        )
        duplicate_instance = next((
            row for row in active_instances
            if str((row.metadata_json or {}).get('assessment_type') or 'quiz') == assessment_type
        ), None)
        if duplicate_instance is not None:
            assessment_label = 'Final test' if assessment_type == 'final_test' else 'Quiz'
            raise ValueError(
                f'{assessment_label} đang tồn tại trên Course cho bài này '
                f'(instance={duplicate_instance.id}). Hãy vào Lịch sử Quiz và bấm Khôi phục '
                'trước khi tạo lại để tránh cộng dồn số câu.'
            )

        instance = CourseQuizInstance(
            id=str(uuid.uuid4()),
            openedx_course_id=course_id,
            subject_id=subject.id if subject else release.subject_id,
            chapter_id=chapter.id,
            subject_offering_id=course_mapping.subject_offering_id or release.subject_offering_id,
            bank_release_id=release.id,
            quiz_blueprint_id=quiz_blueprint_id,
            status='creating',
            metadata_json={
                'quiz_title': final_quiz_title,
                'unit_title': final_unit_title,
                'plan': plan,
                'validation': validation,
                'actor': actor,
                'created_from': 'final_test_release_bundle' if assessment_type == 'final_test' else 'bank_release',
                'course_chapter_mapping_id': chapter_mapping.id,
                'assessment_type': assessment_type,
                'source_release_ids': [str(item.id) for item in final_source_releases] if assessment_type == 'final_test' else [str(release.id)],
                'source_chapters': final_source_details if assessment_type == 'final_test' else [],
                'timer_config': timer_config,
                'quiz_idempotency_key': quiz_idempotency_key,
            },
        )
        self.db.add(instance)
        self.db.commit()
        quiz_result: dict = {}
        created_node_id = ''
        rollback_result: dict = {}
        rollback_error = ''
        try:
            failure_stage = 'Tạo bài kiểm tra trên CMS'
            quiz_result = await connector.create_quiz_node(
                course_id=course_id,
                parent_node_id=chapter_mapping.openedx_parent_node_id,
                quiz_title=final_quiz_title,
                unit_title=final_unit_title,
                metadata={
                    'bank_release_id': release.id,
                    'bank_release_code': release.release_code,
                    'source_release_ids': [str(item.id) for item in final_source_releases] if assessment_type == 'final_test' else [str(release.id)],
                    'source_release_codes': [str(item.release_code or '') for item in final_source_releases] if assessment_type == 'final_test' else [str(release.release_code or '')],
                    'course_quiz_instance_id': instance.id,
                    'idempotency_key': quiz_idempotency_key,
                    'quiz_idempotency_key': quiz_idempotency_key,
                    'recover_empty_legacy_partial': True,
                    'subject_code': getattr(subject, 'code', None),
                    'chapter_id': chapter.id,
                    'source': 'ai_final_test_release_bundle' if assessment_type == 'final_test' else 'ai_question_bank_release',
                    'custom_timer_enabled': timer_config['custom_timer_enabled'],
                    'timer_config': timer_config,
                    'sequential_title': final_quiz_title,
                    'unit_title': final_unit_title,
                    'grade_as': grade_as,
                    'format': grade_as,
                    'graded': True,
                    'course_quiz_policy': {
                        'scope': 'course',
                        'max_attempts': 1,
                        'showanswer': 'never',
                    },
                },
            )
            if quiz_result.get('ok') is not True:
                raise RuntimeError(f'Open edX không tạo Quiz node thành công: {quiz_result}')
            course_policy_result = quiz_result.get('course_quiz_policy_result') if isinstance(quiz_result.get('course_quiz_policy_result'), dict) else {}
            course_policy_after = course_policy_result.get('after') if isinstance(course_policy_result.get('after'), dict) else {}
            if not (
                course_policy_result.get('ok') is True
                and course_policy_result.get('verified') is True
                and course_policy_after.get('max_attempts') == 1
                and str(course_policy_after.get('showanswer') or '').lower() == 'never'
            ):
                raise RuntimeError(
                    'Open edX chưa xác minh Course Advanced Settings bắt buộc '
                    f'(Maximum Attempts = 1, Show Answer = Never): {course_policy_result}'
                )
            unit_node_id = quiz_result.get('leaf_unit_node_id') or quiz_result.get('unit_node_id')
            if not unit_node_id:
                raise RuntimeError('Open edX không trả leaf_unit_node_id sau khi tạo Quiz')
            created_nodes = quiz_result.get('created_nodes') if isinstance(quiz_result.get('created_nodes'), list) else []
            created_node_id = str(
                quiz_result.get('quiz_node_id')
                or (created_nodes[0].get('usage_key') if created_nodes else '')
                or unit_node_id
            )
            sequence_usage_key = ''
            for node in reversed(created_nodes):
                if str(node.get('block_type') or '').lower() == 'sequential':
                    sequence_usage_key = node.get('usage_key') or ''
                    break
            if not sequence_usage_key and len(created_nodes) >= 2:
                sequence_usage_key = created_nodes[-2].get('usage_key') or ''

            # Force-save timer config through the LMS unit-reset plugin after we know
            # the real sequential/unit usage keys returned by Open edX. The earlier
            # best-effort save inside the CMS connector can be skipped if CMS has not
            # loaded the unit-reset plugin yet, so do not rely on it.
            forced_timer_result = {'enabled': False, 'status': 'not_requested'}
            if timer_config['custom_timer_enabled']:
                failure_stage = 'Lưu thời gian làm bài'
                forced_timer_result = await connector.upsert_quiz_timer_config(
                    course_id=course_id,
                    sequence_usage_key=sequence_usage_key,
                    unit_usage_key=unit_node_id,
                    title=final_unit_title,
                    duration_seconds=timer_config['duration_seconds'],
                    cooldown_seconds=timer_config['cooldown_seconds'],
                    enabled=True,
                    auto_submit_on_timeout=timer_config['auto_submit_on_timeout'],
                    lock_after_timeout=timer_config['lock_after_timeout'],
                    native_timed_exam=False,
                    metadata={
                        'source': 'ai_server_force_save_after_quiz_create',
                        'course_quiz_instance_id': instance.id,
                        'bank_release_id': release.id,
                        'release_code': release.release_code,
                        'quiz_title': final_quiz_title,
                        'cms_timer_config_result': quiz_result.get('timer_config_result'),
                    },
                )
                if forced_timer_result.get('ok') is False or forced_timer_result.get('success') is False:
                    raise RuntimeError(f'Không lưu được cấu hình timer vào LMS plugin: {forced_timer_result}')

            failure_stage = 'Thêm các nhóm câu hỏi'
            insert_result = await connector.insert_problem_banks(
                course_id=course_id,
                unit_node_id=unit_node_id,
                slots=plan['slots'],
                metadata={
                    'bank_release_id': release.id,
                    'bank_release_code': release.release_code,
                    'openedx_library_key': release.openedx_library_key,
                    'source_release_ids': [str(item.id) for item in final_source_releases] if assessment_type == 'final_test' else [str(release.id)],
                    'cleanup_legacy_ai_randomized_blocks': True,
                    'source': 'final_test_release_bundle_native_itembank' if assessment_type == 'final_test' else 'bank_release_native_itembank',
                },
            )
            if insert_result.get('ok') is not True:
                raise RuntimeError(f'Open edX không tạo Problem Bank thành công: {insert_result}')
            instance.openedx_quiz_node_id = quiz_result.get('created_nodes', [{}])[0].get('usage_key') if isinstance(quiz_result.get('created_nodes'), list) and quiz_result.get('created_nodes') else unit_node_id
            instance.openedx_unit_node_id = unit_node_id
            instance.status = 'created'
            instance.metadata_json = {
                **(instance.metadata_json or {}),
                'quiz_title': final_quiz_title,
                'unit_title': final_unit_title,
                'assessment_type': assessment_type,
                'quiz_result': quiz_result,
                'problem_bank_result': insert_result,
                'timer_config': {
                    **timer_config,
                    'course_id': course_id,
                    'unit_usage_key': unit_node_id,
                    'sequence_usage_key': sequence_usage_key,
                    'unit_reset_plugin_result': quiz_result.get('timer_config_result'),
                    'force_saved_timer_result': forced_timer_result,
                },
                'created_at': datetime.utcnow().isoformat(),
            }
            self.db.commit()
            return {
                'ok': True,
                'status': 'created',
                'course_quiz_instance_id': instance.id,
                'openedx_course_id': course_id,
                'openedx_quiz_node_id': instance.openedx_quiz_node_id,
                'openedx_unit_node_id': instance.openedx_unit_node_id,
                'bank_release_id': release.id,
                'release_code': release.release_code,
                'plan': plan,
                'quiz_result': quiz_result,
                'course_quiz_policy_result': quiz_result.get('course_quiz_policy_result'),
                'problem_bank_result': insert_result,
                'timer_config': instance.metadata_json.get('timer_config') or timer_config,
                'message': 'Đã tạo Final test và native Problem Bank từ Bank Release trên Open edX.' if assessment_type == 'final_test' else 'Đã tạo Quiz và native Problem Bank từ Bank Release trên Open edX.',
                **_ui_notice('success', 'Đã tạo Final test và native Problem Bank từ Bank Release trên Open edX.' if assessment_type == 'final_test' else 'Đã tạo Quiz và native Problem Bank từ Bank Release trên Open edX.'),
            }
        except Exception as exc:
            # Compensate a partially-created Studio node. A failed timer or
            # ItemBank insert must not leave an invisible orphan Quiz behind.
            if created_node_id:
                try:
                    rollback_result = await connector.delete_quiz_node(
                        course_id=course_id,
                        node_id=created_node_id,
                        metadata={
                            'course_quiz_instance_id': instance.id,
                            'bank_release_id': release.id,
                            'rollback_source': 'create_quiz_compensation',
                        },
                    )
                except Exception as rollback_exc:
                    rollback_error = f'{type(rollback_exc).__name__}: {str(rollback_exc) or repr(rollback_exc)}'
            rollback_confirmed = bool(rollback_result.get('ok') and rollback_result.get('deleted')) if rollback_result else False
            instance.status = 'failed' if not created_node_id or rollback_confirmed else 'rollback_manual_required'
            instance.openedx_quiz_node_id = created_node_id or instance.openedx_quiz_node_id
            instance.metadata_json = {
                **(instance.metadata_json or {}),
                'failed_at': datetime.utcnow().isoformat(),
                'error': f'{type(exc).__name__}: {str(exc) or repr(exc)}',
                'error_code': bank_operation_error_code(exc),
                'error_message': bank_operation_user_message(exc),
                'failure_stage': failure_stage,
                'remote_node_created_before_failure': bool(created_node_id),
                'compensating_rollback_result': rollback_result,
                'compensating_rollback_error': rollback_error or None,
                'manual_cleanup_required': bool(created_node_id and not rollback_confirmed),
                'manual_cleanup_note': (
                    'Rollback tự động chưa được Open edX xác nhận. Hãy kiểm tra node trong Studio.'
                    if created_node_id and not rollback_confirmed
                    else 'Không còn node Quiz mồ côi theo kết quả rollback tự động.'
                ),
            }
            self.db.commit()
            raise
