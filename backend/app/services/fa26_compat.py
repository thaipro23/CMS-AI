from __future__ import annotations

import hashlib
import logging
import re
import uuid
from contextvars import ContextVar, Token
from datetime import datetime
from typing import Any

from sqlalchemy import event, func
from sqlalchemy.orm import Session as OrmSession

from app.db.session import SessionLocal
from app.models.question import Question
from app.models.question_bank import LearningMaterialVersion, MaterialChunk, Subject, SubjectOffering
from app.services.bank_operation_jobs import BankOperationJobService
from app.services.question_bank.constraint_planner import (
    QTYPES,
    build_final_constraint_plan,
    build_release_constraint_plan,
)
from app.services.question_bank.helpers import normalize_academic_term_code
from app.services.question_bank.quiz_creation import QuestionBankQuizCreationWorkflowService
from app.services.question_bank_service import VersionedQuestionBankService

logger = logging.getLogger(__name__)

_PATCHED = False
_MATERIAL_IMPORT_EVENT_REGISTERED = False

_ORIGINAL_CREATE_JOB = BankOperationJobService.create_job
_ORIGINAL_GET_JOB = BankOperationJobService.get_job

_DEFAULT_TYPE_WEIGHTS = {
    'single_select': 50,
    'multi_select': 30,
    'dropdown_fill': 20,
    'text_input': 0,
    'numerical_input': 0,
}
_DEFAULT_CONSTRAINT_CONFIG = {
    'difficulty_enabled': True,
    'question_type_enabled': False,
    'question_type_weights': dict(_DEFAULT_TYPE_WEIGHTS),
}
_QUIZ_CONSTRAINT_CONTEXT: ContextVar[dict[str, Any]] = ContextVar(
    'fa26_quiz_constraint_config',
    default=dict(_DEFAULT_CONSTRAINT_CONFIG),
)


def _subject_code_key(value: Any) -> str:
    return re.sub(r'[^A-Z0-9]+', '', str(value or '').upper())


def _coerce_bool(value: Any, fallback: bool) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return fallback
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {'1', 'true', 'yes', 'on'}:
            return True
        if normalized in {'0', 'false', 'no', 'off'}:
            return False
    return bool(value)


def normalize_quiz_constraint_config(payload: dict[str, Any] | None) -> dict[str, Any]:
    source = payload if isinstance(payload, dict) else {}
    raw_weights = source.get('question_type_weights')
    raw_weights = raw_weights if isinstance(raw_weights, dict) else {}

    weights: dict[str, int] = {}
    for key in QTYPES:
        try:
            weights[key] = max(0, min(100, int(raw_weights.get(key, _DEFAULT_TYPE_WEIGHTS.get(key, 0)) or 0)))
        except (TypeError, ValueError):
            weights[key] = int(_DEFAULT_TYPE_WEIGHTS.get(key, 0))

    return {
        'difficulty_enabled': _coerce_bool(
            source.get('difficulty_enabled'),
            bool(_DEFAULT_CONSTRAINT_CONFIG['difficulty_enabled']),
        ),
        'question_type_enabled': _coerce_bool(
            source.get('question_type_enabled'),
            bool(_DEFAULT_CONSTRAINT_CONFIG['question_type_enabled']),
        ),
        'question_type_weights': weights,
    }


def _validated_constraint_config() -> dict[str, Any]:
    config = normalize_quiz_constraint_config(_QUIZ_CONSTRAINT_CONTEXT.get())
    if config['question_type_enabled']:
        total = sum(int(value or 0) for value in config['question_type_weights'].values())
        if total != 100:
            raise ValueError(
                f'Tổng tỷ lệ Định dạng câu phải bằng 100%; hiện tại là {total}%.'
            )
    return config


def bind_quiz_constraint_request(payload: dict[str, Any] | None) -> Token:
    """Bind request-local Quiz/Final constraint flags before FastAPI validation."""
    return _QUIZ_CONSTRAINT_CONTEXT.set(normalize_quiz_constraint_config(payload))


def reset_quiz_constraint_request(token: Token | None) -> None:
    if token is not None:
        _QUIZ_CONSTRAINT_CONTEXT.reset(token)


def current_quiz_constraint_config() -> dict[str, Any]:
    return normalize_quiz_constraint_config(_QUIZ_CONSTRAINT_CONTEXT.get())


def _create_subject_offering_compat(
    self: VersionedQuestionBankService,
    *,
    subject_id: str,
    code: str = '',
    name: str = '',
    term: str | None = None,
    season: str | None = None,
    year: int | str | None = None,
    version_code: str = '',
    based_on_offering_id: str | None = None,
    clone_from_offering_id: str | None = None,
    clone_chapters: bool = True,
    clone_materials: bool = True,
    clone_questions: bool = True,
    description: str = '',
    actor: str | None = None,
) -> SubjectOffering:
    """Create a subject version while accepting legacy duplicate Subject UUIDs by code."""
    del clone_chapters, clone_materials, clone_questions

    subject = self.db.get(Subject, subject_id)
    if not subject:
        raise ValueError('Không tìm thấy môn học')

    source_offering_id = clone_from_offering_id or based_on_offering_id
    source_offering = self.db.get(SubjectOffering, source_offering_id) if source_offering_id else None
    if source_offering_id:
        if not source_offering:
            raise ValueError('Phiên bản môn nguồn không thuộc môn đã chọn')
        if str(source_offering.subject_id) != str(subject.id):
            source_subject = self.db.get(Subject, source_offering.subject_id)
            source_code = _subject_code_key(getattr(source_subject, 'code', None))
            target_code = _subject_code_key(subject.code)
            if not source_code or not target_code or source_code != target_code:
                raise ValueError('Phiên bản môn nguồn không thuộc môn đã chọn')

    term_info = normalize_academic_term_code(
        term=term,
        season=season,
        year=year,
        code=code or term or version_code,
    )
    term_code = str(term_info['term_code'])
    existing_term = self.db.query(SubjectOffering).filter(
        SubjectOffering.subject_id == subject.id,
        func.upper(SubjectOffering.term) == term_code.upper(),
    ).first()
    if existing_term:
        raise ValueError(f'Mỗi học kỳ chỉ có một phiên bản môn cuối. {subject.code}_{term_code} đã tồn tại.')

    offering_code = (code or f'{subject.code}_{term_code}').strip().upper()
    if not offering_code.startswith(subject.code.upper()):
        offering_code = f'{subject.code}_{offering_code}'
    offering_name = (name or f"{subject.code} - {term_info['display_name']} ({term_code})").strip()

    item = SubjectOffering(
        id=str(uuid.uuid4()),
        department_id=subject.department_id,
        subject_id=subject.id,
        code=offering_code,
        name=offering_name,
        term=term_code,
        version_code=(version_code or term_code).strip().upper(),
        based_on_offering_id=source_offering_id,
        created_by=actor,
        metadata_json={
            'architecture': 'subject_version_tree',
            'term_policy': 'SP/SU/FA + 2-digit year, e.g. SP25/SU26/FA27',
            'term': term_info,
            'description': description or '',
            'clone_policy': 'exact_working_copy_new_records_no_shared_ids',
            'release_policy': 'release_not_cloned_create_manually_after_editing',
            'diff_policy': 'only_when_material_changes_after_clone',
            'legacy_subject_code_compat': bool(
                source_offering and str(source_offering.subject_id) != str(subject.id)
            ),
        },
    )
    self.db.add(item)
    self.db.flush()

    clone_result = None
    if source_offering:
        clone_result = self._clone_subject_offering_content(source=source_offering, target=item, actor=actor)
        item.metadata_json = {
            **(item.metadata_json or {}),
            'cloned_from_offering_id': source_offering.id,
            'clone_result': clone_result,
        }

    self.db.commit()
    self.db.refresh(item)
    self._invalidate_dashboard_cache()
    return item


def _build_release_quiz_plan_compat(
    self: QuestionBankQuizCreationWorkflowService,
    *,
    release,
    total_questions: int,
    difficulty_easy: int,
    difficulty_medium: int,
    difficulty_hard: int,
    max_families_per_bank: int = 2,
) -> dict:
    config = _validated_constraint_config()
    return build_release_constraint_plan(
        self,
        release=release,
        total_questions=total_questions,
        difficulty_easy=difficulty_easy,
        difficulty_medium=difficulty_medium,
        difficulty_hard=difficulty_hard,
        max_families_per_bank=max_families_per_bank,
        config=config,
    )


def _build_final_test_plan_compat(
    self: QuestionBankQuizCreationWorkflowService,
    *,
    source_releases,
    source_details,
    total_questions: int,
    difficulty_easy: int,
    difficulty_medium: int,
    difficulty_hard: int,
    max_families_per_bank: int = 2,
) -> dict:
    config = _validated_constraint_config()
    return build_final_constraint_plan(
        self,
        source_releases=source_releases,
        source_details=source_details,
        total_questions=total_questions,
        difficulty_easy=difficulty_easy,
        difficulty_medium=difficulty_medium,
        difficulty_hard=difficulty_hard,
        max_families_per_bank=max_families_per_bank,
        config=config,
    )


def _create_job_compat(self: BankOperationJobService, *args, **kwargs):
    operation_type = str(kwargs.get('operation_type') or '')
    if operation_type == 'quiz_create':
        request_json = dict(kwargs.get('request_json') or {})
        request_json.update(current_quiz_constraint_config())
        kwargs['request_json'] = request_json
    return _ORIGINAL_CREATE_JOB(self, *args, **kwargs)


def _get_job_compat(self: BankOperationJobService, job_id: str):
    job = _ORIGINAL_GET_JOB(self, job_id)
    if job and str(getattr(job, 'operation_type', '') or '') == 'quiz_create':
        _QUIZ_CONSTRAINT_CONTEXT.set(
            normalize_quiz_constraint_config(getattr(job, 'request_json', None) or {})
        )
    else:
        _QUIZ_CONSTRAINT_CONTEXT.set(dict(_DEFAULT_CONSTRAINT_CONFIG))
    return job


def _legacy_question_chunk_content(question: Question) -> str:
    lines: list[str] = []
    prompt = str(question.question_text or '').strip()
    if prompt:
        lines.append(prompt)
    for label, field in (
        ('A', question.option_a),
        ('B', question.option_b),
        ('C', question.option_c),
        ('D', question.option_d),
    ):
        value = str(field or '').strip()
        if value:
            lines.append(f'{label}. {value}')
    answer = str(question.correct_answer or '').strip()
    if answer:
        lines.append(f'Đáp án: {answer}')
    explanation = str(question.explanation or '').strip()
    if explanation:
        lines.append(f'Giải thích: {explanation}')
    return '\n'.join(lines).strip()


def _legacy_chunk_source_ref(question: Question) -> str:
    return str(
        question.source_ref
        or question.source_node_id
        or f'legacy-question:{getattr(question, "id", "") or uuid.uuid4()}'
    )


def _ensure_legacy_material_chunks(db: OrmSession, material_id: str) -> int:
    material = db.get(LearningMaterialVersion, material_id)
    if not material:
        return 0

    questions = (
        db.query(Question)
        .filter(
            Question.material_version_id == material_id,
            Question.source_type == 'legacy_quiz_excel',
        )
        .order_by(Question.created_at.asc(), Question.id.asc())
        .all()
    )
    if not questions:
        return 0

    existing_refs = {
        str(row[0])
        for row in db.query(MaterialChunk.source_ref)
        .filter(MaterialChunk.material_version_id == material_id)
        .all()
        if row[0]
    }
    next_index = int(
        db.query(func.max(MaterialChunk.chunk_index))
        .filter(MaterialChunk.material_version_id == material_id)
        .scalar()
        or 0
    )
    created = 0
    for question in questions:
        source_ref = _legacy_chunk_source_ref(question)
        if source_ref in existing_refs:
            continue
        content = _legacy_question_chunk_content(question)
        if not content:
            continue
        next_index += 1
        db.add(
            MaterialChunk(
                id=str(uuid.uuid4()),
                material_version_id=material.id,
                bank_version_id=material.bank_version_id,
                subject_id=material.subject_id,
                chapter_id=material.chapter_id,
                subject_offering_id=material.subject_offering_id,
                chunk_index=next_index,
                content=content,
                token_count=max(1, len(content.split())),
                source_type='legacy_quiz_excel',
                page_number=question.source_page,
                source_ref=source_ref,
                content_hash=hashlib.sha256(content.encode('utf-8')).hexdigest(),
                created_at=question.created_at or datetime.utcnow(),
            )
        )
        existing_refs.add(source_ref)
        created += 1
    return created


def _materialize_new_legacy_question_chunks(session: OrmSession, _flush_context, _instances) -> None:
    """Create preview chunks in the same transaction that imports legacy Questions."""
    legacy_questions = [
        item
        for item in list(session.new)
        if isinstance(item, Question)
        and str(getattr(item, 'source_type', '') or '').strip().lower() == 'legacy_quiz_excel'
        and getattr(item, 'material_version_id', None)
    ]
    if not legacy_questions:
        return

    pending_refs = {
        str(getattr(item, 'source_ref', '') or '')
        for item in list(session.new)
        if isinstance(item, MaterialChunk) and getattr(item, 'source_ref', None)
    }
    grouped: dict[str, list[Question]] = {}
    for question in legacy_questions:
        grouped.setdefault(str(question.material_version_id), []).append(question)

    with session.no_autoflush:
        for material_id, questions in grouped.items():
            material = session.get(LearningMaterialVersion, material_id)
            if not material:
                continue
            existing_refs = {
                str(row[0])
                for row in session.query(MaterialChunk.source_ref)
                .filter(MaterialChunk.material_version_id == material_id)
                .all()
                if row[0]
            }
            existing_refs.update(pending_refs)
            next_index = int(
                session.query(func.max(MaterialChunk.chunk_index))
                .filter(MaterialChunk.material_version_id == material_id)
                .scalar()
                or 0
            )
            next_index += sum(
                1
                for item in list(session.new)
                if isinstance(item, MaterialChunk)
                and str(getattr(item, 'material_version_id', '') or '') == material_id
            )

            for question in questions:
                source_ref = _legacy_chunk_source_ref(question)
                if source_ref in existing_refs:
                    continue
                content = _legacy_question_chunk_content(question)
                if not content:
                    continue
                next_index += 1
                session.add(
                    MaterialChunk(
                        id=str(uuid.uuid4()),
                        material_version_id=material.id,
                        bank_version_id=material.bank_version_id,
                        subject_id=material.subject_id,
                        chapter_id=material.chapter_id,
                        subject_offering_id=material.subject_offering_id,
                        chunk_index=next_index,
                        content=content,
                        token_count=max(1, len(content.split())),
                        source_type='legacy_quiz_excel',
                        page_number=question.source_page,
                        source_ref=source_ref,
                        content_hash=hashlib.sha256(content.encode('utf-8')).hexdigest(),
                        created_at=question.created_at or datetime.utcnow(),
                    )
                )
                existing_refs.add(source_ref)


def _register_legacy_material_import_event() -> None:
    global _MATERIAL_IMPORT_EVENT_REGISTERED
    if _MATERIAL_IMPORT_EVENT_REGISTERED:
        return
    event.listen(OrmSession, 'before_flush', _materialize_new_legacy_question_chunks)
    _MATERIAL_IMPORT_EVENT_REGISTERED = True


def backfill_legacy_material_preview_chunks() -> dict[str, int]:
    """Repair historical imports; new imports materialize chunks before their own commit."""
    db = SessionLocal()
    materials_checked = 0
    materials_backfilled = 0
    chunks_created = 0
    try:
        material_ids = [
            str(row[0])
            for row in (
                db.query(Question.material_version_id)
                .filter(
                    Question.source_type == 'legacy_quiz_excel',
                    Question.material_version_id.isnot(None),
                )
                .distinct()
                .all()
            )
            if row[0]
        ]
        for material_id in material_ids:
            materials_checked += 1
            created_for_material = _ensure_legacy_material_chunks(db, material_id)
            if created_for_material:
                materials_backfilled += 1
                chunks_created += created_for_material
        db.commit()
    except Exception:
        db.rollback()
        logger.exception('legacy material preview chunk backfill failed')
    finally:
        db.close()
    return {
        'materials_checked': materials_checked,
        'materials_backfilled': materials_backfilled,
        'chunks_created': chunks_created,
    }


def apply_fa26_compat_patches() -> None:
    global _PATCHED
    if _PATCHED:
        return
    VersionedQuestionBankService.create_subject_offering = _create_subject_offering_compat
    QuestionBankQuizCreationWorkflowService._build_release_quiz_plan = _build_release_quiz_plan_compat
    QuestionBankQuizCreationWorkflowService._build_final_test_plan = _build_final_test_plan_compat
    BankOperationJobService.create_job = _create_job_compat
    BankOperationJobService.get_job = _get_job_compat
    _register_legacy_material_import_event()
    _PATCHED = True
