from __future__ import annotations

from datetime import datetime
import re
import uuid

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.question import Question
from app.models.question_bank import (
    BankReleaseQuestion,
    CourseQuizInstance,
    QuestionBankRelease,
    QuestionBankVersion,
    QuestionSearchDocument,
    SubjectOffering,
    Subject,
    SubjectChapter,
)
from app.modules.openedx_connector.factory import get_openedx_connector
from app.services.openedx_exporter import question_to_openedx_olx
from app.services.answer_randomizer import normalize_and_shuffle_options
from app.services.question_bank.helpers import _check, _ui_notice, parse_openedx_course_id, question_lineage_root, slugify


class QuestionBankReleasePublishWorkflowService:
    """Release, publish and rollback workflow for VersionedQuestionBankService.

    This module is intentionally split from the 5k-line service without changing
    persistence semantics. Low-level helpers that still belong to the parent
    service are delegated through ``__getattr__`` so the extraction is behavior-
    preserving and easy to verify. This is a behavior-preserving split.
    """

    def __init__(self, service):
        self._service = service

    @property
    def db(self) -> Session:
        return self._service.db

    def __getattr__(self, name):
        return getattr(self._service, name)

    def release_readiness(self, *, bank_version_id: str) -> dict:
        version = self._require_bank_version(bank_version_id)
        meta = version.metadata_json or {}
        published_release_count = int(self.db.query(func.count(QuestionBankRelease.id)).filter(
            QuestionBankRelease.bank_version_id == version.id,
            QuestionBankRelease.status == 'published',
        ).scalar() or 0)
        questions = self.db.query(Question).filter(Question.bank_version_id == version.id).all()
        active = [q for q in questions if not bool(q.is_retired)]
        approved = [q for q in active if q.status in {'approved', 'published'} and not bool(q.is_duplicate)]
        pending = [q for q in active if q.status in {'pending_review', 'needs_review'}]
        draft_error = [q for q in active if q.status == 'draft_error']
        rejected = [q for q in active if q.status == 'rejected']
        unresolved = pending + draft_error
        roots: dict[str, int] = {}
        for q in approved:
            root = question_lineage_root(q)
            roots[root] = roots.get(root, 0) + 1
        duplicate_lineage_roots = [root for root, count in roots.items() if count > 1]
        diff_required = bool(meta.get('diff_required'))
        checks = [
            _check('document_change', 'fail' if diff_required else 'pass', 'Tài liệu đã thay đổi, cần bấm Kiểm tra thay đổi và đánh dấu đã xử lý trước khi chốt.' if diff_required else 'Tài liệu không còn yêu cầu kiểm tra thay đổi.', {'document_change_state': meta.get('document_change_state'), 'diff_base_bank_version_id': meta.get('diff_base_bank_version_id')}),
            _check('approved_questions', 'pass' if approved else 'fail', f'Có {len(approved)} câu đã duyệt.' if approved else 'Chưa có câu đã duyệt để chốt Release.', {'approved_count': len(approved)}),
            _check('pending_review', 'fail' if pending else 'pass', f'Còn {len(pending)} câu chờ duyệt. Phải duyệt hoặc bỏ hết trước khi chốt bộ đề.' if pending else 'Không còn câu chờ duyệt.', {'pending_review_count': len(pending)}),
            _check('draft_error', 'fail' if draft_error else 'pass', f'Còn {len(draft_error)} câu lỗi. Phải sửa hoặc bỏ hết trước khi chốt bộ đề.' if draft_error else 'Không còn câu lỗi.', {'draft_error_count': len(draft_error)}),
            _check('duplicate_lineage', 'fail' if duplicate_lineage_roots else 'pass', f'Có {len(duplicate_lineage_roots)} nhóm câu trùng gốc cần xử lý.' if duplicate_lineage_roots else 'Không phát hiện câu trùng gốc trong bộ đã duyệt.', {'duplicate_lineage_roots': duplicate_lineage_roots[:20]}),
        ]
        can_create = not any(item.get('blocking') for item in checks if item.get('status') == 'fail')
        actions: list[str] = []
        if diff_required:
            actions.append('Bấm Kiểm tra thay đổi tài liệu, xử lý gợi ý, rồi đánh dấu đã xử lý.')
        if pending:
            actions.append('Duyệt hoặc bỏ tất cả câu đang chờ duyệt.')
        if draft_error:
            actions.append('Sửa hoặc bỏ tất cả câu lỗi trước khi chốt bộ đề.')
        if not approved:
            actions.append('Tạo hoặc duyệt thêm câu hỏi trước khi chốt.')
        if duplicate_lineage_roots:
            actions.append('Loại bớt câu trùng gốc để tránh một bộ đề có nhiều câu quá giống nhau.')
        if published_release_count > 0 or self._bank_version_is_published_locked(version):
            can_create = False
            status = 'published'
            actions = ['Bài đã publish; các thao tác chỉnh sửa/tạo câu hỏi/chốt lại đã khóa. Hãy clone/tạo version mới nếu cần thay đổi.']
        else:
            status = 'ready' if can_create else 'blocked'
        return {
            'ok': True,
            'bank_version_id': version.id,
            'can_create_release': can_create,
            'status': status,
            'checks': checks,
            'stats': {
                'total_questions': len(questions),
                'active_questions': len(active),
                'approved_count': len(approved),
                'pending_review_count': len(pending),
                'draft_error_count': len(draft_error),
                'unresolved_count': len(unresolved),
                'rejected_count': len(rejected),
                'retired_count': len([q for q in questions if bool(q.is_retired)]),
                'published_release_count': published_release_count,
                'is_published': published_release_count > 0 or self._bank_version_is_published_locked(version),
                'chapter_question_limit': self._chapter_question_limit_default(),
                'chapter_total_count': self._chapter_question_count(chapter_id=version.chapter_id),
                'chapter_remaining_quota': max(0, self._chapter_question_limit_default() - self._chapter_question_count(chapter_id=version.chapter_id)),
                'difficulty_counts': {
                    'easy': len([q for q in approved if (q.difficulty or '').lower() == 'easy']),
                    'medium': len([q for q in approved if (q.difficulty or '').lower() == 'medium']),
                    'hard': len([q for q in approved if (q.difficulty or '').lower() == 'hard']),
                },
            },
            'recommended_actions': actions,
            'message': 'Bài đã publish; các thao tác chỉnh sửa đã khóa.' if status == 'published' else ('Đủ điều kiện chốt bộ đề.' if can_create else 'Chưa thể chốt bộ đề. Phải duyệt hoặc bỏ hết tất cả câu hỏi trước.'),
        }

    def list_course_quiz_instances(self, *, openedx_course_id: str | None = None, bank_release_id: str | None = None, limit: int = 100) -> list[CourseQuizInstance]:
        query = self.db.query(CourseQuizInstance)
        if openedx_course_id:
            query = query.filter(CourseQuizInstance.openedx_course_id == openedx_course_id)
        if bank_release_id:
            query = query.filter(CourseQuizInstance.bank_release_id == bank_release_id)
        return query.order_by(CourseQuizInstance.created_at.desc()).limit(max(1, min(int(limit or 100), 300))).all()

    async def rollback_course_quiz_instance(self, *, instance_id: str, mode: str = 'safe', note: str = '', actor: str | None = None) -> dict:
        instance = self.db.get(CourseQuizInstance, instance_id)
        if not instance:
            raise ValueError('Không tìm thấy lịch sử Quiz')
        meta = dict(instance.metadata_json or {})
        mode = (mode or 'safe').lower()
        delete_result: dict = {}
        openedx_deleted = False
        manual_required = True
        if mode != 'manual' and instance.openedx_unit_node_id:
            connector = get_openedx_connector()
            delete_func = getattr(connector, 'delete_quiz_node', None)
            if callable(delete_func):
                try:
                    delete_result = await delete_func(
                        course_id=instance.openedx_course_id,
                        node_id=instance.openedx_unit_node_id,
                        metadata={'course_quiz_instance_id': instance.id, 'actor': actor, 'note': note, 'rollback_source': 'ai_server_course_quiz_history'},
                    )
                    openedx_deleted = bool(delete_result.get('ok') and delete_result.get('deleted'))
                    manual_required = not openedx_deleted
                except Exception as exc:
                    delete_result = {'ok': False, 'error': f'{type(exc).__name__}: {str(exc) or repr(exc)}'}
                    manual_required = True
            else:
                delete_result = {'ok': False, 'status': 'delete_quiz_node_unavailable'}
        instance.status = 'rolled_back' if openedx_deleted else 'rollback_manual_required'
        instance.metadata_json = {
            **meta,
            'rollback': {
                'mode': mode,
                'actor': actor,
                'note': note,
                'rolled_back_at': datetime.utcnow().isoformat(),
                'openedx_deleted': openedx_deleted,
                'manual_cleanup_required': manual_required,
                'delete_result': delete_result,
            },
        }
        instance.updated_at = datetime.utcnow()
        self.db.commit()
        return {
            'ok': True,
            'course_quiz_instance_id': instance.id,
            'status': instance.status,
            'openedx_deleted': openedx_deleted,
            'manual_cleanup_required': manual_required,
            'delete_result': delete_result,
            'message': 'Đã rollback Quiz trên Open edX.' if openedx_deleted else 'Đã đánh dấu cần kiểm tra/xóa Quiz thủ công trong Studio.',
            **_ui_notice('success' if openedx_deleted else 'warning', 'Đã rollback Quiz trên Open edX.' if openedx_deleted else 'Đã đánh dấu cần kiểm tra/xóa Quiz thủ công trong Studio.'),
        }

    def _normalize_release_term_slug(self, raw_term: str | None) -> str | None:
        raw = (raw_term or '').strip()
        if not raw:
            return None
        compact = re.sub(r'[^A-Za-z0-9]+', '', raw).upper()
        match = re.search(r'\b(SU|SP|FA|SUMMER|SPRING|FALL)(?:[-_\s]*)(20)?(\d{2})\b', raw, flags=re.I)
        if match:
            prefix_raw = match.group(1).upper()
            prefix = {'SUMMER': 'SU', 'SPRING': 'SP', 'FALL': 'FA'}.get(prefix_raw, prefix_raw)
            return f'{prefix}{match.group(3)}'
        match = re.search(r'(SUMMER|SPRING|FALL)[-_\s]*(20)(\d{2})', raw, flags=re.I)
        if match:
            prefix = {'SUMMER': 'SU', 'SPRING': 'SP', 'FALL': 'FA'}[match.group(1).upper()]
            return f'{prefix}{match.group(3)}'
        if re.fullmatch(r'(SU|SP|FA)\d{2}', compact):
            return compact
        term = re.sub(r'[^A-Za-z0-9]+', '-', raw).strip('-').upper()
        return term or None

    def _release_offering_term_slug(self, *, subject: Subject, version: QuestionBankVersion) -> str | None:
        """Return the subject offering/term part used in Open edX Library keys.

        FPT rule: every release/library is term-scoped. Example:
            WEB107_SU26 / Bài 2.1 / v1.0
            -> lib:FPT:web107-SU26-b-i-2-1-v1-0

        This avoids sharing one Open edX Library across SU/SP/FA offerings.
        """
        offering = self.db.get(SubjectOffering, version.subject_offering_id) if version.subject_offering_id else None
        candidates: list[str] = []
        if offering:
            candidates.extend([offering.term or '', offering.code or '', offering.name or '', offering.version_code or ''])
        metadata = version.metadata_json or {}
        if isinstance(metadata, dict):
            candidates.extend([
                str(metadata.get('term') or ''),
                str(metadata.get('term_code') or ''),
                str(metadata.get('term_name') or ''),
                str(metadata.get('subject_offering_code') or ''),
            ])
        candidates.extend([version.title or '', version.version_code or ''])
        subject_code = (subject.code or '').strip()
        for candidate in candidates:
            raw = (candidate or '').strip()
            if not raw:
                continue
            if subject_code and raw.upper().startswith(subject_code.upper()):
                raw = raw[len(subject_code):].strip(' _-') or candidate
            term = self._normalize_release_term_slug(raw)
            if term:
                return term
        return None

    def release_library_key(self, *, subject: Subject, chapter: SubjectChapter, version: QuestionBankVersion) -> str:
        subject_slug = slugify(subject.code or subject.name, 'subject')
        term_slug = self._release_offering_term_slug(subject=subject, version=version)
        chapter_slug = slugify(self._chapter_display_name(chapter), 'chapter')
        version_slug = slugify(version.version_code.replace('.', '-'), 'v1')
        parts = [subject_slug]
        if term_slug:
            parts.append(term_slug)
        parts.extend([chapter_slug, version_slug])
        key_slug = '-'.join(parts)
        return f'lib:FPT:{key_slug}'

    def _release_library_key_needs_term_upgrade(self, *, library_key: str | None, subject: Subject, version: QuestionBankVersion) -> bool:
        if not library_key:
            return False
        term_slug = self._release_offering_term_slug(subject=subject, version=version)
        if not term_slug:
            return False
        return f'-{term_slug.lower()}-' not in str(library_key).lower()

    def _library_key_same(self, left: str | None, right: str | None) -> bool:
        return str(left or '').strip().lower() == str(right or '').strip().lower()

    def _reset_release_openedx_state_for_key_change(self, *, release: QuestionBankRelease, expected_library_key: str, reason: str) -> bool:
        """Reset stale Open edX import ids when a draft/failed release changes library key.

        This fixes the real workflow where a teacher creates Chapter `Bài 2.1`,
        publish fails because a library with that name already exists, then the
        teacher renames the chapter to `Bài 2.2`. The Release row can still hold
        the old `openedx_library_key` and component ids from the failed attempt.
        If we reuse those stale values, Open edX raises `LearningPackage matching
        query does not exist` or imports into the wrong library.
        """
        old_key = str(release.openedx_library_key or '').strip()
        new_key = str(expected_library_key or '').strip()
        if not new_key or self._library_key_same(old_key, new_key):
            return False
        if release.status == 'published' and release.published_at:
            # A truly published release may already be referenced by quizzes. Do
            # not silently move it to a new library just because the chapter was
            # renamed later. Users should create a new Release instead.
            return False

        release.openedx_library_key = new_key
        release.openedx_library_version = None
        release.status = 'ready'
        release.published_at = None
        release.published_by = None
        release.metadata_json = {
            **(release.metadata_json or {}),
            'stale_openedx_state_reset_at': datetime.utcnow().isoformat(),
            'stale_openedx_state_reset_reason': reason,
            'old_openedx_library_key': old_key or None,
            'new_openedx_library_key': new_key,
        }
        rows = self.db.query(BankReleaseQuestion).filter(BankReleaseQuestion.bank_release_id == release.id).all()
        question_ids = [row.question_id for row in rows]
        for row in rows:
            row.openedx_library_problem_id = None
        if question_ids:
            questions = self.db.query(Question).filter(Question.id.in_(question_ids)).all()
            for question in questions:
                if not question.target_library_key or self._library_key_same(question.target_library_key, old_key):
                    question.openedx_library_problem_id = None
                    question.openedx_block_id = None
                    question.target_library_key = None
                    question.imported_library_at = None
                    question.publish_error = None
                    question.publish_status = None
                    question.openedx_publish_status = None
                    question.openedx_verification_status = None
                    question.openedx_manual_action_required = False
                    if question.status == 'published':
                        question.status = 'approved'
        return True

    def _cleanup_stale_release_keys_for_chapter(self, *, chapter: SubjectChapter, reason: str) -> int:
        releases = self.db.query(QuestionBankRelease).filter(QuestionBankRelease.chapter_id == chapter.id).all()
        changed = 0
        for release in releases:
            version = self.db.get(QuestionBankVersion, release.bank_version_id)
            subject = self.db.get(Subject, release.subject_id)
            if not version or not subject:
                continue
            expected_key = self.release_library_key(subject=subject, chapter=chapter, version=version)
            if self._reset_release_openedx_state_for_key_change(release=release, expected_library_key=expected_key, reason=reason):
                changed += 1
        return changed

    def _release_questions_for_version(self, version: QuestionBankVersion) -> list[Question]:
        return self.db.query(Question).filter(
            Question.bank_version_id == version.id,
            Question.status.in_(['approved', 'published']),
        ).order_by(Question.difficulty.asc(), Question.question_family_id.asc().nullslast(), Question.created_at.asc()).all()

    def create_release(self, *, bank_version_id: str, release_code: str | None = None, title: str = '', include_approved_questions: bool = True, actor: str | None = None, force: bool = False) -> QuestionBankRelease:
        version = self.db.get(QuestionBankVersion, bank_version_id)
        if not version:
            raise ValueError('Không tìm thấy Bank Version')
        if self._bank_version_is_published_locked(version):
            raise ValueError('Bài này đã publish. Không tạo Release mới trên cùng Bank Version; hãy clone/tạo version mới nếu cần chỉnh sửa.')
        subject = self.db.get(Subject, version.subject_id)
        chapter = self.db.get(SubjectChapter, version.chapter_id)
        if not subject or not chapter:
            raise ValueError('Bank Version thiếu Subject hoặc Chapter')
        readiness = self.release_readiness(bank_version_id=version.id)
        if not force and not readiness.get('can_create_release'):
            raise ValueError('Chưa thể chốt Release: ' + readiness.get('message', 'Cần xử lý xong câu hỏi/tài liệu trước khi chốt.'))
        chapter_code = slugify(self._chapter_display_name(chapter), 'chapter')
        term_slug = self._release_offering_term_slug(subject=subject, version=version)
        code_parts = [subject.code]
        if term_slug:
            code_parts.append(term_slug)
        code_parts.extend([chapter_code, version.version_code])
        code = release_code or '-'.join(str(part) for part in code_parts if str(part or '').strip())
        library_key = self.release_library_key(subject=subject, chapter=chapter, version=version)
        questions = self._release_questions_for_version(version) if include_approved_questions else []
        counts = {'easy': 0, 'medium': 0, 'hard': 0}
        families = set()
        for question in questions:
            diff = (question.difficulty or 'easy').lower()
            counts[diff if diff in counts else 'easy'] += 1
            if question.question_family_id:
                families.add(question.question_family_id)
        release = QuestionBankRelease(
            id=str(uuid.uuid4()),
            bank_version_id=version.id,
            subject_id=version.subject_id,
            chapter_id=version.chapter_id,
            subject_offering_id=version.subject_offering_id,
            release_code=code,
            title=title or f"{subject.code}{f' - {term_slug}' if term_slug else ''} - {self._chapter_display_name(chapter)} - {version.version_code}",
            # v25.9.15.1: create is a draft/ready metadata step. It is only
            # marked published after Open edX import verifies.
            status='ready' if questions else 'draft',
            approved_question_count=len(questions),
            easy_count=counts['easy'],
            medium_count=counts['medium'],
            hard_count=counts['hard'],
            family_count=len(families),
            openedx_library_key=library_key,
            published_at=None,
            published_by=None,
            metadata_json={
                'one_bank_release_one_openedx_library': True,
                'term_scoped_library': True,
                'shared_across_terms': False,
                'shared_across_courses': False,
                'term_slug': term_slug,
                'publish_wiring': 'pending_openedx_import',
            },
        )
        self.db.add(release)
        self.db.flush()
        for question in questions:
            self.db.add(BankReleaseQuestion(
                id=str(uuid.uuid4()),
                bank_release_id=release.id,
                question_id=question.id,
                question_family_id=question.question_family_id,
                difficulty=question.difficulty,
                openedx_library_problem_id=None,
            ))
        self.db.commit()
        self.db.refresh(release)
        self._safe_refresh_chapter_stats(version.chapter_id)
        return release

    def cancel_failed_release(self, *, release_id: str, actor: str | None = None) -> dict:
        release = self.db.get(QuestionBankRelease, release_id)
        if not release:
            raise ValueError('Không tìm thấy Bank Release')
        if release.status == 'published' or release.published_at:
            raise ValueError('Không thể hủy Release đã published. Hãy tạo Release mới nếu cần đổi tên/chỉnh nội dung.')
        if release.status in {'deprecated', 'archived'}:
            raise ValueError(f'Release đang ở trạng thái {release.status}, không hủy bằng thao tác này.')
        rows = self.db.query(BankReleaseQuestion).filter(BankReleaseQuestion.bank_release_id == release.id).all()
        question_ids = [row.question_id for row in rows]
        old_key = release.openedx_library_key
        for row in rows:
            self.db.delete(row)
        if question_ids:
            questions = self.db.query(Question).filter(Question.id.in_(question_ids)).all()
            for question in questions:
                if not question.target_library_key or self._library_key_same(question.target_library_key, old_key):
                    question.openedx_library_problem_id = None
                    question.openedx_block_id = None
                    question.target_library_key = None
                    question.publish_error = None
                    question.publish_status = None
                    question.openedx_publish_status = None
                    if question.status == 'published':
                        question.status = 'approved'
        self.db.delete(release)
        self.db.commit()
        self._safe_refresh_chapter_stats(release.chapter_id)
        return {'ok': True, 'deleted': True, 'entity_type': 'bank_release', 'entity_id': release_id, 'message': 'Đã hủy Release lỗi/chưa publish'}

    def release_publish_audit(self, *, release_id: str) -> dict:
        """Read-only release publish/rollback QA for production operators.

        This report intentionally uses only AI Server materialized state. It
        does not call Open edX, does not mutate Release/Question rows, and does
        not enqueue publish or rollback jobs. The goal is to make the Bank
        Release state explicit before an operator presses “Đưa lên CMS” or
        rolls back quiz instances.
        """
        release = self.db.get(QuestionBankRelease, release_id)
        checks: list[dict] = []
        next_actions: list[str] = []
        if not release:
            return {
                'ok': False,
                'audit_status': 'BLOCKED',
                'release_id': release_id,
                'message': 'Không tìm thấy Bank Release.',
                'checks': [_check('release_exists', 'fail', 'Không tìm thấy Bank Release.')],
                'counts': {},
                'next_actions': ['Kiểm tra lại release_id hoặc mở lại trang Bài học rồi tải lại dữ liệu.'],
                'read_only': True,
                'mutation_performed': False,
            }

        version = self.db.get(QuestionBankVersion, release.bank_version_id)
        subject = self.db.get(Subject, release.subject_id)
        chapter = self.db.get(SubjectChapter, release.chapter_id)
        expected_library_key = None
        if version and subject and chapter:
            expected_library_key = self.release_library_key(subject=subject, chapter=chapter, version=version)
            checks.append(_check('hierarchy_resolved', 'pass', 'Release có đủ Bank Version, Môn và Bài học.', blocking=False))
        else:
            checks.append(_check('hierarchy_resolved', 'fail', 'Release thiếu Bank Version, Môn hoặc Bài học. Không publish/rollback tự động.'))
            next_actions.append('Kiểm tra dữ liệu Bank Version/Môn/Bài học trước khi thao tác Release.')

        rows = self.db.query(BankReleaseQuestion).filter(BankReleaseQuestion.bank_release_id == release.id).all()
        row_question_ids = [row.question_id for row in rows]
        questions_by_id = {
            q.id: q for q in self.db.query(Question).filter(Question.id.in_(row_question_ids)).all()
        } if row_question_ids else {}
        missing_question_rows = [qid for qid in row_question_ids if qid not in questions_by_id]
        component_rows = [row for row in rows if row.openedx_library_problem_id]
        question_components = [q for q in questions_by_id.values() if q.openedx_library_problem_id]
        target_library_mismatch = [
            q.id for q in questions_by_id.values()
            if q.target_library_key and release.openedx_library_key and not self._library_key_same(q.target_library_key, release.openedx_library_key)
        ]
        unpublished_questions = [
            q.id for q in questions_by_id.values()
            if release.status == 'published' and q.status != 'published'
        ]
        duplicate_problem_ids = []
        seen_problem_ids: set[str] = set()
        for row in component_rows:
            pid = str(row.openedx_library_problem_id or '').strip()
            if not pid:
                continue
            if pid in seen_problem_ids:
                duplicate_problem_ids.append(pid)
            seen_problem_ids.add(pid)

        if rows:
            checks.append(_check('release_has_questions', 'pass', f'Release có {len(rows)} câu trong snapshot chốt.', {'release_question_count': len(rows)}, blocking=False))
        else:
            checks.append(_check('release_has_questions', 'fail', 'Release chưa có câu hỏi. Không thể đưa lên CMS.'))
            next_actions.append('Chốt lại bộ đề sau khi duyệt câu hỏi đạt yêu cầu.')

        if missing_question_rows:
            checks.append(_check('release_question_integrity', 'fail', f'Có {len(missing_question_rows)} dòng release trỏ tới câu hỏi không còn tồn tại.', {'sample_question_ids': missing_question_rows[:10]}))
            next_actions.append('Hủy Release lỗi/chưa publish rồi chốt lại bộ đề để tái tạo snapshot câu hỏi sạch.')
        else:
            checks.append(_check('release_question_integrity', 'pass', 'Các dòng release đều trỏ tới câu hỏi còn tồn tại.', blocking=False))

        if expected_library_key:
            if release.openedx_library_key:
                if self._library_key_same(release.openedx_library_key, expected_library_key):
                    checks.append(_check('library_key_matches_rule', 'pass', 'Library key khớp quy tắc Môn/Kỳ/Bài/Version.', {'library_key': release.openedx_library_key}, blocking=False))
                else:
                    checks.append(_check('library_key_matches_rule', 'warn' if release.status != 'published' else 'fail', 'Library key hiện tại khác key kỳ vọng. Nếu đã đổi tên Bài hoặc Version, cần reimport có kiểm soát.', {'current': release.openedx_library_key, 'expected': expected_library_key}, blocking=release.status == 'published'))
                    next_actions.append('Nếu release chưa publish, publish lại sẽ chuẩn hóa key; nếu đã publish, tạo Release mới thay vì ghi đè key cũ.')
            else:
                checks.append(_check('library_key_present', 'warn', 'Release chưa có Library key; hệ thống sẽ tạo theo quy tắc khi publish.', {'expected': expected_library_key}, blocking=False))
        elif not release.openedx_library_key:
            checks.append(_check('library_key_present', 'fail', 'Không xác định được Library key vì thiếu hierarchy Release.'))

        if release.status == 'published':
            if release.published_at and release.openedx_library_key:
                checks.append(_check('release_published_state', 'pass', 'Release đang ở trạng thái đã đưa lên CMS và có thời điểm publish.', blocking=False))
            else:
                checks.append(_check('release_published_state', 'fail', 'Release status là published nhưng thiếu published_at hoặc Library key.'))
                next_actions.append('Rà soát metadata release; nếu là dữ liệu lỗi UAT, hủy/tạo lại release hoặc reimport có kiểm soát.')
            if len(component_rows) == len(rows) and rows:
                checks.append(_check('release_components_complete', 'pass', 'Tất cả câu trong Release đã có component id CMS/Library.', {'component_count': len(component_rows)}, blocking=False))
            else:
                checks.append(_check('release_components_complete', 'fail', f'Release đã publish nhưng chỉ có {len(component_rows)}/{len(rows)} câu có component id CMS/Library.', {'component_count': len(component_rows), 'release_question_count': len(rows)}))
                next_actions.append('Chạy publish lại với force_reimport nếu đây là UAT hoặc tạo Release mới nếu production thật cần bảo toàn lịch sử.')
        elif release.status in {'publish_failed', 'publish_in_progress'}:
            checks.append(_check('release_published_state', 'fail', f'Release đang ở trạng thái {release.status}; cần xử lý trước khi tạo Quiz/Final test.', {'status': release.status}))
            next_actions.append('Mở lịch sử tác vụ nền để xem lỗi publish, sau đó hủy Release lỗi/chưa publish hoặc publish lại khi đã sửa nguyên nhân.')
        elif release.status in {'ready', 'draft'}:
            checks.append(_check('release_published_state', 'warn', 'Release đã chốt nhưng chưa đưa lên CMS.', {'status': release.status}, blocking=False))
            next_actions.append('Bấm “Đưa lên CMS” sau khi các check còn lại không còn blocker.')
        else:
            checks.append(_check('release_published_state', 'warn', f'Release đang ở trạng thái {release.status}; cần kiểm tra trước khi thao tác.', {'status': release.status}, blocking=False))

        if duplicate_problem_ids:
            checks.append(_check('duplicate_library_problem_ids', 'fail', 'Có component id bị trùng trong cùng Release.', {'sample_problem_ids': duplicate_problem_ids[:10]}))
            next_actions.append('Không tạo Quiz/Final test từ Release này cho tới khi đã reimport hoặc tạo Release mới sạch.')
        else:
            checks.append(_check('duplicate_library_problem_ids', 'pass', 'Không phát hiện component id trùng trong cùng Release.', blocking=False))

        if target_library_mismatch:
            checks.append(_check('question_library_mismatch', 'warn', f'Có {len(target_library_mismatch)} câu có target_library_key khác Release hiện tại.', {'sample_question_ids': target_library_mismatch[:10]}, blocking=False))
            next_actions.append('Rà lại câu hỏi carry-over/reimport; nếu cần, chốt Release mới từ Bank Version sạch.')
        if unpublished_questions:
            checks.append(_check('question_status_after_publish', 'warn', f'Có {len(unpublished_questions)} câu trong Release chưa mang status published dù Release đã publish.', {'sample_question_ids': unpublished_questions[:10]}, blocking=False))

        quiz_instances = self.db.query(CourseQuizInstance).filter(CourseQuizInstance.bank_release_id == release.id).order_by(CourseQuizInstance.created_at.desc()).limit(100).all()
        active_quiz_instances = [item for item in quiz_instances if item.status not in {'rolled_back', 'rollback_manual_required', 'failed'}]
        rollback_manual_count = len([item for item in quiz_instances if item.status == 'rollback_manual_required'])
        failed_quiz_count = len([item for item in quiz_instances if item.status == 'failed'])
        if active_quiz_instances:
            checks.append(_check('course_quiz_instances_present', 'warn', f'Release đã có {len(active_quiz_instances)} Quiz/Final test instance đang hiệu lực. Rollback cần xử lý theo từng instance.', {'active_instance_count': len(active_quiz_instances)}, blocking=False))
            next_actions.append('Trước khi publish lại release đã dùng để tạo Quiz/Final test, xem lịch sử CourseQuizInstance và rollback instance sai nếu cần.')
        else:
            checks.append(_check('course_quiz_instances_present', 'pass', 'Chưa có Quiz/Final test instance hiệu lực từ Release này hoặc đã rollback.', blocking=False))
        if rollback_manual_count:
            checks.append(_check('rollback_manual_required', 'warn', f'Có {rollback_manual_count} rollback cần dọn thủ công trong Studio.', {'manual_required_count': rollback_manual_count}, blocking=False))
        if failed_quiz_count:
            checks.append(_check('failed_quiz_instances', 'warn', f'Có {failed_quiz_count} lần tạo Quiz/Final test lỗi cần kiểm tra.', {'failed_count': failed_quiz_count}, blocking=False))

        blockers = [check for check in checks if check.get('blocking')]
        warnings = [check for check in checks if check.get('status') == 'warn' and not check.get('blocking')]
        if blockers:
            audit_status = 'BLOCKED'
            message = f'Có {len(blockers)} blocker trước khi publish/tạo Quiz từ Release.'
        elif release.status == 'published' and len(component_rows) == len(rows) and rows:
            audit_status = 'PUBLISHED_VERIFIED'
            message = 'Release đã publish và component id đã đủ theo dữ liệu AI Server.'
        elif warnings:
            audit_status = 'READY_WITH_WARNINGS'
            message = 'Release có thể thao tác có kiểm soát, nhưng còn cảnh báo cần đọc trước.'
        else:
            audit_status = 'READY_TO_PUBLISH'
            message = 'Release sẵn sàng để đưa lên CMS theo dữ liệu AI Server.'
        if not next_actions:
            next_actions = ['Không cần xử lý thêm trong AI Server. Có thể tiếp tục bước vận hành phù hợp.']
        return {
            'ok': not bool(blockers),
            'audit_status': audit_status,
            'release_id': release.id,
            'release_code': release.release_code,
            'release_status': release.status,
            'bank_version_id': release.bank_version_id,
            'chapter_id': release.chapter_id,
            'subject_id': release.subject_id,
            'openedx_library_key': release.openedx_library_key,
            'expected_openedx_library_key': expected_library_key,
            'published_at': release.published_at.isoformat() if release.published_at else None,
            'message': message,
            'counts': {
                'release_question_count': len(rows),
                'release_approved_question_count': int(release.approved_question_count or 0),
                'component_count': len(component_rows),
                'question_component_count': len(question_components),
                'missing_question_row_count': len(missing_question_rows),
                'target_library_mismatch_count': len(target_library_mismatch),
                'unpublished_question_count': len(unpublished_questions),
                'course_quiz_instance_count': len(quiz_instances),
                'active_course_quiz_instance_count': len(active_quiz_instances),
                'rollback_manual_required_count': rollback_manual_count,
                'failed_course_quiz_instance_count': failed_quiz_count,
            },
            'checks': checks,
            'blockers': blockers,
            'warnings': warnings,
            'next_actions': list(dict.fromkeys(next_actions))[:10],
            'quiz_instances': [
                {
                    'id': item.id,
                    'openedx_course_id': item.openedx_course_id,
                    'status': item.status,
                    'openedx_unit_node_id': item.openedx_unit_node_id,
                    'openedx_quiz_node_id': item.openedx_quiz_node_id,
                    'created_at': item.created_at.isoformat() if item.created_at else None,
                    'updated_at': item.updated_at.isoformat() if item.updated_at else None,
                }
                for item in quiz_instances[:20]
            ],
            'read_only': True,
            'mutation_performed': False,
            'raw_tracking_log_scanned': False,
        }

    def _release_publish_course_id(self, release: QuestionBankRelease, subject: Subject, course_id_for_org: str | None = None) -> str:
        if course_id_for_org and parse_openedx_course_id(course_id_for_org).get('ok'):
            return course_id_for_org.strip()
        # The connector endpoint needs a course-shaped id primarily to resolve
        # the org. This synthetic id is intentionally marked BANK so it cannot
        # be confused with a real semester run in audit logs.
        return f'course-v1:FPT+{subject.code}+BANK'

    async def publish_release_to_openedx(self, *, release_id: str, actor: str | None = None, course_id_for_org: str | None = None, force_reimport: bool = False) -> dict:
        if settings.use_mock_openedx:
            raise ValueError('USE_MOCK_OPENEDX=true: không publish Bank Release bằng mock connector.')
        release = self.db.get(QuestionBankRelease, release_id)
        if not release:
            raise ValueError('Không tìm thấy Bank Release')
        version = self.db.get(QuestionBankVersion, release.bank_version_id)
        subject = self.db.get(Subject, release.subject_id)
        chapter = self.db.get(SubjectChapter, release.chapter_id)
        if not version or not subject or not chapter:
            raise ValueError('Release thiếu Bank Version/Subject/Chapter')
        if release.status in {'deprecated', 'archived'}:
            raise ValueError(f'Release đang ở trạng thái {release.status}, không publish lại.')

        questions = self._release_questions_for_version(version)
        if not questions:
            raise ValueError('Bank Version chưa có câu hỏi approved/published để publish release.')
        existing_items = {
            item.question_id: item
            for item in self.db.query(BankReleaseQuestion).filter(BankReleaseQuestion.bank_release_id == release.id).all()
        }
        for question in questions:
            if question.id not in existing_items:
                item = BankReleaseQuestion(
                    id=str(uuid.uuid4()),
                    bank_release_id=release.id,
                    question_id=question.id,
                    question_family_id=question.question_family_id,
                    difficulty=question.difficulty,
                    openedx_library_problem_id=None,
                )
                self.db.add(item)
                existing_items[question.id] = item
        self.db.flush()

        course_id = self._release_publish_course_id(release, subject, course_id_for_org)
        connector = get_openedx_connector()
        expected_library_key = self.release_library_key(subject=subject, chapter=chapter, version=version)
        previous_library_key = release.openedx_library_key
        if not release.openedx_library_key:
            release.openedx_library_key = expected_library_key
        elif not self._library_key_same(release.openedx_library_key, expected_library_key):
            if release.status == 'published' and release.published_at and not force_reimport:
                raise ValueError(
                    'Release này đã published bằng Library key cũ. Nếu đã đổi tên Bài/Chapter, hãy tạo Release mới thay vì ghi đè Release đã published.'
                )
            self._reset_release_openedx_state_for_key_change(
                release=release,
                expected_library_key=expected_library_key,
                reason='publish_expected_library_key_changed_after_rename_or_failed_publish',
            )
        elif self._release_library_key_needs_term_upgrade(library_key=release.openedx_library_key, subject=subject, version=version):
            self._reset_release_openedx_state_for_key_change(
                release=release,
                expected_library_key=expected_library_key,
                reason='publish_library_key_term_upgrade',
            )
        library_key = release.openedx_library_key
        library_key_changed = bool(previous_library_key and not self._library_key_same(previous_library_key, library_key))
        release.status = 'publish_in_progress'
        release.metadata_json = {
            **(release.metadata_json or {}),
            'publish_started_at': datetime.utcnow().isoformat(),
            'publish_course_id_for_org': course_id,
            'expected_openedx_library_key': expected_library_key,
            'previous_openedx_library_key': previous_library_key if previous_library_key != release.openedx_library_key else None,
            'library_key_rule': 'subject-term-chapter-release-version',
        }
        self.db.commit()

        term_slug = self._release_offering_term_slug(subject=subject, version=version)
        metadata_base = {
            'library_key': library_key,
            'library_org': 'FPT',
            'org': 'FPT',
            'term_slug': term_slug,
            'term_scoped_library': True,
            'shared_across_terms': False,
            'shared_across_courses': False,
            'subject_id': subject.id,
            'subject_code': subject.code,
            'subject_name': subject.name,
            'chapter_id': chapter.id,
            'chapter_no': chapter.chapter_no,
            'chapter_title': chapter.title,
            'bank_version_id': version.id,
            'bank_version_code': version.version_code,
            'bank_release_id': release.id,
            'bank_release_code': release.release_code,
            'architecture': 'versioned_question_bank_first',
            'one_bank_release_one_openedx_library': True,
            'tag_names': [
                'ai-learning-check',
                'generated',
                f'subject:{subject.code}',
                *( [f'term:{term_slug}'] if term_slug else [] ),
                f'chapter:{self._chapter_display_name(chapter)}',
                f'bank-release:{release.release_code}',
            ],
        }
        imported_now: list[dict] = []
        errors: list[dict] = []
        try:
            library_result = await connector.ensure_problem_library(
                course_id=course_id,
                chapter_node_id=f'bank-release:{release.id}',
                display_name=release.title or f'{subject.code} - {self._chapter_display_name(chapter)} - {version.version_code}',
                metadata=metadata_base,
            )
            if library_result.get('stub') is True or str(library_result.get('status', '')).startswith('local_stub'):
                raise RuntimeError('Open edX connector trả về stub khi ensure library. Không đánh dấu published.')
            actual_library_key = str(library_result.get('library_key') or library_result.get('openedx_library_id') or library_key).strip()
            if actual_library_key and actual_library_key != library_key:
                release.openedx_library_key = actual_library_key
                library_key = actual_library_key
                metadata_base = {
                    **metadata_base,
                    'library_key': library_key,
                    'requested_library_key': expected_library_key,
                    'actual_openedx_library_key': library_key,
                }
                release.metadata_json = {
                    **(release.metadata_json or {}),
                    'actual_openedx_library_key': library_key,
                    'requested_openedx_library_key': expected_library_key,
                    'library_key_canonicalized_by_connector': True,
                }
                self.db.flush()
            for question in questions:
                item = existing_items[question.id]
                if item.openedx_library_problem_id and not force_reimport and not library_key_changed:
                    continue
                olx = question_to_openedx_olx(question)
                family_tag = question.question_family_id or 'unknown-family'
                diff = (question.difficulty or 'easy').upper()
                tag_names = [
                    *metadata_base['tag_names'],
                    f'difficulty:{diff}',
                    f'family:{family_tag}',
                ]
                metadata = {
                    **metadata_base,
                    'question_id': question.id,
                    'question_family_id': question.question_family_id,
                    'difficulty': question.difficulty,
                    'tag_names': tag_names,
                }
                try:
                    result = await connector.import_problem_to_library(
                        course_id=course_id,
                        library_key=library_key,
                        olx=olx,
                        display_name=(question.question_text or 'AI Question')[:180],
                        metadata=metadata,
                    )
                except Exception as import_exc:
                    text = str(import_exc)
                    if 'LearningPackage matching query does not exist' not in text and 'openedx_library_import_failed' not in text:
                        raise
                    # The library key in DB may be stale/case-mismatched after a
                    # previous failed publish. Re-ensure the current expected
                    # library and retry once with the canonical key returned by
                    # the connector.
                    retry_library = await connector.ensure_problem_library(
                        course_id=course_id,
                        chapter_node_id=f'bank-release:{release.id}',
                        display_name=release.title or f'{subject.code} - {self._chapter_display_name(chapter)} - {version.version_code}',
                        metadata={**metadata_base, 'retry_after_learningpackage_missing': True},
                    )
                    retry_key = str(retry_library.get('library_key') or retry_library.get('openedx_library_id') or expected_library_key).strip()
                    if retry_key and not self._library_key_same(retry_key, library_key):
                        release.openedx_library_key = retry_key
                        library_key = retry_key
                        metadata_base = {**metadata_base, 'library_key': library_key, 'actual_openedx_library_key': library_key}
                        metadata = {**metadata, 'library_key': library_key, 'actual_openedx_library_key': library_key}
                        self.db.flush()
                    result = await connector.import_problem_to_library(
                        course_id=course_id,
                        library_key=library_key,
                        olx=olx,
                        display_name=(question.question_text or 'AI Question')[:180],
                        metadata=metadata,
                    )
                if result.get('stub') is True or str(result.get('status', '')).startswith('local_stub'):
                    raise RuntimeError('Open edX connector trả về stub khi import problem. Không đánh dấu published.')
                problem_id = result.get('openedx_library_problem_id') or result.get('library_problem_id') or result.get('problem_id') or result.get('block_id')
                if not problem_id:
                    raise RuntimeError(f'Connector không trả problem id cho question {question.id}')
                verify = None
                try:
                    verify = await connector.verify_library_problem(course_id, library_key, problem_id, metadata=metadata)
                except Exception as verify_exc:  # keep import but mark manual check
                    verify = {'verified': False, 'manual_check_required': True, 'error': str(verify_exc)}
                item.openedx_library_problem_id = problem_id
                item.difficulty = question.difficulty
                item.question_family_id = question.question_family_id
                question.openedx_library_problem_id = problem_id
                question.target_library_key = library_key
                question.status = 'published'
                question.published_at = datetime.utcnow()
                question.published_by = actor
                imported_now.append({'question_id': question.id, 'problem_id': problem_id, 'verify': verify})
                self.db.flush()
            counts = {'easy': 0, 'medium': 0, 'hard': 0}
            families = set()
            for question in questions:
                diff = (question.difficulty or 'easy').lower()
                counts[diff if diff in counts else 'easy'] += 1
                if question.question_family_id:
                    families.add(question.question_family_id)
            release.status = 'published'
            release.approved_question_count = len(questions)
            release.easy_count = counts['easy']
            release.medium_count = counts['medium']
            release.hard_count = counts['hard']
            release.family_count = len(families)
            release.published_at = datetime.utcnow()
            release.published_by = actor
            release.metadata_json = {
                **(release.metadata_json or {}),
                'publish_completed_at': datetime.utcnow().isoformat(),
                'library_result': library_result,
                'published_question_count': len(questions),
                'imported_now_count': len(imported_now),
                'publish_wiring': 'openedx_library_verified_or_imported',
                'library_key_changed': library_key_changed,
            }
            version.status = 'published'
            version.published_at = release.published_at
            self.db.commit()
            self.db.refresh(release)
            self._safe_refresh_chapter_stats(version.chapter_id)
            return {
                'ok': True,
                'release_id': release.id,
                'release_code': release.release_code,
                'status': release.status,
                'openedx_library_key': release.openedx_library_key,
                'question_count': len(questions),
                'imported_now_count': len(imported_now),
                'skipped_existing_count': len(questions) - len(imported_now),
                'library_result': library_result,
                'imported': imported_now,
                'errors': [],
            }
        except Exception as exc:
            # Best-effort rollback for components imported in this failed request.
            for row in imported_now:
                try:
                    await connector.delete_library_problem(course_id, library_key, row['problem_id'], metadata={'bank_release_id': release.id, 'rollback': True})
                except Exception as delete_exc:
                    errors.append({'question_id': row.get('question_id'), 'problem_id': row.get('problem_id'), 'rollback_error': str(delete_exc)})
            release.status = 'publish_failed'
            release.metadata_json = {
                **(release.metadata_json or {}),
                'publish_failed_at': datetime.utcnow().isoformat(),
                'error': f'{type(exc).__name__}: {str(exc) or repr(exc)}',
                'rollback_errors': errors,
            }
            self.db.commit()
            self._safe_refresh_chapter_stats(version.chapter_id)
            raise RuntimeError(release.metadata_json['error']) from exc

