from __future__ import annotations

from datetime import datetime
from difflib import SequenceMatcher
import re
import uuid

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.course import CourseSyncState
from app.models.question import Question
from app.models.question_bank import (
    BankReleaseQuestion,
    CourseQuizInstance,
    Department,
    EdxCourseChapterMapping,
    EdxCourseMapping,
    QuestionBankRelease,
    Subject,
    SubjectChapter,
    SubjectOffering,
)
from app.modules.openedx_connector.factory import get_openedx_connector
from app.services.question_family import normalize_difficulty
from app.services.question_bank.helpers import (
    _check,
    _ui_notice,
    extract_chapter_number,
    normalize_code,
    normalize_title_match,
    parse_openedx_course_id,
    title_similarity,
)


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
        return bool(total and ready == total), total, ready

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

    async def _load_openedx_sections_for_quiz(self, course_id: str) -> tuple[list[dict], list[str]]:
        warnings: list[str] = []
        blocks: list[dict] = []
        try:
            blocks = await get_openedx_connector().get_course_blocks(course_id)
        except Exception as exc:
            warnings.append(f'Không đọc được cây course trực tiếp từ Open edX: {exc}. Thử dùng dữ liệu sync cũ trong AI Server.')
        if not blocks:
            rows = self.db.query(CourseSyncState).filter(CourseSyncState.course_id == course_id).all()
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
        sections = [block for block in blocks if str(block.get('type') or '').lower() == 'chapter']
        if not sections:
            sections = [block for block in blocks if str(block.get('type') or '').lower() == 'sequential']
            if sections:
                warnings.append('Course chưa trả về Section/chapter rõ ràng; hệ thống tạm dùng Subsection để map. Nên sync lại course nếu tên chưa đúng.')
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
        course_id = (openedx_course_id or '').strip()
        parsed = parse_openedx_course_id(course_id)
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
        sections, section_warnings = await self._load_openedx_sections_for_quiz(course_id)
        warnings.extend(section_warnings)
        if not sections:
            blocking_errors.append('Không đọc được Section từ Open edX course. Hãy kiểm tra connector/sync course trước.')
        used_sections: set[str] = set()
        mappings: list[dict] = []
        release_by_chapter = {item['chapter_id']: item for item in release_status['details']}
        chapters = self.db.query(SubjectChapter).filter(
            SubjectChapter.subject_offering_id == offering.id,
            SubjectChapter.status == 'active',
        ).order_by(SubjectChapter.sort_order.asc(), SubjectChapter.chapter_no.asc()).all()
        for chapter in chapters:
            chapter_title = self._chapter_display_name(chapter)
            action = plan_by_chapter.get(chapter.id) or self._quiz_action_for_chapter_title(chapter_title)
            requires_release = self._quiz_action_requires_release(action)
            section, score, reason = self._match_chapter_to_section(chapter, sections, used_sections)
            if section:
                used_sections.add(str(section.get('block_id') or ''))
            release_info = release_by_chapter.get(chapter.id) or {}
            ready = bool(requires_release and section and release_info.get('ready'))
            production_status = self._quiz_production_status_for_mapping(action=action, section=section, release_info=release_info)
            if requires_release and not section:
                blocking_errors.append(f'{chapter_title} đang chọn {self._quiz_action_label(action)} nhưng chưa tìm thấy Section cùng tên trong course.')
            if requires_release and not release_info.get('ready'):
                blocking_errors.append(f'{chapter_title} đang chọn {self._quiz_action_label(action)} nhưng chưa có Release published đủ component.')
            if not requires_release and not section:
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
                'course_chapter_mapping_id': None,
                'recommended_quiz_title': 'Final test' if action == 'final_test' else f'Quiz {self._chapter_quiz_suffix(chapter)}'.strip(),
                'recommended_unit_title': 'Final test' if action == 'final_test' else 'Quiz',
            })
        existing = self.db.query(EdxCourseMapping).filter(EdxCourseMapping.openedx_course_id == course_id).first()
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
            },
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
        mapping = self.db.query(EdxCourseMapping).filter(EdxCourseMapping.openedx_course_id == course_id).first()
        if mapping:
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
                saved_mappings.append({**item, 'course_chapter_mapping_id': None, 'mapping_status': 'skipped_no_quiz'})
                continue
            if not item.get('ready'):
                raise ValueError(f'{item.get("chapter_title") or "Bài"} chưa sẵn sàng để tạo Quiz/Final test.')
            existing = self.db.query(EdxCourseChapterMapping).filter(
                EdxCourseChapterMapping.course_mapping_id == mapping.id,
                EdxCourseChapterMapping.subject_chapter_id == item['chapter_id'],
            ).first()
            validation = self._chapter_mapping_validation(
                course_mapping_id=mapping.id,
                subject_chapter_id=item['chapter_id'],
                bank_release_id=item['release_id'],
                openedx_parent_node_id=item['openedx_section_id'],
                openedx_node_title=item.get('openedx_section_title'),
            )
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
        rows, questions = self._published_release_question_rows(release)
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

        # FPT slot planner v3:
        # - learner-visible question count is exact per difficulty (one ItemBank slot = one visible question)
        # - a Library component/question is assigned to exactly one slot
        # - a concept/family stays in exactly one slot when there are enough concepts
        # - when concepts/families are more than slots, whole concepts are bin-packed so slot candidate counts are balanced
        # - when concepts/families are fewer than slots, the planner splits large concepts only as a last-resort soft mode
        #   to still satisfy the requested EASY/MEDIUM/HARD counts.
        grouped_rows: dict[str, list[BankReleaseQuestion]] = {'easy': [], 'medium': [], 'hard': []}
        for row in rows:
            question = questions[row.question_id]
            diff = normalize_difficulty(row.difficulty or question.difficulty)
            grouped_rows.setdefault(diff, []).append(row)

        def concept_key_for(row: BankReleaseQuestion) -> str:
            question = questions[row.question_id]
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

        def build_balanced_slots_for_difficulty(diff: str, diff_rows: list[BankReleaseQuestion], target_count: int) -> tuple[list[dict], dict, list[str]]:
            diff_warnings: list[str] = []
            available_count = len(diff_rows)
            if target_count <= 0:
                return [], {
                    'difficulty': diff.upper(),
                    'target_questions': 0,
                    'available_questions': available_count,
                    'selected_slots': 0,
                    'status': 'not_requested',
                }, []
            if available_count <= 0:
                raise ValueError(f'Release chưa có câu {diff.upper()} để tạo Problem Bank {diff.upper()}.')
            if available_count < target_count:
                raise ValueError(
                    f'Release không đủ câu {diff.upper()}: cần {target_count}, hiện có {available_count}. '
                    'Hãy tạo/publish thêm câu hoặc giảm tỷ lệ/số câu Quiz.'
                )

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
                    f'{diff.upper()} chỉ có {len(groups)} concept/family cho {target_count} slot; '
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
                    'rule': f'random 1/{max(len(question_ids), 1)} {diff.upper()} variants',
                    'warning': 'Có concept bị tách do thiếu concept/family.' if split_family_keys else '',
                })

            coverage = {
                'difficulty': diff.upper(),
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
        slots: list[dict] = []
        coverage: list[dict] = []
        warnings: list[str] = []
        assigned_question_ids: set[str] = set()
        assigned_components: set[str] = set()
        slot_no = 1

        for diff in ('easy', 'medium', 'hard'):
            target_count = int(requested.get(diff) or 0)
            diff_slots, diff_coverage, diff_warnings = build_balanced_slots_for_difficulty(diff, list(grouped_rows.get(diff) or []), target_count)
            warnings.extend(diff_warnings)
            for slot in diff_slots:
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
            coverage.append(diff_coverage)
        if not slots:
            raise ValueError('Không có mức độ nào được chọn để tạo Problem Bank.')
        if sum(int(slot.get('pick_count') or 0) for slot in slots) != int(total_questions):
            warnings.append(
                f'Tổng pick_count thực tế {sum(int(slot.get("pick_count") or 0) for slot in slots)} khác yêu cầu {total_questions}; hãy kiểm tra tỷ lệ difficulty.'
            )
        plan = {
            'ok': True,
            'planner_engine': 'bank_release_export_parity_difficulty_itembank_v2',
            'uses_llm': False,
            'release_id': release.id,
            'release_code': release.release_code,
            'openedx_library_key': release.openedx_library_key,
            'requested_total_questions': int(total_questions),
            'total_questions': int(total_questions),
            'target_counts': {k.upper(): v for k, v in requested.items()},
            'effective_target_counts': {k.upper(): requested[k] for k in requested},
            'coverage': coverage,
            'slots': slots,
            'warnings': list(dict.fromkeys(warnings)),
            'assigned_question_count': len(assigned_question_ids),
            'assigned_component_count': len(assigned_components),
            'hard_guard': {'valid': True, 'summary': 'Release plan hợp lệ: EASY/MEDIUM/HARD tách riêng; không trùng question_id hoặc Open edX component giữa các bank.'},
            'message': f'Tạo kế hoạch theo chuẩn /export: {len(slots)} Problem Bank EASY/MEDIUM/HARD, learner thấy {int(total_questions)} câu.',
            **_ui_notice('success', f'Tạo kế hoạch theo chuẩn /export: {len(slots)} Problem Bank EASY/MEDIUM/HARD, learner thấy {int(total_questions)} câu.'),
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
    ) -> dict:
        release = self.db.get(QuestionBankRelease, bank_release_id)
        if not release:
            raise ValueError('Không tìm thấy Bank Release')
        return self._build_release_quiz_plan(
            release=release,
            total_questions=total_questions,
            difficulty_easy=difficulty_easy,
            difficulty_medium=difficulty_medium,
            difficulty_hard=difficulty_hard,
            max_families_per_bank=max_families_per_bank,
        )

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
        if not chapter_mapping.openedx_parent_node_id:
            raise ValueError('Chapter mapping chưa có node Open edX để đặt Quiz')
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
        plan = self._build_release_quiz_plan(
            release=release,
            total_questions=total_questions,
            difficulty_easy=difficulty_easy,
            difficulty_medium=difficulty_medium,
            difficulty_hard=difficulty_hard,
            max_families_per_bank=max_families_per_bank,
        )
        subject = self.db.get(Subject, release.subject_id)
        chapter = self.db.get(SubjectChapter, release.chapter_id)
        connector = get_openedx_connector()
        course_id = course_mapping.openedx_course_id
        assessment_type = 'final_test' if str(assessment_type or '').lower() == 'final_test' else 'quiz'
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
            'auto_submit_on_timeout': bool(custom_timer_enabled),
            'lock_after_timeout': bool(custom_timer_enabled),
            'native_timed_exam': bool(native_timed_exam),
        }
        if timer_config['native_timed_exam']:
            raise ValueError('Quiz tự luyện không dùng native Timed Exam. Hãy dùng custom timer.')
        instance = CourseQuizInstance(
            id=str(uuid.uuid4()),
            openedx_course_id=course_id,
            subject_id=release.subject_id,
            chapter_id=release.chapter_id,
            subject_offering_id=release.subject_offering_id,
            bank_release_id=release.id,
            quiz_blueprint_id=None,
            status='creating',
            metadata_json={'plan': plan, 'validation': validation, 'actor': actor, 'created_from': 'bank_release', 'assessment_type': assessment_type, 'timer_config': timer_config},
        )
        self.db.add(instance)
        self.db.commit()
        try:
            quiz_result = await connector.create_quiz_node(
                course_id=course_id,
                parent_node_id=chapter_mapping.openedx_parent_node_id,
                quiz_title=final_quiz_title,
                unit_title=final_unit_title,
                metadata={
                    'bank_release_id': release.id,
                    'bank_release_code': release.release_code,
                    'subject_code': getattr(subject, 'code', None),
                    'chapter_id': release.chapter_id,
                    'source': 'ai_question_bank_release',
                    'custom_timer_enabled': timer_config['custom_timer_enabled'],
                    'timer_config': timer_config,
                    'sequential_title': final_quiz_title,
                    'unit_title': final_unit_title,
                    'grade_as': grade_as,
                    'format': grade_as,
                    'graded': True,
                },
            )
            if quiz_result.get('ok') is not True:
                raise RuntimeError(f'Open edX không tạo Quiz node thành công: {quiz_result}')
            unit_node_id = quiz_result.get('leaf_unit_node_id') or quiz_result.get('unit_node_id')
            if not unit_node_id:
                raise RuntimeError('Open edX không trả leaf_unit_node_id sau khi tạo Quiz')
            created_nodes = quiz_result.get('created_nodes') if isinstance(quiz_result.get('created_nodes'), list) else []
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

            insert_result = await connector.insert_problem_banks(
                course_id=course_id,
                unit_node_id=unit_node_id,
                slots=plan['slots'],
                metadata={
                    'bank_release_id': release.id,
                    'bank_release_code': release.release_code,
                    'openedx_library_key': release.openedx_library_key,
                    'cleanup_legacy_ai_randomized_blocks': True,
                    'source': 'bank_release_native_itembank',
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
                'problem_bank_result': insert_result,
                'timer_config': instance.metadata_json.get('timer_config') or timer_config,
                'message': 'Đã tạo Final test và native Problem Bank từ Bank Release trên Open edX.' if assessment_type == 'final_test' else 'Đã tạo Quiz và native Problem Bank từ Bank Release trên Open edX.',
                **_ui_notice('success', 'Đã tạo Final test và native Problem Bank từ Bank Release trên Open edX.' if assessment_type == 'final_test' else 'Đã tạo Quiz và native Problem Bank từ Bank Release trên Open edX.'),
            }
        except Exception as exc:
            instance.status = 'failed'
            instance.metadata_json = {
                **(instance.metadata_json or {}),
                'failed_at': datetime.utcnow().isoformat(),
                'error': f'{type(exc).__name__}: {str(exc) or repr(exc)}',
                'manual_cleanup_note': 'Nếu Quiz node đã được tạo trước khi lỗi insert Problem Bank, hãy kiểm tra/xóa thủ công trong Studio. AI Server không báo thành công một phần.',
            }
            self.db.commit()
            raise
