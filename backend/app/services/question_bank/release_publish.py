from __future__ import annotations

from datetime import datetime
import hashlib
import re
import uuid
from typing import Any

from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.openedx_ids import normalize_openedx_course_id, openedx_course_id_candidates
from app.models.question import Question
from app.models.question_bank import (
    BankReleaseQuestion,
    CourseQuizInstance,
    QuestionBankRelease,
    QuestionBankVersion,
    SubjectOffering,
    Subject,
    SubjectChapter,
)
from app.modules.openedx_connector.factory import get_openedx_connector
from app.services.openedx_exporter import question_to_openedx_olx
from app.services.question_media import build_openedx_question_assets
from app.services.question_bank.helpers import _check, _ui_notice, question_lineage_root, slugify


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
        open_release_count = int(self.db.query(func.count(QuestionBankRelease.id)).filter(
            QuestionBankRelease.bank_version_id == version.id,
            QuestionBankRelease.status.notin_(['published', 'deprecated', 'archived']),
        ).scalar() or 0)
        questions = self.db.query(Question).filter(Question.bank_version_id == version.id).all()
        active = [q for q in questions if not bool(q.is_retired)]
        approved, auto_excluded = self._release_question_selection(version)
        pending = [q for q in active if q.status in {'pending_review', 'needs_review'}]
        draft_error = [q for q in active if q.status == 'draft_error']
        rejected = [q for q in active if q.status == 'rejected']
        known_statuses = {'approved', 'published', 'pending_review', 'needs_review', 'draft_error', 'rejected'}
        unknown_status = [q for q in active if q.status not in known_statuses]
        unresolved = pending + unknown_status
        auto_excluded_duplicates = [item for item in auto_excluded if 'duplicate' in item.get('reasons', []) or 'duplicate_lineage' in item.get('reasons', [])]
        duplicate_lineage_roots = sorted({str(item.get('lineage_root') or '') for item in auto_excluded if 'duplicate_lineage' in item.get('reasons', []) and item.get('lineage_root')})
        diff_required = bool(meta.get('diff_required'))
        checks = [
            _check('document_change', 'fail' if diff_required else 'pass', 'Tài liệu đã thay đổi, cần bấm Kiểm tra thay đổi và đánh dấu đã xử lý trước khi chốt.' if diff_required else 'Tài liệu không còn yêu cầu kiểm tra thay đổi.', {'document_change_state': meta.get('document_change_state'), 'diff_base_bank_version_id': meta.get('diff_base_bank_version_id')}),
            _check('approved_questions', 'pass' if approved else 'fail', f'Có {len(approved)} câu đã duyệt.' if approved else 'Chưa có câu đã duyệt để chốt Release.', {'approved_count': len(approved)}),
            _check('pending_review', 'fail' if pending else 'pass', f'Còn {len(pending)} câu chờ duyệt. Phải duyệt hoặc bỏ hết trước khi chốt bộ đề.' if pending else 'Không còn câu chờ duyệt.', {'pending_review_count': len(pending)}),
            _check('draft_error', 'warning' if draft_error else 'pass', f'Có {len(draft_error)} câu lỗi; hệ thống sẽ tự loại khỏi Release, không chặn chốt.' if draft_error else 'Không còn câu lỗi.', {'draft_error_count': len(draft_error), 'auto_excluded': True}, blocking=False),
            _check('legacy_question_status', 'fail' if unknown_status else 'pass', f'Có {len(unknown_status)} câu mang trạng thái legacy/không xác định. Hãy chạy migration/data repair trước khi chốt.' if unknown_status else 'Không có trạng thái câu hỏi legacy/không xác định.', {'unknown_status_count': len(unknown_status), 'sample': [{'question_id': q.id, 'status': q.status} for q in unknown_status[:10]]}),
            _check('duplicate_lineage', 'warning' if auto_excluded_duplicates else 'pass', f'Có {len(auto_excluded_duplicates)} câu trùng; hệ thống sẽ tự loại khỏi Release.' if auto_excluded_duplicates else 'Không phát hiện câu trùng trong bộ đã duyệt.', {'duplicate_lineage_roots': duplicate_lineage_roots[:20], 'auto_excluded_duplicate_count': len(auto_excluded_duplicates)}, blocking=False),
            _check('existing_open_release', 'fail' if open_release_count else 'pass', f'Đã có {open_release_count} Release chưa kết thúc trên Bank Version này. Hãy publish/retry hoặc hủy Release hiện tại thay vì tạo bản trùng.' if open_release_count else 'Không có Release draft/ready/publish_failed trùng trên Bank Version.', {'open_release_count': open_release_count}),
        ]
        can_create = not any(item.get('blocking') for item in checks if item.get('status') == 'fail')
        actions: list[str] = []
        if diff_required:
            actions.append('Bấm Kiểm tra thay đổi tài liệu, xử lý gợi ý, rồi đánh dấu đã xử lý.')
        if pending:
            actions.append('Duyệt hoặc bỏ tất cả câu đang chờ duyệt.')
        if draft_error:
            actions.append(f'{len(draft_error)} câu lỗi sẽ tự bị loại khỏi Release; có thể sửa sau nếu muốn dùng lại.')
        if unknown_status:
            actions.append('Chạy migration/data repair để chuẩn hóa trạng thái legacy trước khi chốt Release.')
        if not approved:
            actions.append('Tạo hoặc duyệt thêm câu hỏi trước khi chốt.')
        if auto_excluded_duplicates:
            actions.append(f'{len(auto_excluded_duplicates)} câu trùng sẽ tự bị loại khỏi Release.')
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
                'unknown_status_count': len(unknown_status),
                'unresolved_count': len(unresolved),
                'auto_excluded_count': len(auto_excluded) + len(draft_error),
                'auto_excluded_duplicate_count': len(auto_excluded_duplicates),
                'rejected_count': len(rejected),
                'retired_count': len([q for q in questions if bool(q.is_retired)]),
                'published_release_count': published_release_count,
                'open_release_count': open_release_count,
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
            'message': 'Bài đã publish; các thao tác chỉnh sửa đã khóa.' if status == 'published' else ('Đủ điều kiện chốt bộ đề; câu lỗi/trùng sẽ tự loại.' if can_create else 'Chưa thể chốt bộ đề. Hãy xử lý các câu còn chờ duyệt hoặc trạng thái không xác định.'),
        }

    def list_course_quiz_instances(self, *, openedx_course_id: str | None = None, bank_release_id: str | None = None, limit: int = 100) -> list[CourseQuizInstance]:
        query = self.db.query(CourseQuizInstance)
        if openedx_course_id:
            candidates = openedx_course_id_candidates(openedx_course_id)
            if not candidates:
                return []
            query = query.filter(CourseQuizInstance.openedx_course_id.in_(candidates))
        if bank_release_id:
            query = query.filter(CourseQuizInstance.bank_release_id == bank_release_id)
        return query.order_by(CourseQuizInstance.created_at.desc()).limit(max(1, min(int(limit or 100), 300))).all()

    async def _reconcile_quiz_absence(self, *, instance: CourseQuizInstance, metadata: dict) -> dict:
        """Check the live CMS tree before keeping a stale local Quiz lock.

        A connector timeout can happen after Studio has rejected or rolled back
        the create request. In that case the AI Server may have no reliable node
        locator, while the local history row still says
        ``rollback_manual_required``. Reading the draft course is safe and
        idempotent: an exact managed node or matching assessment title keeps the
        lock; a successful tree read with no match proves the local row is stale.
        """
        connector = get_openedx_connector()
        blocks = await connector.get_course_blocks(
            normalize_openedx_course_id(instance.openedx_course_id, required=True)
        )
        known_ids = {
            str(value).strip()
            for value in (instance.openedx_quiz_node_id, instance.openedx_unit_node_id)
            if str(value or '').strip()
        }
        normalized_blocks = [item for item in (blocks or []) if isinstance(item, dict)]
        live_ids = {
            str(item.get('block_id') or item.get('id') or '').strip()
            for item in normalized_blocks
        }
        if known_ids & live_ids:
            return {'verified': True, 'absent': False, 'reason': 'managed_node_still_exists', 'live_node_ids': sorted(known_ids & live_ids)}

        expected_titles = {
            str(value).strip().casefold()
            for value in (metadata.get('quiz_title'), metadata.get('unit_title'))
            if str(value or '').strip()
        }
        if not known_ids and not expected_titles:
            return {
                'verified': True,
                'absent': False,
                'reason': 'missing_managed_quiz_identity',
            }
        title_matches = [
            str(item.get('block_id') or item.get('id') or '')
            for item in normalized_blocks
            # A mapped ``chapter`` named “Final test” is the normal empty
            # Section shown in Studio. It is not the Quiz created by ACMS.
            # Quiz creation adds a sequential and a vertical beneath it.
            if str(item.get('type') or '').lower() in {'sequential', 'vertical'}
            and str(item.get('display_name') or '').strip().casefold() in expected_titles
        ]
        if title_matches:
            return {'verified': True, 'absent': False, 'reason': 'managed_assessment_title_still_exists', 'live_node_ids': title_matches}
        return {
            'verified': True,
            'absent': True,
            'reason': 'course_tree_read_success_no_managed_quiz',
            'course_block_count': len(normalized_blocks),
        }

    async def rollback_course_quiz_instance(self, *, instance_id: str, mode: str = 'safe', note: str = '', actor: str | None = None) -> dict:
        instance = self.db.get(CourseQuizInstance, instance_id)
        if not instance:
            raise ValueError('Không tìm thấy lịch sử Quiz')
        meta = dict(instance.metadata_json or {})
        mode = (mode or 'safe').lower()
        delete_result: dict = {}
        # Failed creation can have only the root locator. Deleting the leaf alone
        # also leaves an empty subsection which prevents a clean retry in Studio.
        node_id = instance.openedx_quiz_node_id or instance.openedx_unit_node_id
        compensation = meta.get('compensating_rollback_result') or {}
        openedx_deleted = instance.status == 'rolled_back' or (
            compensation.get('ok') is True and compensation.get('deleted') is True
        )
        manual_required = not openedx_deleted
        if not openedx_deleted and mode != 'manual' and node_id:
            connector = get_openedx_connector()
            delete_func = getattr(connector, 'delete_quiz_node', None)
            if callable(delete_func):
                try:
                    delete_result = await delete_func(
                        course_id=normalize_openedx_course_id(instance.openedx_course_id, required=True),
                        node_id=node_id,
                        metadata={'course_quiz_instance_id': instance.id, 'actor': actor, 'note': note, 'rollback_source': 'ai_server_course_quiz_history'},
                    )
                    openedx_deleted = delete_result.get('ok') is True and delete_result.get('deleted') is True
                    manual_required = not openedx_deleted
                except Exception as exc:
                    delete_result = {'ok': False, 'error': f'{type(exc).__name__}: {str(exc) or repr(exc)}'}
                    manual_required = True
            else:
                delete_result = {'ok': False, 'status': 'delete_quiz_node_unavailable'}
        reconciliation: dict = {}
        # Old rows can lack both node locators. If Studio is already clean, close
        # the stale local lock so the operator can create the assessment again.
        # When CMS cannot be read, retain the manual state and explain why.
        if not openedx_deleted and mode != 'manual':
            try:
                reconciliation = await self._reconcile_quiz_absence(instance=instance, metadata=meta)
                if reconciliation.get('verified') and reconciliation.get('absent'):
                    openedx_deleted = True
                    manual_required = False
                    delete_result = {
                        **delete_result,
                        'ok': True,
                        'deleted': True,
                        'already_missing': True,
                        'status': 'verified_absent_in_course_tree',
                    }
            except Exception as exc:
                reconciliation = {
                    'verified': False,
                    'absent': False,
                    'status': 'course_tree_reconciliation_unavailable',
                    'error': f'{type(exc).__name__}: {str(exc) or repr(exc)}',
                }
        instance.status = 'rolled_back' if openedx_deleted else 'rollback_manual_required'
        instance.metadata_json = {
            **meta,
            'manual_cleanup_required': manual_required,
            'rollback': {
                'mode': mode,
                'actor': actor,
                'note': note,
                'rolled_back_at': datetime.utcnow().isoformat(),
                'openedx_deleted': openedx_deleted,
                'manual_cleanup_required': manual_required,
                'delete_result': delete_result,
                'reconciliation': reconciliation,
            },
        }
        instance.updated_at = datetime.utcnow()
        self.db.commit()
        message = (
            'Đã xóa phần bài kiểm tra trên CMS. Bạn có thể tạo lại.'
            if openedx_deleted else
            'Chưa xác nhận được việc xóa bài kiểm tra trên CMS. Bấm Kiểm tra và khôi phục để thử lại; nếu vẫn lỗi, kiểm tra bài trong Studio.'
        )
        return {
            'ok': openedx_deleted,
            'course_quiz_instance_id': instance.id,
            'status': instance.status,
            'openedx_deleted': openedx_deleted,
            'manual_cleanup_required': manual_required,
            'delete_result': delete_result,
            'message': message,
            **_ui_notice('success' if openedx_deleted else 'warning', message),
        }

    @staticmethod
    def _canonical_library_org() -> str:
        raw = str(getattr(settings, 'openedx_library_org', 'FPT') or 'FPT').strip().upper()
        org = re.sub(r'[^A-Z0-9._-]+', '-', raw).strip('-_.')
        if not org:
            raise ValueError('OPENEDX_LIBRARY_ORG không hợp lệ.')
        return org[:30]

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
        metadata = version.metadata_json or {}
        explicit_candidates: list[str] = []
        inferred_candidates: list[str] = []
        if offering:
            explicit_candidates.append(offering.term or '')
            inferred_candidates.extend([offering.code or '', offering.name or ''])
        if isinstance(metadata, dict):
            explicit_candidates.extend([
                str(metadata.get('term') or ''),
                str(metadata.get('term_code') or ''),
                str(metadata.get('term_name') or ''),
            ])
            inferred_candidates.append(str(metadata.get('subject_offering_code') or ''))
        # title may contain WEB107_SU26; version_code (e.g. v1.0) is not a term.
        inferred_candidates.append(version.title or '')
        subject_code = (subject.code or '').strip()

        def clean_candidate(candidate: str) -> str:
            raw = (candidate or '').strip()
            if subject_code and raw.upper().startswith(subject_code.upper()):
                raw = raw[len(subject_code):].strip(' _-') or candidate
            return raw

        for candidate in explicit_candidates:
            raw = clean_candidate(candidate)
            if raw:
                term = self._normalize_release_term_slug(raw)
                if term:
                    return term

        term_pattern = re.compile(r'(?:\b(?:SU|SP|FA)\s*[-_ ]?\s*(?:20)?\d{2}\b|\b(?:SUMMER|SPRING|FALL)\s*[-_ ]?\s*20\d{2}\b)', re.I)
        for candidate in inferred_candidates:
            raw = clean_candidate(candidate)
            if raw and term_pattern.search(raw):
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
        return f'lib:{self._canonical_library_org()}:{key_slug}'

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

    def _release_question_selection(self, version: QuestionBankVersion) -> tuple[list[Question], list[dict]]:
        """Return clean Release membership and an audited exclusion list."""
        candidates = self.db.query(Question).filter(
            Question.bank_version_id == version.id,
            Question.status.in_(['approved', 'published']),
        ).order_by(Question.difficulty.asc(), Question.question_family_id.asc().nullslast(), Question.created_at.asc()).all()
        selected: list[Question] = []
        excluded: list[dict] = []
        seen_lineage: dict[str, str] = {}
        for question in candidates:
            reasons: list[str] = []
            if bool(question.is_retired):
                reasons.append('retired')
            if bool(question.is_duplicate):
                reasons.append('duplicate')
            lineage_root = question_lineage_root(question)
            if not reasons and lineage_root in seen_lineage:
                reasons.append('duplicate_lineage')
            if reasons:
                excluded.append({
                    'question_id': str(question.id),
                    'reasons': reasons,
                    'lineage_root': lineage_root,
                    'kept_question_id': seen_lineage.get(lineage_root),
                })
                continue
            seen_lineage[lineage_root] = str(question.id)
            selected.append(question)
        return selected, excluded

    def _release_questions_for_version(self, version: QuestionBankVersion) -> list[Question]:
        questions, _excluded = self._release_question_selection(version)
        return questions

    def _refresh_unpublished_release_snapshot(self, release: QuestionBankRelease) -> list[dict]:
        """Refresh a pristine unpublished Release from current clean questions."""
        if release.status == 'published' or release.published_at:
            return []
        version = self.db.get(QuestionBankVersion, release.bank_version_id)
        if not version:
            raise ValueError('Release thiếu Bank Version để làm mới snapshot.')
        rows = self.db.query(BankReleaseQuestion).filter(BankReleaseQuestion.bank_release_id == release.id).all()
        if any(bool(row.openedx_library_problem_id) for row in rows):
            return []

        questions, excluded = self._release_question_selection(version)
        if not questions:
            raise ValueError('Không còn câu đã duyệt hợp lệ sau khi tự loại câu lỗi/trùng. Hãy duyệt ít nhất một câu trước khi đưa lên CMS.')

        selected_by_id = {str(question.id): question for question in questions}
        existing_by_id = {str(row.question_id): row for row in rows}
        for question_id, row in list(existing_by_id.items()):
            if question_id not in selected_by_id:
                self.db.delete(row)
                existing_by_id.pop(question_id, None)

        for question in questions:
            question_id = str(question.id)
            row = existing_by_id.get(question_id)
            if row is None:
                row = BankReleaseQuestion(
                    id=str(uuid.uuid4()),
                    bank_release_id=release.id,
                    question_id=question.id,
                    question_family_id=question.question_family_id,
                    difficulty=question.difficulty,
                    openedx_library_problem_id=None,
                )
                self.db.add(row)
                existing_by_id[question_id] = row
            else:
                row.question_family_id = question.question_family_id
                row.difficulty = question.difficulty

        counts = {'easy': 0, 'medium': 0, 'hard': 0}
        families = set()
        for question in questions:
            diff = (question.difficulty or 'easy').lower()
            counts[diff if diff in counts else 'easy'] += 1
            if question.question_family_id:
                families.add(question.question_family_id)
        question_ids = [str(question.id) for question in questions]
        now = datetime.utcnow().isoformat()
        release.status = 'ready'
        release.approved_question_count = len(questions)
        release.easy_count = counts['easy']
        release.medium_count = counts['medium']
        release.hard_count = counts['hard']
        release.family_count = len(families)
        release.metadata_json = {
            **(release.metadata_json or {}),
            'membership_count': len(question_ids),
            'membership_sha256': self._release_membership_hash(question_ids),
            'membership_frozen_at': now,
            'membership_refreshed_before_publish_at': now,
            'auto_excluded_count': len(excluded),
            'auto_excluded_questions': excluded[:100],
            'auto_exclusion_policy': 'draft_error_rejected_not_candidates; duplicate_retired_duplicate_lineage_excluded',
        }
        self.db.flush()
        return excluded

    @staticmethod
    def _release_membership_hash(question_ids: list[str]) -> str:
        payload = '\n'.join(sorted(str(item) for item in question_ids)).encode('utf-8')
        return hashlib.sha256(payload).hexdigest()

    def _load_frozen_release_snapshot(self, release: QuestionBankRelease) -> tuple[list[BankReleaseQuestion], list[Question]]:
        self._refresh_unpublished_release_snapshot(release)
        rows = self.db.query(BankReleaseQuestion).filter(
            BankReleaseQuestion.bank_release_id == release.id
        ).order_by(BankReleaseQuestion.id.asc()).all()
        if not rows:
            raise ValueError('Release chưa có snapshot câu hỏi. Hãy hủy Release lỗi và chốt lại.')
        question_ids = [str(item.question_id) for item in rows]
        if len(question_ids) != len(set(question_ids)):
            raise ValueError('Snapshot Release có câu hỏi trùng. Không publish để tránh tạo component lặp.')
        questions_by_id = {
            str(item.id): item
            for item in self.db.query(Question).filter(Question.id.in_(question_ids)).all()
        }
        missing = [item for item in question_ids if item not in questions_by_id]
        if missing:
            sample = ', '.join(missing[:20])
            suffix = ' ...' if len(missing) > 20 else ''
            raise ValueError(
                f'Snapshot Release thiếu {len(missing)} câu hỏi trong database. '
                f'Question ID: {sample}{suffix}'
            )
        questions = [questions_by_id[item] for item in question_ids]
        invalid_details: list[str] = []
        for item in questions:
            reasons: list[str] = []
            if item.status not in {'approved', 'published'}:
                reasons.append(f'trạng thái={item.status}')
            if bool(item.is_retired):
                reasons.append('đã retire')
            if bool(item.is_duplicate):
                reasons.append('đánh dấu trùng')
            if not reasons:
                continue
            question_preview = re.sub(r'\s+', ' ', str(item.question_text or '')).strip()[:140]
            invalid_details.append(
                f'{item.id} · {question_preview or "(không có nội dung)"} · {", ".join(reasons)}'
            )
        if invalid_details:
            sample = ' | '.join(invalid_details[:20])
            suffix = ' | ...' if len(invalid_details) > 20 else ''
            raise ValueError(
                f'Snapshot Release có {len(invalid_details)} câu không còn hợp lệ. '
                'Không tự thay membership; hãy xử lý và chốt Release mới. '
                f'Câu cần xử lý: {sample}{suffix}'
            )
        expected_hash = str((release.metadata_json or {}).get('membership_sha256') or '')
        actual_hash = self._release_membership_hash(question_ids)
        if expected_hash and expected_hash != actual_hash:
            raise ValueError('Snapshot Release đã thay đổi sau khi chốt. Không publish để bảo vệ tính bất biến.')
        return rows, questions

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
        existing_release = self.db.query(QuestionBankRelease).filter(
            QuestionBankRelease.bank_version_id == version.id,
            QuestionBankRelease.status.notin_(['deprecated', 'archived']),
        ).order_by(QuestionBankRelease.created_at.desc()).first()
        if existing_release:
            raise ValueError(
                f'Bank Version đã có Release {existing_release.release_code} ở trạng thái {existing_release.status}. '
                'Hãy publish/retry hoặc hủy Release hiện tại thay vì tạo Release trùng.'
            )
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
        questions, auto_excluded = self._release_question_selection(version) if include_approved_questions else ([], [])
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
                'shared_across_courses': True,
                'library_org': self._canonical_library_org(),
                'term_slug': term_slug,
                'publish_wiring': 'pending_openedx_import',
                'membership_count': len(questions),
                'membership_sha256': self._release_membership_hash([question.id for question in questions]),
                'membership_frozen_at': datetime.utcnow().isoformat(),
                'auto_excluded_count': len(auto_excluded),
                'auto_excluded_questions': auto_excluded[:100],
                'auto_exclusion_policy': 'draft_error_rejected_not_candidates; duplicate_retired_duplicate_lineage_excluded',
            },
        )
        self.db.add(release)
        try:
            self.db.flush()
        except IntegrityError as exc:
            self.db.rollback()
            raise ValueError('Release cho Bank Version/Library này đã tồn tại. Hãy tải lại và dùng Release hiện có.') from exc
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
                if bool((release.metadata_json or {}).get('verification_complete')):
                    checks.append(_check('release_component_verification', 'pass', 'Toàn bộ component đã được Open edX verify.', {'verified_component_count': (release.metadata_json or {}).get('verified_component_count')}, blocking=False))
                else:
                    checks.append(_check('release_component_verification', 'fail', 'Release published cũ/chưa có bằng chứng verify đầy đủ. Hãy publish/re-verify trước khi tạo Quiz.', {'verification_complete': False}))
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
        elif release.status == 'published' and len(component_rows) == len(rows) and rows and bool((release.metadata_json or {}).get('verification_complete')):
            audit_status = 'PUBLISHED_VERIFIED'
            message = 'Release đã publish và toàn bộ component đã được Open edX verify.'
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
        # Library publishing is independent from physical delivery Course orgs.
        # The endpoint still requires a course-shaped key, so use a synthetic
        # key under the canonical Library Organization only.
        org = self._canonical_library_org()
        course_token = re.sub(r'[^A-Za-z0-9_-]+', '-', str(subject.code or 'SUBJECT')).strip('-_') or 'SUBJECT'
        return f'course-v1:{org}+{course_token}+BANK'

    async def publish_release_to_openedx(self, *, release_id: str, actor: str | None = None, course_id_for_org: str | None = None, force_reimport: bool = False, progress_callback: Any | None = None) -> dict:
        def report_progress(current: int, label: str) -> None:
            if not progress_callback:
                return
            try:
                progress_callback(max(0, min(int(current), 100)), 100, label)
            except Exception:
                # Progress telemetry must never make an otherwise valid Open edX
                # publish fail. The durable Release state remains authoritative.
                return

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

        release_items, questions = self._load_frozen_release_snapshot(release)
        report_progress(10, f'Đã kiểm tra snapshot Release: {len(questions)} câu')
        existing_items = {str(item.question_id): item for item in release_items}
        membership_hash = self._release_membership_hash([str(item.question_id) for item in release_items])

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
            'requested_physical_course_id': normalize_openedx_course_id(course_id_for_org) if course_id_for_org else None,
            'expected_openedx_library_key': expected_library_key,
            'previous_openedx_library_key': previous_library_key if previous_library_key != release.openedx_library_key else None,
            'library_key_rule': 'subject-term-chapter-release-version',
            'membership_count': len(release_items),
            'membership_sha256': membership_hash,
        }
        self.db.commit()

        term_slug = self._release_offering_term_slug(subject=subject, version=version)
        metadata_base = {
            'library_key': library_key,
            'library_org': self._canonical_library_org(),
            'org': self._canonical_library_org(),
            'term_slug': term_slug,
            'term_scoped_library': True,
            'shared_across_terms': False,
            'shared_across_courses': True,
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
        verified_existing: list[dict] = []
        verification_warnings: list[dict] = []
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
            report_progress(20, 'Content Library đã sẵn sàng trên CMS')
            if actual_library_key and actual_library_key != library_key:
                library_key = actual_library_key
                metadata_base = {
                    **metadata_base,
                    'library_key': library_key,
                    'requested_library_key': expected_library_key,
                    'actual_openedx_library_key': library_key,
                }
            total_publish_questions = max(len(questions), 1)
            for question_index, question in enumerate(questions, start=1):
                item = existing_items[str(question.id)]
                if item.openedx_library_problem_id and not force_reimport and not library_key_changed:
                    existing_problem_id = str(item.openedx_library_problem_id)
                    try:
                        existing_verify = await connector.verify_library_problem(
                            course_id,
                            library_key,
                            existing_problem_id,
                            metadata={**metadata_base, 'question_id': question.id, 'verification_source': 'release_publish_idempotency'},
                        )
                        if existing_verify.get('ok') and existing_verify.get('problem_exists') and existing_verify.get('library_exists', True):
                            verified_existing.append({
                                'question_id': str(question.id),
                                'problem_id': existing_problem_id,
                                'library_key': library_key,
                                'verify': existing_verify,
                            })
                            report_progress(20 + int(65 * question_index / total_publish_questions), f'Đã xác minh {question_index}/{len(questions)} câu trên CMS')
                            continue
                        if existing_verify.get('ok'):
                            verification_warnings.append({
                                'question_id': str(question.id),
                                'problem_id': existing_problem_id,
                                'status': existing_verify.get('status'),
                                'message': 'Component đã lưu trong AI Server nhưng Open edX xác nhận không còn tồn tại; hệ thống sẽ import lại.',
                            })
                        else:
                            raise RuntimeError(
                                f'Không verify an toàn được component hiện có {existing_problem_id} cho question {question.id}: '
                                f'{existing_verify.get("status") or "verify_failed"}'
                            )
                    except Exception as verify_exc:
                        # Never reimport blindly while verification itself is unavailable:
                        # the component may still exist and a retry could create duplicates.
                        raise RuntimeError(
                            f'Không verify được component hiện có {existing_problem_id} cho question {question.id}: '
                            f'{type(verify_exc).__name__}: {str(verify_exc) or repr(verify_exc)}'
                        ) from verify_exc
                media_rows, media_assets = build_openedx_question_assets(self.db, question)
                olx = question_to_openedx_olx(question, media=media_rows)
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
                    # Internal transport-only field. Real connector promotes this
                    # to top-level `assets` and strips it from metadata so image
                    # bytes never enter audit/result metadata.
                    '_question_media_assets': media_assets,
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
                        if imported_now:
                            raise RuntimeError('Open edX đổi Library key giữa quá trình import; đã dừng để tránh chia snapshot sang nhiều Library.')
                        library_key = retry_key
                        metadata_base = {**metadata_base, 'library_key': library_key, 'actual_openedx_library_key': library_key}
                        metadata = {**metadata, 'library_key': library_key, 'actual_openedx_library_key': library_key}
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
                except Exception as verify_exc:
                    imported_now.append({
                        'question_id': str(question.id),
                        'problem_id': str(problem_id),
                        'library_key': library_key,
                        'verify': {'ok': False, 'status': 'verify_unavailable'},
                    })
                    raise RuntimeError(
                        f'Import question {question.id} đã trả component id nhưng bước verify Open edX thất bại: '
                        f'{type(verify_exc).__name__}: {str(verify_exc) or repr(verify_exc)}'
                    ) from verify_exc
                imported_now.append({
                    'question_id': str(question.id),
                    'problem_id': str(problem_id),
                    'library_key': library_key,
                    'verify': verify,
                })
                if not (isinstance(verify, dict) and verify.get('ok') and verify.get('problem_exists') and verify.get('library_exists', True)):
                    raise RuntimeError(
                        f'Open edX không xác nhận component vừa import cho question {question.id}: '
                        f'{(verify or {}).get("status") if isinstance(verify, dict) else "invalid_verify_response"}'
                    )
                report_progress(20 + int(65 * question_index / total_publish_questions), f'Đã đưa và xác minh {question_index}/{len(questions)} câu trên CMS')
            report_progress(90, 'Đang kiểm tra tính đầy đủ của toàn bộ Release')
            published_at = datetime.utcnow()
            result_by_question_id = {
                row['question_id']: row
                for row in [*verified_existing, *imported_now]
            }
            questions_by_id = {str(question.id): question for question in questions}
            missing_component_results = [question_id for question_id in questions_by_id if question_id not in result_by_question_id]
            if missing_component_results:
                raise RuntimeError(f'Publish thiếu kết quả component cho {len(missing_component_results)} câu trong snapshot.')
            unverified_component_results = [
                question_id
                for question_id, row in result_by_question_id.items()
                if not (
                    isinstance(row.get('verify'), dict)
                    and row['verify'].get('ok')
                    and row['verify'].get('problem_exists')
                    and row['verify'].get('library_exists', True)
                )
            ]
            if unverified_component_results:
                raise RuntimeError(
                    f'Publish có {len(unverified_component_results)} component chưa được Open edX verify; không đánh dấu Release published.'
                )
            for question_id, question in questions_by_id.items():
                row = result_by_question_id[question_id]
                item = existing_items[question_id]
                item.openedx_library_problem_id = row['problem_id']
                item.difficulty = question.difficulty
                item.question_family_id = question.question_family_id
                question.openedx_library_problem_id = row['problem_id']
                question.target_library_key = row['library_key']
                question.status = 'published'
                question.published_at = published_at
                question.published_by = actor
            release.openedx_library_key = library_key
            release.metadata_json = {
                **(release.metadata_json or {}),
                'actual_openedx_library_key': library_key,
                'requested_openedx_library_key': expected_library_key,
                'library_key_canonicalized_by_connector': not self._library_key_same(library_key, expected_library_key),
            }
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
            release.published_at = published_at
            release.published_by = actor
            release.metadata_json = {
                **(release.metadata_json or {}),
                'publish_completed_at': datetime.utcnow().isoformat(),
                'library_result': library_result,
                'published_question_count': len(questions),
                'imported_now_count': len(imported_now),
                'verified_existing_count': len(verified_existing),
                'verification_warnings': verification_warnings,
                'verification_complete': True,
                'verified_component_count': len(result_by_question_id),
                'publish_wiring': 'openedx_library_verified_or_imported',
                'library_key_changed': library_key_changed,
            }
            version.status = 'published'
            version.published_at = release.published_at
            report_progress(97, 'Xác minh hoàn tất, đang ghi trạng thái Published')
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
                'skipped_existing_count': len(verified_existing),
                'verified_existing_count': len(verified_existing),
                'verification_warnings': verification_warnings,
                'library_result': library_result,
                'imported': imported_now,
                'errors': [],
            }
        except Exception as exc:
            # Best-effort rollback for components imported in this failed request.
            for row in imported_now:
                try:
                    await connector.delete_library_problem(course_id, row.get('library_key') or library_key, row['problem_id'], metadata={'bank_release_id': release.id, 'rollback': True})
                except Exception as delete_exc:
                    errors.append({'question_id': row.get('question_id'), 'problem_id': row.get('problem_id'), 'rollback_error': str(delete_exc)})
            error_text = f'{type(exc).__name__}: {str(exc) or repr(exc)}'
            self.db.rollback()
            failed_release = self.db.get(QuestionBankRelease, release_id)
            failed_version = self.db.get(QuestionBankVersion, release.bank_version_id)
            if failed_release:
                failed_release.status = 'publish_failed'
                failed_release.metadata_json = {
                    **(failed_release.metadata_json or {}),
                    'publish_failed_at': datetime.utcnow().isoformat(),
                    'error': error_text,
                    'rollback_errors': errors,
                    'manual_cleanup_required': bool(errors),
                    'remote_imported_before_failure': len(imported_now),
                }
                self.db.add(failed_release)
                self.db.commit()
            if failed_version:
                self._safe_refresh_chapter_stats(failed_version.chapter_id)
            raise RuntimeError(error_text) from exc
