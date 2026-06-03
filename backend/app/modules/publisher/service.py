from __future__ import annotations

import re
from collections import defaultdict
from datetime import datetime
from difflib import SequenceMatcher
from typing import Any
from urllib.parse import quote, urlparse

from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.question import Question
from app.models.publish import PublishBatch, PublishBatchItem
from app.services.library_service import ChapterLibraryService
from app.modules.openedx_connector.factory import get_openedx_connector
from app.services.openedx_exporter import question_to_openedx_olx
from app.services.question_service import QuestionService
from app.services.cms_tags import build_library_tags, build_question_tags, merge_tags
from app.services.quality_checker import QualityChecker


PUBLISH_MODES = {'publish_new', 'replace', 'delete_reimport'}
WARNING_STATUSES = {'published_with_pending_changes', 'imported_needs_manual_publish', 'imported_needs_manual_verify', 'rollback_openedx_delete_unverified'}
PUBLISHED_OK_STATUSES = {'verified', 'published', 'success', 'published_with_tag_warning'}


def _clean_openedx_usage_key(value: object) -> str:
    """Normalize Open edX usage keys before verify/delete/rollback.

    Older publish rows may contain JSON-encoded or URL-encoded strings such as
    '"lb:FPT:..."'.  Passing those quotes to the CMS connector makes
    LibraryUsageLocatorV2 parsing fail.
    """
    import json
    from urllib.parse import unquote

    text = str(value or '').strip()
    for _ in range(3):
        decoded = unquote(text).strip()
        if decoded != text:
            text = decoded
            continue
        if len(text) >= 2 and text[0] == text[-1] and text[0] in {'"', "'"}:
            inner = text[1:-1].strip()
            if inner != text:
                text = inner
                continue
        try:
            loaded = json.loads(text)
            if isinstance(loaded, str) and loaded.strip() != text:
                text = loaded.strip()
                continue
        except Exception:
            pass
        break
    return text


class OpenEdXPublisher:
    def __init__(self, db: Session):
        self.db = db

    @staticmethod
    def _looks_like_stub_result(result: dict | None) -> bool:
        if not isinstance(result, dict):
            return False
        text = ' '.join(str(result.get(key) or '') for key in ('mode', 'status', 'implementation', 'openedx_library_problem_id', 'openedx_block_id', 'openedx_library_id')).lower()
        return any(marker in text for marker in ('mock', 'stub', 'local_stub', 'lib-problem-v1:', 'bank-item-v1:', 'mock-library'))

    @staticmethod
    def _real_publish_guard(result: dict | None, step: str) -> None:
        if OpenEdXPublisher._looks_like_stub_result(result):
            raise RuntimeError(
                f'Open edX connector trả về kết quả {step} dạng mock/stub, chưa phải publish thật. '
                'Hãy tắt USE_MOCK_OPENEDX và cài connector production có tạo Library/Problem thật trong Studio.'
            )

    @staticmethod
    def _normalize_mode(mode: str | None) -> str:
        value = (mode or 'publish_new').strip().lower()
        if value in {'new', 'publish'}:
            value = 'publish_new'
        if value in {'republish', 'update'}:
            value = 'replace'
        if value not in PUBLISH_MODES:
            raise ValueError(f'Mode publish không hợp lệ: {mode}. Hợp lệ: publish_new, replace, delete_reimport.')
        return value

    @staticmethod
    def _is_published_ok(status: str | None) -> bool:
        value = (status or '').strip().lower()
        return value in PUBLISHED_OK_STATUSES or value.startswith('published_ok')

    @staticmethod
    def _is_publish_warning(status: str | None) -> bool:
        value = (status or '').strip().lower()
        return value in WARNING_STATUSES


    def _apply_openedx_lifecycle(self, question: Question, publish_status: str | None, *, delete_status: str | None = None) -> None:
        """Write explicit Open edX lifecycle fields alongside legacy publish_status.

        question.status remains the teacher/review workflow status. These fields
        tell the UI whether the component is merely imported, verified/published,
        pending manual Studio action, or waiting for manual delete.
        """
        value = (publish_status or '').strip().lower()
        question.openedx_publish_status = None
        question.openedx_verification_status = None
        question.openedx_manual_action_required = False
        if value in {'ensuring_library', 'importing_problem', 'publish_in_progress'}:
            question.openedx_publish_status = 'publishing'
            question.openedx_verification_status = 'pending'
        elif self._is_published_ok(value):
            question.openedx_publish_status = 'published'
            question.openedx_verification_status = 'verified'
        elif self._is_publish_warning(value):
            question.openedx_publish_status = 'imported'
            question.openedx_verification_status = 'pending'
            question.openedx_manual_action_required = True
        elif value == 'failed':
            question.openedx_publish_status = 'failed'
            question.openedx_verification_status = 'failed'
        elif value.startswith('rolled_back'):
            question.openedx_publish_status = 'rolled_back'
            question.openedx_verification_status = 'not_applicable'
        elif value.startswith('rollback_openedx_delete'):
            question.openedx_publish_status = 'rolled_back'
            question.openedx_verification_status = 'not_applicable'
            question.openedx_manual_action_required = True
        if delete_status is not None:
            question.openedx_delete_status = delete_status
            if delete_status in {'manual_delete_required', 'failed'}:
                question.openedx_manual_action_required = True

    @staticmethod
    def _batch_response(batch: PublishBatch) -> dict:
        summary = batch.summary_json or {}
        return {
            'course_id': batch.course_id,
            'batch_id': batch.id,
            'mode': batch.mode,
            'published': batch.published_count,
            'failed': batch.failed_count,
            'warnings': batch.warning_count,
            'status': batch.status,
            'errors': batch.errors_json or [],
            'libraries': summary.get('libraries') or [],
            'problem_bank_guide': summary.get('problem_bank_guide') or [],
            'idempotent_replay': True,
        }

    @staticmethod
    def _authoring_mfe_base_url() -> str | None:
        explicit = getattr(settings, 'openedx_authoring_mfe_base_url', None)
        if explicit:
            return explicit.rstrip('/')
        base = (settings.openedx_cms_base_url or settings.openedx_base_url or '').strip().rstrip('/')
        if not base:
            return None
        parsed = urlparse(base)
        host = parsed.netloc
        if not host:
            return None
        if host.startswith('studio.'):
            host = 'apps.' + host[len('studio.'):]
        elif host.startswith('studio-'):
            host = 'apps-' + host[len('studio-'):]
        elif host.startswith('cms.'):
            host = 'apps.' + host[len('cms.'):]
        elif host.startswith('cms-'):
            host = 'apps-' + host[len('cms-'):]
        else:
            # Last-resort Tutor/local convention. Keep the same host if it is already an MFE host.
            if not host.startswith('apps.') and not host.startswith('apps-'):
                host = 'apps.' + host
        return f'{parsed.scheme or "http"}://{host}/authoring'

    @classmethod
    def _library_studio_url(cls, library_key: str | None) -> str | None:
        if not library_key:
            return None
        base = cls._authoring_mfe_base_url()
        if not base:
            return None
        return f'{base}/library/{quote(str(library_key), safe=":")}'

    def _question_item(self, question: Question) -> dict:
        return {
            'question_text': question.question_text,
            'options': {'A': question.option_a, 'B': question.option_b, 'C': question.option_c, 'D': question.option_d},
            'correct_answer': question.correct_answer,
            'explanation': question.explanation,
            'source_ref': question.source_ref,
            'source_chunk_id': question.source_chunk_id,
            'source_type': question.source_type,
            'source_excerpt': question.source_excerpt,
        }

    @staticmethod
    def _word_set(text: str) -> set[str]:
        return {w for w in re.findall(r'[0-9a-zA-ZÀ-ỹ]{3,}', (text or '').lower()) if len(w) >= 3}

    def _quality_guard(self, question: Question) -> None:
        """Last guard before sending data to Open edX.

        This implements v25.9.13.27: if a question fails publish-quality checks,
        it is moved to needs_review and publish is blocked. Teacher can edit and
        approve again.
        """
        result = QualityChecker(self.db).check(self._question_item(question))
        flags = list(result.flags or [])
        detail: dict[str, Any] = dict(result.detail or {})

        q_lower = (question.question_text or '').lower()
        correct_text = str(getattr(question, f'option_{(question.correct_answer or "").lower()}', '') or '').strip()
        if correct_text and len(correct_text) >= 8 and correct_text.lower() in q_lower:
            flags.append('answer_leaked_in_question')
            detail['answer_leaked_in_question'] = correct_text[:180]

        options = [question.option_a, question.option_b, question.option_c, question.option_d]
        normalized_options = [' '.join(str(x or '').lower().split()) for x in options]
        for i, left in enumerate(normalized_options):
            for j, right in enumerate(normalized_options[i + 1:], start=i + 1):
                if left and right and SequenceMatcher(None, left, right).ratio() >= 0.90:
                    flags.append('very_similar_choices')
                    detail.setdefault('very_similar_choices', []).append([chr(65 + i), chr(65 + j)])

        source_words = self._word_set(question.source_excerpt or '')
        q_words = self._word_set(question.question_text or '')
        if source_words and q_words:
            overlap = len(source_words & q_words) / max(1, min(len(source_words), len(q_words)))
            if overlap < 0.08 and (question.source_type or '').lower() != 'problem':
                flags.append('weak_source_grounding')
                detail['source_overlap'] = round(overlap, 4)

        difficulty = (question.difficulty or '').lower()
        if difficulty == 'hard' and len(self._word_set(question.question_text or '')) < 8:
            flags.append('difficulty_mismatch')
            detail['difficulty_mismatch'] = 'Hard question is too short/simple.'

        blocking = [flag for flag in flags if flag not in {'missing_explanation', 'missing_source_reference'}]
        if not result.passed or blocking:
            question.status = 'needs_review'
            question.publish_status = 'blocked_quality_guard'
            self._apply_openedx_lifecycle(question, question.publish_status)
            question.publish_error = 'Không publish vì câu hỏi cần review chất lượng trước: ' + ', '.join(sorted(set(blocking or flags)))
            question.quality_flags = merge_tags(question.quality_flags, sorted(set(flags)))
            question.draft_error_reason = question.draft_error_reason or (blocking or flags or ['quality_guard'])[0]
            question.draft_error_detail = {**(question.draft_error_detail or {}), 'publish_quality_guard': detail, 'reason': result.reason}
            self.db.commit()
            raise ValueError(question.publish_error)

    def _prepare_question_publish(self, question: Question, mode: str = 'publish_new') -> tuple[str, object, dict, str, list[str]]:
        mode = self._normalize_mode(mode)
        if question.status == 'published' and mode == 'publish_new':
            raise ValueError('Question was already published. Use mode=replace hoặc mode=delete_reimport để publish lại vào component cũ.')
        if question.status not in {'approved', 'published'}:
            raise ValueError('Only approved/published questions can be published to CMS. Nếu bị quality guard, sửa câu rồi approve lại.')
        if question.status == 'approved':
            self._quality_guard(question)

        target = ChapterLibraryService(self.db).resolve_question_target(question)
        if not target:
            raise ValueError('Cannot resolve parent Chapter/Module library for this question. Sync course tree first or set source_node_id.')

        question.source_node_id = question.source_node_id or question.block_id or target.source_node_id
        question.source_node_title = question.source_node_title or target.source_node_title
        question.chapter_node_id = target.chapter_node_id
        question.chapter_title = target.chapter_title
        question.target_library_id = target.library.id
        question.target_library_key = target.library.library_key

        tag_payload = build_question_tags(question, target)
        question.tags = tag_payload.tag_names
        target.library.metadata_json = {
            **(target.library.metadata_json or {}),
            **build_library_tags(question.course_id, target.chapter_node_id, target.chapter_title, question.difficulty).as_metadata(),
        }
        self.db.flush()

        olx = question_to_openedx_olx(question)
        metadata = {
            'source_node_id': question.source_node_id,
            'source_node_title': question.source_node_title,
            'source_chunk_id': question.source_chunk_id,
            'source_type': question.source_type,
            'source_ref': question.source_ref,
            'source_excerpt': question.source_excerpt,
            'chapter_node_id': target.chapter_node_id,
            'chapter_title': target.chapter_title,
            'difficulty': question.difficulty,
            'course_id': question.course_id,
            'question_id': question.id,
            'previous_openedx_usage_key': question.openedx_library_problem_id,
            'publish_mode': mode,
            'library_key': target.library.library_key,
            'architecture': 'chapter_difficulty_library_problem_bank_friendly',
            **tag_payload.as_metadata(),
        }
        display_name = (question.learning_objective or question.topic or target.chapter_title or question.question_text or 'Learning Check')[:90]
        return olx, target, metadata, display_name, tag_payload.tag_names

    async def dry_run_question(self, question_id: str, mode: str = 'publish_new') -> dict:
        question = QuestionService(self.db).get_or_raise(question_id)
        olx, target, metadata, display_name, tag_names = self._prepare_question_publish(question, mode=mode)
        return {
            'ok': True,
            'mode': 'dry_run',
            'publish_mode': mode,
            'question_id': question.id,
            'course_id': question.course_id,
            'display_name': display_name,
            'library_key': target.library.library_key,
            'library_display_name': target.library.display_name,
            'chapter_node_id': target.chapter_node_id,
            'difficulty': question.difficulty,
            'metadata': metadata,
            'tag_names': tag_names,
            'library_tags': (target.library.metadata_json or {}).get('tag_names', []),
            'olx_preview': olx[:4000],
            'olx_length': len(olx),
        }

    def _verification_status(self, verify_result: dict | None, import_result: dict) -> tuple[str, dict]:
        verify_result = verify_result or {}
        import_status = str((import_result or {}).get('status') or '').lower()
        import_published = 'published' in import_status or bool((import_result or {}).get('published'))

        # After import/publish, Open edX Library UI/API can be stale for a few seconds,
        # especially on Ulmo where we bypass some post-publish tasks.  If the import
        # endpoint itself reported a successful publish but follow-up verification says
        # `problem_missing`, do not fail the whole publish. Keep the Open edX mapping and
        # surface this as a stale verification warning.  For rollback, `problem_missing`
        # is handled by the delete endpoint as success.
        if verify_result.get('library_exists') is False:
            raise RuntimeError(f'Open edX verification failed: {verify_result}')
        if verify_result.get('problem_exists') is False:
            if import_published and verify_result.get('library_exists') is True:
                return 'published_ok_stale_verify', {
                    **verify_result,
                    'stale_verify_warning': True,
                    'stale_verify_reason': 'Open edX import endpoint reported published, but immediate verify could not find the component yet.',
                }
            raise RuntimeError(f'Open edX verification failed: {verify_result}')

        # Verification endpoint can be unavailable or stale while the import endpoint already
        # completed the actual Open edX publish. Do not downgrade a successful publish to
        # warning unless Open edX explicitly reports unpublished/manual state.
        if verify_result.get('status') == 'verification_unavailable':
            if import_published:
                return 'verified', {**verify_result, 'verified_from_import_publish_result': True}
            return 'imported_needs_manual_verify', verify_result

        if verify_result.get('published') is True or verify_result.get('status') in {'verified', 'published'}:
            return 'verified', verify_result

        if verify_result.get('has_unpublished_changes') is True or verify_result.get('manual_publish_required') is True or verify_result.get('published') is False:
            # If the import result says the Library publish completed but a follow-up verify is stale,
            # treat as published_ok_stale_verify instead of showing a scary warning in /export.
            if import_published and verify_result.get('problem_exists', True) and verify_result.get('library_exists', True):
                return 'published_ok_stale_verify', {**verify_result, 'stale_verify_warning': True}
            return 'published_with_pending_changes', verify_result

        tag_count = verify_result.get('tag_count')
        if tag_count is not None and int(tag_count or 0) <= 0:
            enriched = {**verify_result, 'tag_warning': 'Không thấy tag trong Open edX sau publish.'}
            return 'published_with_tag_warning', enriched

        if import_published:
            return 'verified', verify_result or {'verified_from_import_response': True}
        return 'verified', verify_result or {'verified_from_import_response': True}

    async def publish_question(self, question_id: str, actor: str = 'teacher', mode: str = 'publish_new', batch_id: str | None = None) -> Question:
        mode = self._normalize_mode(mode)
        question = self.db.query(Question).filter(Question.id == question_id).with_for_update().first()
        if not question:
            raise ValueError('Question not found')
        if question.publish_status in {'publish_in_progress', 'ensuring_library', 'importing_problem'}:
            raise ValueError('Question is already being published. Vui lòng đợi lượt publish hiện tại hoàn tất.')
        question.publish_status = 'publish_in_progress'
        self._apply_openedx_lifecycle(question, question.publish_status)
        self.db.commit()
        if settings.use_mock_openedx:
            question.publish_status = 'blocked_mock_openedx'
            self._apply_openedx_lifecycle(question, question.publish_status)
            question.publish_error = 'USE_MOCK_OPENEDX=true nên không publish thật sang Open edX.'
            self.db.commit()
            raise ValueError('USE_MOCK_OPENEDX=true: đây chỉ là mock connector, không tạo Library/Problem thật trong Open edX.')

        olx, target, metadata, display_name, tag_names = self._prepare_question_publish(question, mode=mode)
        connector = get_openedx_connector()
        library_metadata = {
            'library_key': target.library.library_key,
            'chapter_node_id': target.chapter_node_id,
            'chapter_title': target.chapter_title,
            'difficulty': question.difficulty,
            'architecture': 'course_many_libraries_by_chapter_and_difficulty',
            **build_library_tags(question.course_id, target.chapter_node_id, target.chapter_title, question.difficulty).as_metadata(),
        }

        item: PublishBatchItem | None = None
        if batch_id:
            item = PublishBatchItem(batch_id=batch_id, question_id=question.id, course_id=question.course_id, library_key=target.library.library_key, difficulty=question.difficulty, status='running')
            self.db.add(item)
            self.db.flush()

        try:
            question.publish_status = 'ensuring_library'
            self._apply_openedx_lifecycle(question, question.publish_status)
            question.publish_verification_json = {'step': 'ensure_library', 'target_library_key': target.library.library_key, 'metadata': metadata, 'tag_names': tag_names, 'mode': mode}
            self.db.commit()

            library_result = await connector.ensure_problem_library(
                course_id=question.course_id,
                chapter_node_id=target.chapter_node_id,
                display_name=target.library.display_name,
                metadata=library_metadata,
            )
            self._real_publish_guard(library_result, 'ensure_library')

            target.library.openedx_library_id = library_result.get('openedx_library_id') or library_result.get('library_id') or target.library.openedx_library_id
            target.library.library_key = library_result.get('library_key') or target.library.library_key
            target.library.status = library_result.get('status') or 'library_ready'
            metadata['library_key'] = target.library.library_key
            target.library.metadata_json = {**(target.library.metadata_json or {}), **library_metadata, 'library_key': target.library.library_key, 'ensure_result': library_result}

            if mode == 'delete_reimport' and question.openedx_library_problem_id:
                try:
                    delete_result = await connector.delete_library_problem(question.course_id, target.library.library_key, question.openedx_library_problem_id, metadata=metadata)
                    metadata['delete_reimport_result'] = delete_result
                except Exception as delete_exc:
                    metadata['delete_reimport_warning'] = str(delete_exc)

            question.publish_status = 'importing_problem'
            self._apply_openedx_lifecycle(question, question.publish_status)
            question.publish_verification_json = {'library_result': library_result, 'step': 'import_problem', 'mode': mode}
            self.db.commit()

            result = await connector.import_problem_to_library(
                course_id=question.course_id,
                library_key=target.library.library_key,
                olx=olx,
                display_name=display_name,
                metadata=metadata,
            )
            self._real_publish_guard(result, 'import_problem')

            problem_id = result.get('openedx_library_problem_id') or result.get('library_problem_id') or result.get('problem_id') or result.get('block_id')
            if not problem_id:
                raise RuntimeError('Open edX connector không trả về problem_id/library_problem_id sau khi import. Không đánh dấu published để tránh báo thành công giả.')

            verify_result = None
            try:
                verify_result = await connector.verify_library_problem(question.course_id, target.library.library_key, problem_id, metadata={**metadata, 'tag_names': tag_names})
                self._real_publish_guard(verify_result, 'verify_problem')
            except Exception as verify_exc:
                verify_result = {'status': 'verification_unavailable', 'manual_check_required': True, 'error': str(verify_exc)}

            publish_status, normalized_verify = self._verification_status(verify_result, result)

            question.source_node_id = metadata['source_node_id']
            question.chapter_node_id = target.chapter_node_id
            question.chapter_title = target.chapter_title
            question.target_library_id = target.library.id
            question.target_library_key = target.library.library_key
            question.openedx_block_id = result.get('openedx_block_id') or result.get('block_id') or problem_id
            question.openedx_library_problem_id = problem_id
            question.imported_library_at = datetime.utcnow()
            question.publish_error = None if self._is_published_ok(publish_status) else 'Đã import nhưng cần kiểm tra/publish thủ công trong Studio.'
            question.publish_status = publish_status
            self._apply_openedx_lifecycle(question, publish_status)
            question.publish_verification_json = {
                'library_result': library_result,
                'import_result': result,
                'verify_result': normalized_verify,
                'verified': self._is_published_ok(publish_status),
                'openedx_library_key': target.library.library_key,
                'openedx_problem_id': problem_id,
                'tag_names': tag_names,
                'mode': mode,
            }
            question.status = 'published' if self._is_published_ok(publish_status) else 'approved'
            question.published_at = datetime.utcnow()
            question.published_by = actor
            question.reviewed_by = actor

            if item:
                item.library_key = target.library.library_key
                item.openedx_usage_key = problem_id
                item.status = publish_status
                item.message = question.publish_error or 'OK'
                item.result_json = question.publish_verification_json

            self.db.commit()
            self.db.refresh(question)
            return question
        except Exception as exc:
            question.publish_status = 'failed'
            self._apply_openedx_lifecycle(question, question.publish_status)
            question.publish_error = str(exc)
            question.publish_verification_json = {**(question.publish_verification_json or {}), 'error': str(exc), 'mode': mode}
            if question.status == 'published' and mode == 'publish_new':
                question.status = 'approved'
            if item:
                item.status = 'failed'
                item.message = str(exc)
                item.result_json = {'error': str(exc), 'metadata': metadata}
            self.db.commit()
            raise

    def _batch_summary(self, course_id: str, batch_id: str | None = None) -> list[dict]:
        query = self.db.query(Question).filter(Question.course_id == course_id, Question.openedx_library_problem_id.isnot(None))
        if batch_id:
            item_question_ids = [row[0] for row in self.db.query(PublishBatchItem.question_id).filter(PublishBatchItem.batch_id == batch_id).all()]
            if item_question_ids:
                query = query.filter(Question.id.in_(item_question_ids))
        rows = query.all()
        grouped: dict[tuple[str, str], dict] = {}
        for q in rows:
            key = ((q.difficulty or 'unknown').upper(), q.target_library_key or 'unknown')
            if key not in grouped:
                grouped[key] = {
                    'difficulty': key[0],
                    'library_key': key[1],
                    'library_display_name': key[1],
                    'component_count': 0,
                    'verified_count': 0,
                    'pending_count': 0,
                    'failed_count': 0,
                    'status': 'published',
                    'studio_url': self._library_studio_url(key[1]),
                }
            row = grouped[key]
            row['component_count'] += 1
            if self._is_published_ok(q.publish_status):
                row['verified_count'] += 1
            elif self._is_publish_warning(q.publish_status):
                row['pending_count'] += 1
            elif q.publish_status == 'failed':
                row['failed_count'] += 1
            else:
                row['pending_count'] += 1
        for row in grouped.values():
            if row['failed_count']:
                row['status'] = 'failed'
            elif row['pending_count']:
                row['status'] = 'published_with_pending_changes'
            else:
                row['status'] = 'published'
        return sorted(grouped.values(), key=lambda r: (r['library_key'], r['difficulty']))

    async def publish_course_approved(self, course_id: str, actor: str = 'teacher', mode: str = 'publish_new', idempotency_key: str | None = None) -> dict:
        mode = self._normalize_mode(mode)
        idempotency_key = (idempotency_key or '').strip() or None
        if idempotency_key:
            existing = self.db.query(PublishBatch).filter(
                PublishBatch.course_id == course_id,
                PublishBatch.actor_id == actor,
                PublishBatch.mode == mode,
                PublishBatch.idempotency_key == idempotency_key,
            ).first()
            if existing:
                return self._batch_response(existing)
        query = self.db.query(Question).filter(Question.course_id == course_id)
        if mode == 'publish_new':
            query = query.filter(Question.status == 'approved')
        else:
            query = query.filter(Question.status.in_(['approved', 'published']))
        questions = query.order_by(Question.chapter_title.asc(), Question.difficulty.asc(), Question.created_at.asc()).all()

        batch = PublishBatch(course_id=course_id, actor_id=actor, mode=mode, total_questions=len(questions), status='running', created_at=datetime.utcnow(), idempotency_key=idempotency_key)
        self.db.add(batch)
        self.db.commit()

        ok, failed, warnings = 0, 0, 0
        errors: list[dict] = []
        for q in questions:
            try:
                before_status = q.publish_status
                await self.publish_question(q.id, actor, mode=mode, batch_id=batch.id)
                self.db.refresh(q)
                if self._is_published_ok(q.publish_status):
                    ok += 1
                else:
                    ok += 1
                    warnings += 1
            except Exception as exc:
                failed += 1
                errors.append({'question_id': q.id, 'error': str(exc), 'difficulty': q.difficulty, 'library_key': q.target_library_key})

        summary = self._batch_summary(course_id, batch.id)
        status = 'success' if ok and not failed and not warnings else ('warning' if ok and not failed and warnings else ('partial_success' if ok and failed else 'failed'))
        batch.status = status
        batch.published_count = ok
        batch.failed_count = failed
        batch.warning_count = warnings
        batch.summary_json = {'libraries': summary, 'problem_bank_guide': self._problem_bank_guide(summary), 'idempotency_key': idempotency_key}
        batch.errors_json = errors
        batch.completed_at = datetime.utcnow()
        self.db.commit()
        return {
            'course_id': course_id,
            'batch_id': batch.id,
            'mode': mode,
            'published': ok,
            'failed': failed,
            'warnings': warnings,
            'status': status,
            'errors': errors,
            'libraries': summary,
            'problem_bank_guide': self._problem_bank_guide(summary),
        }

    @staticmethod
    def _problem_bank_guide(summary: list[dict]) -> list[str]:
        return [f'{row["library_key"]}: {row["component_count"]} components' for row in summary]

    async def dry_run_course_approved(self, course_id: str) -> dict:
        questions = self.db.query(Question).filter(Question.course_id == course_id, Question.status == 'approved').all()
        rows = []
        for q in questions:
            try:
                rows.append(await self.dry_run_question(q.id))
            except Exception as exc:
                rows.append({'ok': False, 'question_id': q.id, 'error': str(exc)})
        return {'course_id': course_id, 'approved_count': len(questions), 'items': rows, 'libraries': self._batch_summary(course_id)}

    def publish_history(self, course_id: str, limit: int = 20) -> dict:
        batches = self.db.query(PublishBatch).filter(PublishBatch.course_id == course_id).order_by(PublishBatch.created_at.desc()).limit(min(max(limit, 1), 100)).all()
        return {
            'course_id': course_id,
            'batches': [
                {
                    'id': b.id,
                    'course_id': b.course_id,
                    'actor_id': b.actor_id,
                    'mode': b.mode,
                    'status': b.status,
                    'total_questions': b.total_questions,
                    'published_count': b.published_count,
                    'failed_count': b.failed_count,
                    'warning_count': b.warning_count,
                    'summary': b.summary_json or {},
                    'errors': b.errors_json or [],
                    'created_at': b.created_at.isoformat() if b.created_at else None,
                    'completed_at': b.completed_at.isoformat() if b.completed_at else None,
                }
                for b in batches
            ],
        }

    async def rollback_batch(self, batch_id: str, actor: str = 'teacher', level: str = 'ai_server', idempotency_key: str | None = None) -> dict:
        batch = self.db.query(PublishBatch).filter(PublishBatch.id == batch_id).with_for_update().first()
        if not batch:
            raise ValueError('Publish batch not found')

        normalized_level = (level or 'ai_server').strip().lower()
        idempotency_key = (idempotency_key or '').strip() or None
        previous_rollback = (batch.summary_json or {}).get('rollback') if isinstance(batch.summary_json, dict) else None
        if idempotency_key and batch.rollback_idempotency_key == idempotency_key and previous_rollback:
            return {
                'batch_id': batch_id,
                'level': previous_rollback.get('level') or normalized_level,
                'reset_questions': previous_rollback.get('reset_questions', 0),
                'deleted_openedx_components': previous_rollback.get('deleted_openedx_components', 0),
                'manual_delete_required': previous_rollback.get('manual_delete_required', 0),
                'failed_delete_count': previous_rollback.get('failed_delete_count', 0),
                'skipped_delete_count': previous_rollback.get('skipped_delete_count', 0),
                'errors': batch.errors_json or [],
                'items': [],
                'idempotent_replay': True,
            }
        if idempotency_key:
            batch.rollback_idempotency_key = idempotency_key
            self.db.flush()
        delete_openedx = normalized_level in {'openedx', 'open_edx', 'odx', 'delete_openedx', 'delete_open_edx'}
        items = self.db.query(PublishBatchItem).filter(PublishBatchItem.batch_id == batch_id).all()
        connector = get_openedx_connector() if delete_openedx else None

        reset_count = 0
        deleted_count = 0
        manual_delete_count = 0
        failed_delete_count = 0
        skipped_delete_count = 0
        errors: list[dict] = []
        item_results: list[dict] = []

        for item in items:
            q = self.db.get(Question, item.question_id)
            if not q:
                item.status = 'question_missing'
                item.message = 'Question not found during rollback'
                continue

            delete_result = None
            open_edx_deleted = False
            item_failed_delete = False
            item_manual_delete = False
            should_clear_openedx_mapping = False

            problem_id = _clean_openedx_usage_key(q.openedx_library_problem_id or item.openedx_usage_key)
            library_key = q.target_library_key or item.library_key
            if delete_openedx:
                if problem_id and library_key and connector is not None:
                    try:
                        delete_result = await connector.delete_library_problem(
                            q.course_id,
                            library_key,
                            problem_id,
                            metadata={
                                'question_id': q.id,
                                'rollback_batch_id': batch_id,
                                'openedx_block_id': q.openedx_block_id,
                                'openedx_library_problem_id': q.openedx_library_problem_id,
                            },
                        )
                        open_edx_deleted = bool(delete_result.get('deleted')) or delete_result.get('status') in {'already_absent', 'deleted_and_published'}
                        if open_edx_deleted:
                            deleted_count += 1
                            should_clear_openedx_mapping = True
                            item.status = 'rolled_back_openedx_deleted'
                            item.message = 'Deleted from Open edX Library and reset in AI Server'
                        else:
                            manual_delete_count += 1
                            item_manual_delete = True
                            item.status = 'rollback_manual_delete_required'
                            item.message = delete_result.get('status') or 'Open edX delete was not verified'
                            errors.append({
                                'question_id': q.id,
                                'problem_id': problem_id,
                                'library_key': library_key,
                                'delete_status': delete_result.get('status'),
                                'manual_delete_required': True,
                                'delete_result': delete_result,
                            })
                    except Exception as exc:
                        failed_delete_count += 1
                        item_failed_delete = True
                        item.status = 'rollback_openedx_delete_failed'
                        item.message = str(exc)
                        errors.append({'question_id': q.id, 'problem_id': problem_id, 'library_key': library_key, 'delete_error': str(exc)})
                else:
                    skipped_delete_count += 1
                    should_clear_openedx_mapping = True
                    item.status = 'rollback_no_openedx_mapping'
                    item.message = 'No Open edX usage key/library mapping; reset AI Server only'
            else:
                item.status = 'rolled_back_ai_server'
                item.message = 'Reset in AI Server only'

            # Always restore the question to approved so it can be republished.
            q.status = 'approved'
            if delete_openedx:
                if open_edx_deleted:
                    q.publish_status = 'rolled_back_openedx_deleted'
                    self._apply_openedx_lifecycle(q, q.publish_status, delete_status='deleted')
                    q.publish_error = f'Rollback batch {batch_id} bởi {actor}. Đã xóa component khỏi Open edX Library.'
                elif item_failed_delete or item_manual_delete:
                    q.publish_status = 'rollback_openedx_delete_unverified'
                    self._apply_openedx_lifecycle(q, q.publish_status, delete_status='failed' if item_failed_delete else 'manual_delete_required')
                    q.publish_error = f'Rollback batch {batch_id} bởi {actor}. AI Server đã reset, nhưng Open edX cần kiểm tra/xóa thủ công.'
                else:
                    q.publish_status = 'rolled_back_ai_server_no_openedx_mapping'
                    self._apply_openedx_lifecycle(q, q.publish_status, delete_status='not_applicable')
                    q.publish_error = f'Rollback batch {batch_id} bởi {actor}. Không có mapping Open edX để xóa.'
            else:
                q.publish_status = 'rolled_back_ai_server'
                self._apply_openedx_lifecycle(q, q.publish_status, delete_status='not_requested')
                q.publish_error = f'Rollback batch {batch_id} bởi {actor}. Chỉ reset AI Server, không xóa Open edX.'

            q.publish_verification_json = {
                **(q.publish_verification_json or {}),
                'rollback_batch_id': batch_id,
                'rollback_level': normalized_level,
                'delete_openedx_requested': delete_openedx,
                'delete_openedx_result': delete_result,
            }
            q.published_at = None
            q.published_by = None
            # Do not erase mapping when delete failed; otherwise user cannot retry
            # ODX rollback because the usage_key is lost. Clear it only after a
            # verified delete/already-absent result, or when no mapping existed.
            if delete_openedx and should_clear_openedx_mapping:
                q.openedx_block_id = None
                q.openedx_library_problem_id = None
            reset_count += 1
            item.result_json = {**(item.result_json or {}), 'rollback': {'level': normalized_level, 'delete_result': delete_result}}
            item_results.append({'question_id': q.id, 'item_id': item.id, 'status': item.status, 'deleted_openedx': open_edx_deleted})

        if delete_openedx and errors:
            batch.status = 'rolled_back_openedx_partial' if deleted_count or reset_count else 'rollback_openedx_failed'
        else:
            batch.status = f'rolled_back_{normalized_level}'
        batch.summary_json = {
            **(batch.summary_json or {}),
            'rollback': {
                'level': normalized_level,
                'reset_questions': reset_count,
                'deleted_openedx_components': deleted_count,
                'manual_delete_required': manual_delete_count,
                'failed_delete_count': failed_delete_count,
                'skipped_delete_count': skipped_delete_count,
                'idempotency_key': idempotency_key,
            },
        }
        batch.errors_json = errors
        self.db.commit()
        return {
            'batch_id': batch_id,
            'level': normalized_level,
            'reset_questions': reset_count,
            'deleted_openedx_components': deleted_count,
            'manual_delete_required': manual_delete_count,
            'failed_delete_count': failed_delete_count,
            'skipped_delete_count': skipped_delete_count,
            'errors': errors,
            'items': item_results,
        }
