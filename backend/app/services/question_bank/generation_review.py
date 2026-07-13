from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.question import Question, QuestionReviewLog
from app.models.question_bank import (
    BankQuestionFamily,
    ConceptVersion,
    LearningMaterialVersion,
    MaterialChunk,
    QuestionBankVersion,
    Subject,
    SubjectChapter,
)
from app.services.answer_randomizer import normalize_and_shuffle_options
from app.services.cost_control import CostControlService
from app.services.generation_cache import question_fingerprint, sha256_text
from app.services.model_gateway import ModelGateway
from app.services.quality_checker import QualityChecker
from app.services.question_family import build_question_family_id, normalize_difficulty
from app.services.source_chunk_refs import join_source_chunk_ids, split_source_chunk_ids
from app.services.token_counter import count_tokens
from app.services.question_bank.helpers import slugify


class QuestionBankGenerationReviewWorkflowService:
    """Generation and review workflow for VersionedQuestionBankService.

    This module is intentionally behavior-preserving: routes still call the
    public methods on VersionedQuestionBankService, while the heavy
    generation/review workflow lives here. Low-level helpers that remain on the
    parent service are accessed through __getattr__ to avoid rewriting publish,
    material, and release semantics in the same refactor.
    """

    def __init__(self, parent_service: Any):
        self.parent = parent_service

    @property
    def db(self) -> Session:
        return self.parent.db

    def __getattr__(self, name: str) -> Any:
        return getattr(self.parent, name)

    def _bank_generation_content(self, *, bank_version_id: str, material_version_ids: list[str] | None = None, max_input_tokens: int = 18000) -> tuple[str, list[MaterialChunk], int]:
        query = self.db.query(MaterialChunk).filter(MaterialChunk.bank_version_id == bank_version_id)
        if material_version_ids:
            query = query.filter(MaterialChunk.material_version_id.in_(material_version_ids))
        rows = query.order_by(MaterialChunk.material_version_id.asc(), MaterialChunk.chunk_index.asc()).all()
        selected: list[MaterialChunk] = []
        total = 0
        parts: list[str] = []
        for row in rows:
            token_count = int(row.token_count or count_tokens(row.content or ''))
            if selected and total + token_count > max_input_tokens:
                break
            selected.append(row)
            total += token_count
            parts.append(
                "Source: " + str(row.source_ref or f'bank-material:{row.material_version_id}') + "\n"
                + "Type: " + str(row.source_type or 'file') + "\n"
                + "ChunkId: " + str(row.id) + "\n"
                + "BlockId: " + str(row.material_version_id) + "\n"
                + (f"Page: {row.page_number}\n" if row.page_number else "")
                + str(row.content or '')
            )
        return '\n\n---\n\n'.join(parts), selected, total

    def _chunks_to_generation_content(self, chunks: list[MaterialChunk], *, max_input_tokens: int = 18000) -> tuple[str, list[MaterialChunk], int]:
        selected: list[MaterialChunk] = []
        total = 0
        parts: list[str] = []
        for row in chunks:
            token_count = int(row.token_count or count_tokens(row.content or ''))
            if selected and total + token_count > max_input_tokens:
                break
            selected.append(row)
            total += token_count
            parts.append(
                "Source: " + str(row.source_ref or f'bank-material:{row.material_version_id}') + "\n"
                + "Type: " + str(row.source_type or 'file') + "\n"
                + "ChunkId: " + str(row.id) + "\n"
                + "BlockId: " + str(row.material_version_id) + "\n"
                + (f"Page: {row.page_number}\n" if row.page_number else "")
                + str(row.content or '')
            )
        return '\n\n---\n\n'.join(parts), selected, total

    @staticmethod
    def _split_count_evenly(total: int, bucket_count: int) -> list[int]:
        total = max(0, int(total or 0))
        bucket_count = max(1, int(bucket_count or 1))
        base = total // bucket_count
        remainder = total % bucket_count
        return [base + (1 if index < remainder else 0) for index in range(bucket_count)]

    def _balanced_material_generation_plan(
        self,
        *,
        chunks: list[MaterialChunk],
        question_count: int,
        difficulty_easy: int,
        difficulty_medium: int,
        difficulty_hard: int,
    ) -> list[dict]:
        grouped: dict[str, list[MaterialChunk]] = {}
        for chunk in chunks:
            grouped.setdefault(str(chunk.material_version_id), []).append(chunk)
        material_ids = sorted(grouped.keys())
        if not material_ids:
            return []
        material_counts = self._split_count_evenly(int(question_count), len(material_ids))
        plan: list[dict] = []
        for material_id, material_total in zip(material_ids, material_counts):
            if material_total <= 0:
                continue
            diff_counts = self._difficulty_counts(
                total_questions=material_total,
                easy=difficulty_easy,
                medium=difficulty_medium,
                hard=difficulty_hard,
            )
            plan.append({
                'material_version_id': material_id,
                'question_count': material_total,
                'difficulty_counts': diff_counts,
                'chunks': grouped[material_id],
            })
        return plan

    def _difficulty_counts(self, *, total_questions: int, easy: int, medium: int, hard: int) -> dict[str, int]:
        total_percent = max(int(easy or 0) + int(medium or 0) + int(hard or 0), 1)
        raw = {
            'easy': total_questions * int(easy or 0) / total_percent,
            'medium': total_questions * int(medium or 0) / total_percent,
            'hard': total_questions * int(hard or 0) / total_percent,
        }
        counts = {k: int(v) for k, v in raw.items()}
        remainder = total_questions - sum(counts.values())
        order = sorted(raw.keys(), key=lambda key: raw[key] - counts[key], reverse=True)
        for key in order[:remainder]:
            counts[key] += 1
        return {k: v for k, v in counts.items() if v > 0}

    def _get_or_create_concept_version(self, *, version: QuestionBankVersion, material_version_id: str | None, item: dict, chunk_ids: list[str]) -> ConceptVersion:
        title = str(item.get('concept_title') or item.get('concept') or item.get('topic') or 'Khái niệm chưa đặt tên').strip()
        key = slugify(str(item.get('concept_key') or title), 'concept')[:180]
        row = self.db.query(ConceptVersion).filter(ConceptVersion.bank_version_id == version.id, ConceptVersion.concept_key == key).first()
        if row:
            return row
        row = ConceptVersion(
            id=str(uuid.uuid4()),
            bank_version_id=version.id,
            subject_id=version.subject_id,
            chapter_id=version.chapter_id,
            material_version_id=material_version_id,
            concept_key=key,
            concept_title=title,
            description=str(item.get('ai_rationale') or ''),
            learning_objective=str(item.get('learning_objective') or ''),
            source_evidence=str(item.get('source_evidence') or item.get('source_excerpt') or ''),
            source_chunk_hash=sha256_text('|'.join(sorted(chunk_ids)), 64) if chunk_ids else None,
            status='active',
        )
        self.db.add(row)
        self.db.flush()
        return row

    def _get_or_create_bank_family(self, *, version: QuestionBankVersion, concept: ConceptVersion, difficulty: str, item: dict) -> BankQuestionFamily:
        diff = normalize_difficulty(difficulty)
        family_key = build_question_family_id(
            course_id=f'bank:{version.id}',
            chapter_node_id=version.chapter_id,
            difficulty=diff,
            concept_id=concept.id,
            concept_key=concept.concept_key,
            concept_title=concept.concept_title,
            topic=item.get('topic'),
            learning_objective=item.get('learning_objective'),
            question_text=item.get('question') or item.get('question_text'),
        )
        row = self.db.query(BankQuestionFamily).filter(
            BankQuestionFamily.bank_version_id == version.id,
            BankQuestionFamily.difficulty == diff,
            BankQuestionFamily.family_key == family_key,
        ).first()
        if row:
            return row
        row = BankQuestionFamily(
            id=str(uuid.uuid4()),
            bank_version_id=version.id,
            subject_id=version.subject_id,
            chapter_id=version.chapter_id,
            concept_version_id=concept.id,
            difficulty=diff,
            family_key=family_key,
            family_title=concept.concept_title,
            family_fingerprint=sha256_text(f'{version.id}|{concept.concept_key}|{diff}', 64),
            status='active',
        )
        self.db.add(row)
        self.db.flush()
        return row

    def _next_variant_no(self, *, bank_version_id: str, family_key: str) -> int:
        value = self.db.query(func.max(Question.variant_no)).filter(
            Question.bank_version_id == bank_version_id,
            Question.question_family_id == family_key,
        ).scalar()
        return int(value or 0) + 1

    def _chapter_question_count(self, *, chapter_id: str) -> int:
        # Người dùng hiểu quota theo Bài/Chapter, không theo Bank Version kỹ thuật.
        # Tính cả approved / pending / rejected / draft_error để không thể bỏ câu rồi tạo vô hạn.
        return int(self.db.query(func.count(Question.id)).filter(
            Question.bank_version_id.isnot(None),
            Question.subject_chapter_id == chapter_id,
            or_(Question.is_retired.is_(False), Question.is_retired.is_(None)),
        ).scalar() or 0)

    async def preview_generate_from_bank_version(
        self,
        *,
        bank_version_id: str,
        question_count: int,
        target_question_count: int | None = None,
        difficulty_easy: int = 50,
        difficulty_medium: int = 30,
        difficulty_hard: int = 20,
        material_version_ids: list[str] | None = None,
    ) -> dict:
        version = self._require_bank_version(bank_version_id)
        self._raise_if_published_locked(version, action='không thể tạo thêm câu hỏi')
        subject = self.db.get(Subject, version.subject_id)
        chapter = self.db.get(SubjectChapter, version.chapter_id)
        if not subject or not chapter:
            raise ValueError('Bank Version thiếu Subject hoặc Chapter')
        if question_count < 1 or question_count > 100:
            raise ValueError('Số câu tạo thêm phải trong khoảng 1-100')
        if int(difficulty_easy or 0) + int(difficulty_medium or 0) + int(difficulty_hard or 0) != 100:
            raise ValueError('Tổng tỷ lệ EASY/MEDIUM/HARD phải bằng 100%')
        effective_target = max(1, int(target_question_count or self._chapter_question_limit_default()))
        chapter_total = self._chapter_question_count(chapter_id=version.chapter_id)
        remaining = max(0, effective_target - chapter_total)
        if question_count > remaining:
            raise ValueError(f'Vượt chỉ tiêu của bài. Hiện có {chapter_total}/{effective_target} câu, chỉ còn được tạo thêm {remaining} câu.')
        content, chunks, content_tokens = self._bank_generation_content(bank_version_id=version.id, material_version_ids=material_version_ids)
        if not content.strip() or not chunks:
            raise ValueError('Bank Version chưa có tài liệu/chunk. Hãy upload tài liệu trước khi tạo câu hỏi.')
        counts = self._difficulty_counts(total_questions=question_count, easy=difficulty_easy, medium=difficulty_medium, hard=difficulty_hard)
        material_plan = self._balanced_material_generation_plan(
            chunks=chunks,
            question_count=question_count,
            difficulty_easy=difficulty_easy,
            difficulty_medium=difficulty_medium,
            difficulty_hard=difficulty_hard,
        )
        model_calls = sum(len([value for value in item.get('difficulty_counts', {}).values() if int(value or 0) > 0]) for item in material_plan) or 1
        # Estimate nhanh, không gọi GPT thật. Input tính theo tài liệu x difficulty, để phản ánh việc chia đều câu theo tài liệu.
        estimated_input_tokens = int(content_tokens * model_calls + 4300 * model_calls)
        estimated_cached_input_tokens = 0
        estimated_output_tokens = int(question_count * 320)
        raw_cost, pricing = await CostControlService(self.db).calculate_cost_usd(
            model_name=settings.openai_model,
            input_tokens=estimated_input_tokens,
            cached_input_tokens=estimated_cached_input_tokens,
            output_tokens=estimated_output_tokens,
            apply_safety_factor=False,
            refresh_pricing=False,
        )
        estimated_cost_usd = raw_cost * settings.cost_safety_factor
        return {
            'ok': True,
            'bank_version_id': version.id,
            'chapter_id': version.chapter_id,
            'question_count': int(question_count),
            'difficulty_counts': counts,
            'material_balancing': [
                {
                    'material_version_id': item.get('material_version_id'),
                    'question_count': item.get('question_count'),
                    'difficulty_counts': item.get('difficulty_counts'),
                    'chunk_count': len(item.get('chunks') or []),
                }
                for item in material_plan
            ],
            'current_question_count': chapter_total,
            'chapter_question_limit': effective_target,
            'remaining_quota': remaining,
            'estimated_input_tokens': estimated_input_tokens,
            'estimated_cached_input_tokens': estimated_cached_input_tokens,
            'estimated_output_tokens': estimated_output_tokens,
            'estimated_raw_cost_usd': round(raw_cost, 6),
            'estimated_cost_usd': round(estimated_cost_usd, 6),
            'estimated_cost_vnd': round(estimated_cost_usd * settings.usd_to_vnd, 0),
            'model_name': settings.openai_model,
            'pricing': pricing.as_dict() if pricing else None,
            'token_source': 'local_bank_generation_estimate',
            'message': 'Đây là ước tính trước khi gọi GPT thật. Chi phí thực tế có thể chênh lệch theo output của model.',
        }

    async def generate_from_bank_version(
        self,
        *,
        bank_version_id: str,
        question_count: int,
        target_question_count: int | None = None,
        difficulty_easy: int = 50,
        difficulty_medium: int = 30,
        difficulty_hard: int = 20,
        material_version_ids: list[str] | None = None,
        provider: str = 'openai',
        actor: str | None = None,
        approve_after_generate: bool = False,
    ) -> dict:
        version = self._require_bank_version(bank_version_id)
        self._raise_if_published_locked(version, action='không thể tạo thêm câu hỏi')
        subject = self.db.get(Subject, version.subject_id)
        chapter = self.db.get(SubjectChapter, version.chapter_id)
        if not subject or not chapter:
            raise ValueError('Bank Version thiếu Subject hoặc Chapter')
        if question_count < 1 or question_count > 100:
            raise ValueError('Số câu tạo thêm phải trong khoảng 1-100')
        if int(difficulty_easy or 0) + int(difficulty_medium or 0) + int(difficulty_hard or 0) != 100:
            raise ValueError('Tổng tỷ lệ EASY/MEDIUM/HARD phải bằng 100%')
        meta = dict(version.metadata_json or {})
        effective_target = max(1, int(target_question_count or meta.get('target_question_count') or self._chapter_question_limit_default()))
        if target_question_count:
            meta['target_question_count'] = int(target_question_count)
            version.metadata_json = meta
        if effective_target:
            active_count = self._chapter_question_count(chapter_id=version.chapter_id)
            if active_count + int(question_count) > effective_target:
                remaining = max(0, effective_target - active_count)
                raise ValueError(f'Vượt chỉ tiêu của bài. Hiện có {active_count}/{effective_target} câu, chỉ còn được tạo thêm {remaining} câu.')
        content, chunks, input_tokens = self._bank_generation_content(bank_version_id=version.id, material_version_ids=material_version_ids)
        if not content.strip() or not chunks:
            raise ValueError('Bank Version chưa có tài liệu/chunk. Hãy upload tài liệu trước khi generate.')
        counts = self._difficulty_counts(total_questions=question_count, easy=difficulty_easy, medium=difficulty_medium, hard=difficulty_hard)
        material_plan = self._balanced_material_generation_plan(
            chunks=chunks,
            question_count=question_count,
            difficulty_easy=difficulty_easy,
            difficulty_medium=difficulty_medium,
            difficulty_hard=difficulty_hard,
        )
        if not material_plan:
            raise ValueError('Không có tài liệu hợp lệ để chia đều số câu hỏi.')
        material_titles = {
            row.id: (row.title or row.file_name or row.id)
            for row in self.db.query(LearningMaterialVersion).filter(
                LearningMaterialVersion.id.in_([item['material_version_id'] for item in material_plan])
            ).all()
        }
        scope_title = f'{subject.code} · {chapter.title} · {version.version_code}'
        questions_created: list[Question] = []
        raw_usage_parts: list[dict] = []
        errors: list[dict] = []
        gateway = ModelGateway()
        checker = QualityChecker(self.db)

        for material_item in material_plan:
            active_material_id = str(material_item['material_version_id'])
            material_title = material_titles.get(active_material_id, active_material_id)
            material_content, material_chunks, material_tokens = self._chunks_to_generation_content(material_item.get('chunks') or [])
            local_chunk_ids = [row.id for row in material_chunks]
            if not material_content.strip() or not local_chunk_ids:
                errors.append({'material_version_id': active_material_id, 'error': 'Tài liệu không còn chunk hợp lệ để tạo câu hỏi.'})
                continue
            material_scope_title = f'{scope_title} · Tài liệu: {material_title}'
            for difficulty, count in (material_item.get('difficulty_counts') or {}).items():
                if count <= 0:
                    continue
                try:
                    items, usage = await gateway.generate_questions(
                        content=material_content,
                        question_count=count,
                        scope_title=material_scope_title,
                        target_difficulty=difficulty,
                        provider=provider,
                        prompt_cache_key='qbank:' + sha256_text(f'{version.id}:{active_material_id}:{difficulty}:{material_content}:{settings.openai_model}', 56),
                    )
                    raw_usage_parts.append({
                        'material_version_id': active_material_id,
                        'material_title': material_title,
                        'difficulty': difficulty,
                        'requested': count,
                        'input_tokens': material_tokens,
                        'usage': usage,
                    })
                except Exception as exc:
                    errors.append({
                        'material_version_id': active_material_id,
                        'material_title': material_title,
                        'difficulty': difficulty,
                        'error': f'{type(exc).__name__}: {str(exc) or repr(exc)}',
                    })
                    continue

                for index, raw_item in enumerate(items or []):
                    item = dict(raw_item or {})
                    item['difficulty'] = normalize_difficulty(item.get('difficulty') or difficulty)
                    randomized = normalize_and_shuffle_options(item, index=index, force_shuffle=True)
                    item['options'] = randomized.options
                    item['correct_answer'] = randomized.correct_answer
                    if not item.get('source_ref'):
                        item['source_ref'] = f'bank-material:{active_material_id}'
                    if not item.get('source_type'):
                        item['source_type'] = 'bank_material'
                    if not item.get('source_excerpt'):
                        item['source_excerpt'] = item.get('source_evidence') or ''
                    bank_source_chunk_ids = split_source_chunk_ids(item.get('source_chunk_id') or item.get('bank_chunk_id'))
                    valid_bank_chunk_ids = [chunk_id for chunk_id in bank_source_chunk_ids if chunk_id in local_chunk_ids]
                    joined_chunk_ids = join_source_chunk_ids(valid_bank_chunk_ids) if valid_bank_chunk_ids else None
                    # QualityChecker is course-first and validates ContentChunk IDs. Bank-first chunk IDs live in
                    # MaterialChunk, so keep the check payload clean while still saving the bank chunk reference below.
                    item['source_chunk_id'] = None
                    quality = checker.check(item)
                    status = 'approved' if (quality.passed and approve_after_generate) else ('pending_review' if quality.passed else 'draft_error')
                    question_text = str(item.get('question') or item.get('question_text') or '').strip()
                    if not question_text:
                        continue
                    concept = self._get_or_create_concept_version(version=version, material_version_id=active_material_id, item=item, chunk_ids=local_chunk_ids)
                    family = self._get_or_create_bank_family(version=version, concept=concept, difficulty=item['difficulty'], item=item)
                    q_hash = question_fingerprint(
                        question_text,
                        course_id=f'bank:{version.id}',
                        source_node_id=f'{family.family_key}:{active_material_id}',
                        difficulty=item['difficulty'],
                    )
                    existing = self.db.query(Question.id).filter(Question.bank_version_id == version.id, Question.question_hash == q_hash).first()
                    if existing:
                        continue
                    options = item.get('options') or {}
                    q = Question(
                        course_id=f'bank:{version.id}',
                        source_course_id=None,
                        department_id=subject.department_id,
                        subject_id=version.subject_id,
                        subject_chapter_id=version.chapter_id,
                        bank_version_id=version.id,
                        material_version_id=active_material_id,
                        concept_version_id=concept.id,
                        lesson_id=None,
                        lesson_title=material_scope_title,
                        block_id=f'bank-version:{version.id}:material:{active_material_id}',
                        topic=item.get('topic') or chapter.title,
                        concept_id=concept.id,
                        concept_title=concept.concept_title,
                        concept_key=concept.concept_key,
                        question_family_id=family.family_key,
                        variant_no=self._next_variant_no(bank_version_id=version.id, family_key=family.family_key),
                        source_evidence=str(item.get('source_evidence') or item.get('source_excerpt') or ''),
                        difficulty=item['difficulty'],
                        cognitive_level=item.get('cognitive_level') or 'remember',
                        learning_objective=item.get('learning_objective') or concept.learning_objective or '',
                        question_type=item.get('question_type') or 'single_choice',
                        question_text=question_text,
                        question_hash=q_hash,
                        option_a=options.get('A', ''),
                        option_b=options.get('B', ''),
                        option_c=options.get('C', ''),
                        option_d=options.get('D', ''),
                        correct_answer=item.get('correct_answer') or randomized.correct_answer or 'A',
                        explanation=item.get('explanation') or quality.reason,
                        source_ref=item.get('source_ref') or f'bank-material:{active_material_id}',
                        source_type=item.get('source_type') or 'bank_material',
                        source_page=item.get('source_page'),
                        source_timestamp_start=item.get('source_timestamp_start'),
                        source_timestamp_end=item.get('source_timestamp_end'),
                        source_chunk_id=joined_chunk_ids,
                        source_node_id=f'bank-version:{version.id}:material:{active_material_id}',
                        source_node_title=material_scope_title,
                        chapter_node_id=version.chapter_id,
                        chapter_title=chapter.title,
                        source_excerpt=item.get('source_excerpt') or item.get('source_evidence') or '',
                        tags=item.get('tags') or [],
                        ai_rationale=item.get('ai_rationale') or '',
                        quality_score=quality.score,
                        quality_flags=(quality.flags or []) + (['answer_randomized'] if randomized.changed else []),
                        draft_error_reason=None if quality.passed else (quality.error_code or 'quality_failed'),
                        draft_error_detail=None if quality.passed else (quality.detail or {'reason': quality.reason}),
                        generation_job_id=None,
                        model_provider=provider,
                        model_name=settings.openai_model,
                        status=status,
                        reviewed_by=actor if status == 'approved' else None,
                        reviewed_at=datetime.utcnow() if status == 'approved' else None,
                    )
                    self.db.add(q)
                    self.db.flush()
                    self.db.add(QuestionReviewLog(
                        id=str(uuid.uuid4()),
                        question_id=q.id,
                        old_status='generated',
                        new_status=status,
                        actor=actor or 'system',
                        note=f'Tạo câu hỏi từ tài liệu trong ngân hàng đề: {material_title}',
                    ))
                    questions_created.append(q)

        version.metadata_json = {
            **(version.metadata_json or {}),
            'last_bank_generate_at': datetime.utcnow().isoformat(),
            'last_bank_generate_requested_questions': question_count,
            'last_bank_generate_created_questions': len(questions_created),
            'last_bank_generate_input_tokens': input_tokens,
            'last_bank_generate_material_balancing': [
                {
                    'material_version_id': item.get('material_version_id'),
                    'question_count': item.get('question_count'),
                    'difficulty_counts': item.get('difficulty_counts'),
                    'chunk_count': len(item.get('chunks') or []),
                }
                for item in material_plan
            ],
            'last_bank_generate_errors': errors,
            'last_bank_generate_by': actor,
        }
        self.db.commit()
        self._safe_refresh_chapter_stats(version.chapter_id)
        return {
            'ok': not errors and bool(questions_created),
            'bank_version_id': version.id,
            'requested_questions': question_count,
            'created_questions': len(questions_created),
            'pending_review_count': len([q for q in questions_created if q.status == 'pending_review']),
            'approved_count': len([q for q in questions_created if q.status == 'approved']),
            'draft_error_count': len([q for q in questions_created if q.status == 'draft_error']),
            'input_chunks': len(chunks),
            'input_tokens': input_tokens,
            'difficulty_counts': counts,
            'material_balancing': [
                {
                    'material_version_id': item.get('material_version_id'),
                    'question_count': item.get('question_count'),
                    'difficulty_counts': item.get('difficulty_counts'),
                    'chunk_count': len(item.get('chunks') or []),
                }
                for item in material_plan
            ],
            'questions': [q.id for q in questions_created],
            'usage': raw_usage_parts,
            'errors': errors,
            'message': 'Đã generate câu hỏi từ Bank Version. Câu hỏi cần review trước khi tạo Release.' if questions_created else 'Không tạo được câu hỏi mới.',
        }


    def _require_bank_question(self, question_id: str, bank_version_id: str | None = None) -> Question:
        question = self.db.get(Question, question_id)
        if not question or not question.bank_version_id:
            raise ValueError('Không tìm thấy câu hỏi trong ngân hàng đề')
        if bank_version_id and question.bank_version_id != bank_version_id:
            raise ValueError('Câu hỏi không thuộc Bank Version đang chọn')
        return question

    def update_bank_question(self, *, bank_version_id: str, question_id: str, payload, actor: str | None = None):
        version = self._require_bank_version(bank_version_id)
        self._raise_if_published_locked(version, action='không thể sửa câu hỏi')
        question = self._require_bank_question(question_id, bank_version_id=version.id)
        if question.status == 'published':
            raise ValueError('Câu hỏi đã nằm trong Release published, không sửa trực tiếp ở đây')

        data = payload.model_dump(exclude_unset=True) if hasattr(payload, 'model_dump') else dict(payload or {})
        note = data.pop('note', '') or 'Giáo viên sửa câu hỏi trong ngân hàng đề'
        target_status = data.pop('target_status', None)
        allowed_fields = {
            'difficulty', 'cognitive_level', 'learning_objective', 'question_text',
            'option_a', 'option_b', 'option_c', 'option_d', 'correct_answer',
            'explanation', 'concept_title', 'question_family_id', 'source_ref',
            'source_type', 'source_excerpt', 'source_evidence',
        }
        changed = False
        for field, value in data.items():
            if field in allowed_fields and value is not None:
                setattr(question, field, value)
                changed = True

        if not (question.question_text or '').strip():
            raise ValueError('Câu hỏi không được để trống')
        options = [question.option_a, question.option_b, question.option_c, question.option_d]
        if any(not (opt or '').strip() for opt in options):
            raise ValueError('Phải có đủ 4 đáp án A/B/C/D')
        if question.correct_answer not in ('A', 'B', 'C', 'D'):
            raise ValueError('Đáp án đúng phải là A, B, C hoặc D')

        if question.status == 'draft_error' and changed:
            question.draft_error_reason = None
            question.draft_error_detail = None
            question.quality_flags = []
            if not target_status:
                target_status = 'pending_review'

        if target_status:
            if target_status not in ('pending_review', 'approved', 'rejected'):
                raise ValueError('Trạng thái sau khi sửa không hợp lệ')
            question.status = target_status
            if target_status == 'approved':
                question.reviewed_by = actor
                question.reviewed_at = datetime.utcnow()
                question.is_retired = False
                question.retired_reason = None
                question.retired_at = None

        question.updated_at = datetime.utcnow()
        self.db.add(question)
        self.db.add(QuestionReviewLog(
            id=str(uuid.uuid4()),
            question_id=question.id,
            old_status='edit',
            new_status=question.status,
            actor=actor or 'teacher',
            note=note,
        ))
        self.db.commit()
        self.db.refresh(question)
        self._safe_refresh_chapter_stats(version.chapter_id)
        return question

    def review_bank_question(self, *, bank_version_id: str, question_id: str, action: str = 'approve', note: str = '', actor: str | None = None) -> dict:
        version = self._require_bank_version(bank_version_id)
        self._raise_if_published_locked(version, action='không thể đổi trạng thái câu hỏi')
        question = self._require_bank_question(question_id, bank_version_id=version.id)
        action = (action or '').strip().lower()
        target_status = {'approve': 'approved', 'reject': 'rejected', 'back_to_review': 'pending_review'}.get(action)
        if not target_status:
            raise ValueError('Hành động duyệt không hợp lệ')
        if question.status == 'published':
            raise ValueError('Câu hỏi đã nằm trong Release published, không đổi trạng thái trực tiếp ở đây')
        old_status = question.status
        question.status = target_status
        question.reviewed_by = actor
        question.reviewed_at = datetime.utcnow()
        question.updated_at = datetime.utcnow()
        if target_status == 'approved':
            question.is_retired = False
            question.retired_reason = None
            question.retired_at = None
        self.db.add(QuestionReviewLog(
            id=str(uuid.uuid4()),
            question_id=question.id,
            old_status=old_status,
            new_status=target_status,
            actor=actor or 'teacher',
            note=note or f'Bank review: {action}',
        ))
        self.db.commit()
        self.db.refresh(question)
        self._safe_refresh_chapter_stats(version.chapter_id)
        return {
            'ok': True,
            'question': question,
            'old_status': old_status,
            'new_status': target_status,
            'message': 'Đã duyệt câu hỏi.' if target_status == 'approved' else ('Đã từ chối câu hỏi.' if target_status == 'rejected' else 'Đã đưa câu hỏi về trạng thái chờ duyệt.'),
        }

    def bulk_review_bank_questions(self, *, bank_version_id: str, action: str = 'approve', question_ids: list[str] | None = None, approve_all_pending: bool = False, apply_to_filtered: bool = False, status_filter: str | None = None, difficulty: str | None = None, search: str | None = None, note: str = '', actor: str | None = None) -> dict:
        version = self._require_bank_version(bank_version_id)
        self._raise_if_published_locked(version, action='không thể duyệt/bỏ hàng loạt câu hỏi')
        action = (action or '').strip().lower()
        if action not in {'approve', 'reject', 'back_to_review'}:
            raise ValueError('Hành động duyệt không hợp lệ')
        query = self.db.query(Question).filter(Question.bank_version_id == version.id)
        if approve_all_pending:
            query = query.filter(Question.status.in_(['pending_review', 'needs_review']))
        elif apply_to_filtered:
            if status_filter and status_filter not in {'all', 'needs_action'}:
                query = query.filter(Question.status == status_filter)
            elif status_filter == 'needs_action':
                query = query.filter(Question.status.in_(['pending_review', 'needs_review', 'draft_error']))
            if difficulty and difficulty != 'all':
                query = query.filter(Question.difficulty == difficulty)
            if search and search.strip():
                pattern = f"%{search.strip()}%"
                query = query.filter(or_(Question.question_text.ilike(pattern), Question.concept_title.ilike(pattern), Question.question_family_id.ilike(pattern)))
            total_filtered = int(query.order_by(None).count())
            if total_filtered > 2000:
                raise ValueError('Bộ lọc có hơn 2.000 câu. Hãy thu hẹp bộ lọc hoặc xử lý theo từng trang để tránh job HTTP quá nặng.')
        else:
            ids = [item for item in (question_ids or []) if item]
            if not ids:
                raise ValueError('Chưa chọn câu hỏi')
            query = query.filter(Question.id.in_(ids))
        rows = query.order_by(Question.created_at.asc()).all()
        changed: list[str] = []
        skipped: list[dict] = []
        for question in rows:
            if question.status == 'published':
                skipped.append({'question_id': question.id, 'reason': 'published_question_not_changed'})
                continue
            try:
                result = self.review_bank_question(bank_version_id=version.id, question_id=question.id, action=action, note=note, actor=actor)
                changed.append(result['question'].id)
            except Exception as exc:
                skipped.append({'question_id': question.id, 'reason': str(exc)})
        return {
            'ok': True,
            'changed_count': len(changed),
            'skipped_count': len(skipped),
            'changed_question_ids': changed,
            'skipped': skipped,
            'message': f'Đã xử lý {len(changed)} câu hỏi.' + (f' Bỏ qua {len(skipped)} câu.' if skipped else ''),
        }

    def mark_document_diff_resolved(self, *, bank_version_id: str, note: str = '', actor: str | None = None) -> dict:
        version = self._require_bank_version(bank_version_id)
        self._raise_if_published_locked(version, action='không thể xử lý diff tài liệu')
        meta = dict(version.metadata_json or {})
        meta.update({
            'diff_required': False,
            'document_change_state': 'diff_resolved',
            'diff_resolved_at': datetime.utcnow().isoformat(),
            'diff_resolved_by': actor,
            'diff_resolved_note': note or 'Giáo viên đã kiểm tra thay đổi tài liệu.',
        })
        version.metadata_json = meta
        version.updated_at = datetime.utcnow()
        self.db.commit()
        self._safe_refresh_chapter_stats(version.chapter_id)
        return {
            'ok': True,
            'bank_version_id': version.id,
            'diff_required': False,
            'document_change_state': 'diff_resolved',
            'message': 'Đã đánh dấu tài liệu đã được kiểm tra. Có thể chốt Release nếu câu hỏi đã duyệt đủ.',
        }
