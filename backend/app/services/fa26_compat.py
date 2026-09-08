from __future__ import annotations

import hashlib
import logging
import re
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import func

from app.db.session import SessionLocal
from app.models.question import Question
from app.models.question_bank import LearningMaterialVersion, MaterialChunk, Subject, SubjectOffering
from app.services.question_bank.helpers import normalize_academic_term_code
from app.services.question_bank.quiz_creation import QuestionBankQuizCreationWorkflowService
from app.services.question_bank_service import VersionedQuestionBankService

logger = logging.getLogger(__name__)

_PATCHED = False
_ORIGINAL_FINAL_TEST_PLAN = QuestionBankQuizCreationWorkflowService._build_final_test_plan


def _subject_code_key(value: Any) -> str:
    return re.sub(r'[^A-Z0-9]+', '', str(value or '').upper())


def _canonical_question_type(value: Any) -> str:
    raw = str(value or '').strip().lower().replace('-', '_').replace(' ', '_')
    aliases = {
        'single': 'single_select',
        'single_choice': 'single_select',
        'single_select': 'single_select',
        'multiple_choice': 'multi_select',
        'multiple_select': 'multi_select',
        'multi_choice': 'multi_select',
        'multi_select': 'multi_select',
        'text': 'text_input',
        'text_input': 'text_input',
        'numerical': 'numerical_input',
        'numeric': 'numerical_input',
        'numerical_input': 'numerical_input',
    }
    return aliases.get(raw, raw)


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
    """Apply FA26 Final Test compatibility without changing source question types.

    Final Test always uses the native multi-Release planner, which balances the
    visible question allocation across source lessons/Releases. Difficulty remains
    the only explicit quota. Question format is preserved from each source question
    (single/multi/text/numerical) and is never converted or hard-filtered to one type.

    Legacy Excel questions may rebalance difficulty when classified capacity is
    short; native questions remain strict and must satisfy the requested mix.
    """
    all_questions: list[Question] = []
    for release in source_releases or []:
        rows, questions = self._published_release_question_rows(release)
        all_questions.extend(questions[row.question_id] for row in rows if row.question_id in questions)

    all_legacy = bool(all_questions) and all(
        str(getattr(question, 'source_type', '') or '').strip().lower() == 'legacy_quiz_excel'
        for question in all_questions
    )
    kwargs = {
        'source_releases': source_releases,
        'source_details': source_details,
        'total_questions': total_questions,
        'difficulty_easy': difficulty_easy,
        'difficulty_medium': difficulty_medium,
        'difficulty_hard': difficulty_hard,
        'max_families_per_bank': max_families_per_bank,
    }

    plan = _ORIGINAL_FINAL_TEST_PLAN(self, **kwargs)

    candidate_type_counts = {
        'single_select': 0,
        'multi_select': 0,
        'text_input': 0,
        'numerical_input': 0,
    }
    for question in all_questions:
        qtype = _canonical_question_type(getattr(question, 'question_type', None))
        candidate_type_counts[qtype] = candidate_type_counts.get(qtype, 0) + 1

    # Do not expose an invented exact question-type mix. Each Problem Bank keeps
    # the original component/question types and Open edX samples from those pools.
    plan['candidate_question_type_counts'] = candidate_type_counts
    plan['question_type_policy'] = 'preserve_source_types_no_quota'
    plan['question_type_filter_applied'] = False

    if all_legacy:
        plan['difficulty_policy'] = 'legacy_rebalance_when_capacity_short'
        return plan

    requested = {
        str(key).upper(): int(value or 0)
        for key, value in (plan.get('target_counts') or {}).items()
    }
    effective = {
        str(key).upper(): int(value or 0)
        for key, value in (plan.get('effective_target_counts') or {}).items()
    }
    if requested and effective and requested != effective:
        raise ValueError(
            'Final test native không được tự cân lại tỷ lệ độ khó. '
            f'Yêu cầu={requested}, thực tế={effective}. Hãy bổ sung câu hỏi hoặc chỉnh cấu hình.'
        )
    plan['difficulty_policy'] = 'strict_native'
    return plan


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


def backfill_legacy_material_preview_chunks() -> dict[str, int]:
    """Backfill MaterialChunk rows for historical legacy quiz materials that have none."""
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
            if db.query(MaterialChunk.id).filter(MaterialChunk.material_version_id == material_id).first():
                continue
            material = db.get(LearningMaterialVersion, material_id)
            if not material:
                continue
            questions = (
                db.query(Question)
                .filter(
                    Question.material_version_id == material_id,
                    Question.source_type == 'legacy_quiz_excel',
                )
                .order_by(Question.created_at.asc(), Question.id.asc())
                .all()
            )
            created_for_material = 0
            for index, question in enumerate(questions, start=1):
                content = _legacy_question_chunk_content(question)
                if not content:
                    continue
                db.add(
                    MaterialChunk(
                        id=str(uuid.uuid4()),
                        material_version_id=material.id,
                        bank_version_id=material.bank_version_id,
                        subject_id=material.subject_id,
                        chapter_id=material.chapter_id,
                        subject_offering_id=material.subject_offering_id,
                        chunk_index=index,
                        content=content,
                        token_count=max(1, len(content.split())),
                        source_type='legacy_quiz_excel',
                        page_number=question.source_page,
                        source_ref=str(question.source_ref or f'legacy-question:{question.id}'),
                        content_hash=hashlib.sha256(content.encode('utf-8')).hexdigest(),
                        created_at=question.created_at or datetime.utcnow(),
                    )
                )
                created_for_material += 1
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
    QuestionBankQuizCreationWorkflowService._build_final_test_plan = _build_final_test_plan_compat
    _PATCHED = True
