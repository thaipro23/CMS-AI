from datetime import datetime
from sqlalchemy.orm import Session
from app.core.rbac import UserContext, ensure_course_access, restrict_query_to_courses
from app.models.question import Question, QuestionEmbedding, QuestionReviewLog, QuestionVersion
from app.models.course import ContentChunk
from app.services.library_service import ChapterLibraryService
from app.services.quality_checker import QualityChecker
from app.services.duplicate_detector import DuplicateDetector
from app.services.generation_cache import question_fingerprint
from app.services.answer_randomizer import normalize_and_shuffle_options
from app.services.pedagogy import normalize_pedagogy, remap_pedagogy_after_shuffle
from app.services.question_diversity import diversity_report
from app.services.question_family import build_question_family_id, normalize_family_id, reconcile_question_families
from app.services.source_chunk_refs import first_existing_content_chunk, join_source_chunk_ids, split_source_chunk_ids


class QuestionService:
    def __init__(self, db: Session):
        self.db = db
        self.checker = QualityChecker(db)

    def _quality_error_payload(self, quality, duplicate_id: str | None = None, duplicate_score: float = 0.0) -> tuple[str | None, dict]:
        if duplicate_id:
            return 'duplicate_question', {
                'message': 'Câu hỏi gần trùng với câu đã có trong cùng course.',
                'duplicate_question_id': duplicate_id,
                'duplicate_score': round(float(duplicate_score or 0), 4),
                'flags': quality.flags or [],
            }
        if quality.passed:
            return None, {}
        code = quality.error_code or ((quality.flags or [None])[0]) or 'quality_failed'
        return code, {
            'message': quality.reason,
            'flags': quality.flags or [],
            'score': quality.score,
            **(quality.detail or {}),
        }


    def _existing_family_variant_count(self, course_id: str, family_id: str) -> int:
        if not family_id:
            return 0
        return int(self.db.query(Question).filter(
            Question.course_id == course_id,
            Question.question_family_id == family_id,
        ).count() or 0)

    def _resolve_family_fields(
        self,
        *,
        course_id: str,
        item: dict,
        difficulty: str,
        chapter_node_id: str | None,
        source_node_id: str | None,
        source_chunk_id: str | None,
        question_text: str,
    ) -> tuple[str, int, str]:
        concept_id = item.get('concept_id')
        concept_key = item.get('concept_key')
        concept_title = item.get('concept_title') or item.get('concept') or item.get('topic')
        family_id = normalize_family_id(
            item.get('question_family_id') or item.get('family_id'),
            course_id=course_id,
            chapter_node_id=chapter_node_id,
            difficulty=difficulty,
            concept_id=concept_id,
            concept_key=concept_key,
            concept_title=concept_title,
            topic=item.get('topic'),
            learning_objective=item.get('learning_objective') or item.get('learning_purpose'),
            source_node_id=source_node_id,
            source_chunk_id=source_chunk_id,
            question_text=question_text,
        )
        # variant_no is backend-owned. Model-provided values are ignored because
        # they may restart at 1 in every batch and create duplicate variant numbers.
        variant_no = self._existing_family_variant_count(course_id, family_id) + 1
        source_evidence = str(item.get('source_evidence') or item.get('source_excerpt') or '').strip()
        return family_id, variant_no, source_evidence

    def create_from_ai_items(self, *, course_id: str, lesson_id: str | None, items: list[dict], provider: str, model_name: str, job_id: str | None = None) -> list[Question]:
        questions: list[Question] = []
        detector = DuplicateDetector(self.db)
        family_variant_offsets: dict[str, int] = {}
        for index, raw_item in enumerate(items):
            item = dict(raw_item or {})
            randomized = normalize_and_shuffle_options(item, index=index, force_shuffle=True)
            item['pedagogy'] = remap_pedagogy_after_shuffle(
                item.get('pedagogy'), randomized.source_label_by_new_label, randomized.correct_answer
            )
            item['options'] = randomized.options
            item['correct_answer'] = randomized.correct_answer

            quality = self.checker.check(item)
            status = 'pending_review' if quality.passed else 'draft_error'
            duplicate_id, duplicate_score = detector.find_duplicate(course_id, item.get('question') or item.get('question_text') or '')
            if duplicate_id:
                status = 'draft_error'
                quality.flags = (quality.flags or []) + [f'duplicate:{duplicate_score:.3f}']
                quality.passed = False

            options = item.get('options') or {}
            source = item.get('source') or {}
            source_chunk_id = join_source_chunk_ids(split_source_chunk_ids(item.get('source_chunk_id') or source.get('chunk_id')))
            source_chunk = first_existing_content_chunk(self.db, source_chunk_id) if source_chunk_id else None
            source_node_id = item.get('source_node_id') or item.get('block_id') or source.get('block_id')
            source_node_title = item.get('source_node_title') or item.get('node_title')
            if not source_node_id and source_chunk:
                source_node_id = source_chunk.block_id
            source_ref = item.get('source_ref') or source.get('ref') or (source_chunk.source_ref if source_chunk else '') or ''
            source_type = item.get('source_type') or source.get('type') or (source_chunk.source_type if source_chunk else '') or 'course_component'
            source_page = item.get('source_page') or source.get('page') or (source_chunk.page_number if source_chunk else None)
            source_timestamp_start = item.get('source_timestamp_start') or source.get('timestamp_start') or (source_chunk.timestamp_start if source_chunk else None)
            source_timestamp_end = item.get('source_timestamp_end') or source.get('timestamp_end') or (source_chunk.timestamp_end if source_chunk else None)
            source_excerpt = item.get('source_excerpt') or source.get('excerpt') or item.get('source_evidence') or ''
            item_difficulty = item.get('difficulty') or 'easy'
            target = ChapterLibraryService(self.db).resolve_target(course_id, source_node_id, source_node_title, item_difficulty)
            if target:
                source_node_id = target.source_node_id or source_node_id
                source_node_title = target.source_node_title or source_node_title

            question_text = item.get('question') or item.get('question_text') or ''
            question_hash = question_fingerprint(
                question_text,
                course_id=course_id,
                source_node_id=source_node_id,
                difficulty=item_difficulty,
            )
            existing = self.db.query(Question.id).filter(Question.course_id == course_id, Question.question_hash == question_hash).first()
            if existing:
                # Exact duplicate cache: skip insert entirely and generate only the
                # missing amount in later repair/regenerate jobs.
                continue

            question_family_id, variant_no, source_evidence = self._resolve_family_fields(
                course_id=course_id,
                item=item,
                difficulty=item_difficulty,
                chapter_node_id=target.chapter_node_id if target else None,
                source_node_id=source_node_id,
                source_chunk_id=source_chunk_id,
                question_text=question_text,
            )
            variant_no += family_variant_offsets.get(question_family_id, 0)
            family_variant_offsets[question_family_id] = family_variant_offsets.get(question_family_id, 0) + 1

            draft_reason, draft_detail = self._quality_error_payload(quality, duplicate_id, duplicate_score)
            flags = list(quality.flags or [])
            if randomized.changed and 'answer_randomized' not in flags:
                flags.append('answer_randomized')

            q = Question(
                course_id=course_id,
                lesson_id=lesson_id,
                lesson_title=item.get('lesson_title'),
                block_id=source_node_id or item.get('block_id') or source.get('block_id'),
                topic=item.get('topic') or '',
                concept_id=item.get('concept_id'),
                concept_title=item.get('concept_title') or item.get('concept') or item.get('topic'),
                concept_key=item.get('concept_key'),
                question_family_id=question_family_id,
                variant_no=variant_no,
                source_evidence=source_evidence,
                difficulty=item_difficulty,
                cognitive_level=item.get('cognitive_level') or item.get('level') or 'remember',
                learning_objective=item.get('learning_objective') or item.get('learning_purpose') or '',
                pedagogy_json=normalize_pedagogy(
                    item.get('pedagogy'),
                    correct_answer=item.get('correct_answer'),
                    options=options,
                ),
                question_type=item.get('question_type') or 'single_choice',
                question_text=question_text,
                question_hash=question_hash,
                option_a=options.get('A', ''),
                option_b=options.get('B', ''),
                option_c=options.get('C', ''),
                option_d=options.get('D', ''),
                correct_answer=item.get('correct_answer') or 'A',
                explanation=item.get('explanation') or quality.reason,
                source_ref=source_ref,
                source_type=source_type,
                source_page=source_page,
                source_timestamp_start=source_timestamp_start,
                source_timestamp_end=source_timestamp_end,
                source_chunk_id=source_chunk_id,
                source_node_id=source_node_id,
                source_node_title=source_node_title,
                chapter_node_id=target.chapter_node_id if target else None,
                chapter_title=target.chapter_title if target else None,
                target_library_id=target.library.id if target else None,
                target_library_key=target.library.library_key if target else None,
                source_excerpt=source_excerpt,
                tags=item.get('tags') or [],
                ai_rationale=(
                    item.get('ai_rationale') or item.get('rationale')
                    or item.get('source_evidence')
                    or item.get('learning_objective') or ''
                ),
                quality_score=quality.score,
                quality_flags=flags if quality.passed else (flags or [quality.reason]),
                draft_error_reason=draft_reason,
                draft_error_detail=draft_detail or None,
                is_duplicate=bool(duplicate_id),
                duplicate_of_question_id=duplicate_id,
                duplicate_score=float(duplicate_score or 0) if duplicate_id else None,
                generation_job_id=job_id,
                model_provider=provider,
                model_name=model_name,
                status=status,
            )
            self.db.add(q)
            questions.append(q)
        self.db.flush()
        reconcile_question_families(self.db, course_id, commit=False)
        for q in questions:
            detector.save_embedding(q)
        self.db.commit()
        for q in questions:
            self.db.refresh(q)
        return questions

    def get_or_raise(self, question_id: str) -> Question:
        q = self.db.get(Question, question_id)
        if not q:
            raise ValueError('Question not found')
        return q

    def _snapshot(self, q: Question, *, actor: str, note: str) -> None:
        snapshot = {
            'course_id': q.course_id,
            'lesson_id': q.lesson_id,
            'lesson_title': q.lesson_title,
            'block_id': q.block_id,
            'topic': q.topic,
            'concept_id': q.concept_id,
            'concept_title': q.concept_title,
            'concept_key': q.concept_key,
            'question_family_id': q.question_family_id,
            'variant_no': q.variant_no,
            'source_evidence': q.source_evidence,
            'difficulty': q.difficulty,
            'cognitive_level': q.cognitive_level,
            'learning_objective': q.learning_objective,
            'pedagogy_json': q.pedagogy_json or {},
            'question_type': q.question_type,
            'question_text': q.question_text,
            'question_hash': q.question_hash,
            'option_a': q.option_a,
            'option_b': q.option_b,
            'option_c': q.option_c,
            'option_d': q.option_d,
            'correct_answer': q.correct_answer,
            'explanation': q.explanation,
            'source_ref': q.source_ref,
            'source_type': q.source_type,
            'source_page': q.source_page,
            'source_timestamp_start': q.source_timestamp_start,
            'source_timestamp_end': q.source_timestamp_end,
            'source_chunk_id': q.source_chunk_id,
            'source_node_id': q.source_node_id,
            'source_node_title': q.source_node_title,
            'chapter_node_id': q.chapter_node_id,
            'chapter_title': q.chapter_title,
            'target_library_key': q.target_library_key,
            'source_excerpt': q.source_excerpt,
            'tags': q.tags,
            'status': q.status,
            'draft_error_reason': q.draft_error_reason,
            'draft_error_detail': q.draft_error_detail,
            'duplicate_score': q.duplicate_score,
            'version': q.version,
        }
        self.db.add(QuestionVersion(question_id=q.id, version=q.version, actor=actor, note=note, snapshot=snapshot))

    def update_question(self, question_id: str, payload, actor: str | None = None) -> Question:
        q = self.get_or_raise(question_id)
        actor = actor or getattr(payload, 'actor', None) or 'system'
        if q.status == 'published':
            raise ValueError('Published question cannot be edited directly. Create a new version first.')

        self._snapshot(q, actor=actor, note=payload.note)

        editable_fields = [
            'lesson_title', 'block_id', 'topic', 'concept_id', 'concept_title', 'concept_key', 'source_evidence', 'difficulty', 'cognitive_level', 'learning_objective', 'pedagogy_json',
            'question_text', 'option_a', 'option_b', 'option_c', 'option_d', 'correct_answer', 'explanation',
            'source_ref', 'source_type', 'source_page', 'source_timestamp_start', 'source_timestamp_end',
            'source_chunk_id', 'source_node_id', 'source_node_title', 'source_excerpt', 'tags'
        ]
        data = payload.model_dump(exclude_unset=True)
        for field in editable_fields:
            if field in data:
                setattr(q, field, data[field])

        target = ChapterLibraryService(self.db).resolve_question_target(q)
        if target:
            q.source_node_id = target.source_node_id
            q.source_node_title = target.source_node_title
            q.chapter_node_id = target.chapter_node_id
            q.chapter_title = target.chapter_title
            q.target_library_id = target.library.id
            q.target_library_key = target.library.library_key

        q.question_family_id = build_question_family_id(
            course_id=q.course_id,
            chapter_node_id=q.chapter_node_id,
            difficulty=q.difficulty,
            concept_id=q.concept_id,
            concept_key=q.concept_key,
            concept_title=q.concept_title,
            legacy_family_id=q.question_family_id,
            topic=q.topic,
            learning_objective=q.learning_objective,
            source_node_id=q.source_node_id,
            source_chunk_id=q.source_chunk_id,
            question_text=q.question_text,
        )
        if not q.source_evidence:
            q.source_evidence = q.source_excerpt or ''

        item = {
            'question': q.question_text,
            'options': {'A': q.option_a, 'B': q.option_b, 'C': q.option_c, 'D': q.option_d},
            'correct_answer': q.correct_answer,
            'explanation': q.explanation,
            'source_ref': q.source_ref,
            'source_chunk_id': q.source_chunk_id,
        }
        quality = self.checker.check(item)
        q.question_hash = question_fingerprint(
            q.question_text,
            course_id=q.course_id,
            source_node_id=q.source_node_id,
            difficulty=q.difficulty,
        )
        duplicate_id, duplicate_score = DuplicateDetector(self.db).find_duplicate(q.course_id, q.question_text)
        if duplicate_id and duplicate_id != q.id:
            q.is_duplicate = True
            q.duplicate_of_question_id = duplicate_id
            q.duplicate_score = float(duplicate_score or 0)
            quality.flags = (quality.flags or []) + [f'duplicate:{duplicate_score:.3f}']
            quality.passed = False
        elif not duplicate_id:
            q.is_duplicate = False
            q.duplicate_of_question_id = None
            q.duplicate_score = None
        q.quality_score = quality.score
        q.quality_flags = (quality.flags or []) if quality.passed else (quality.flags or [quality.reason])
        q.draft_error_reason, q.draft_error_detail = self._quality_error_payload(quality, q.duplicate_of_question_id, q.duplicate_score or 0)
        q.status = 'pending_review' if quality.passed else 'draft_error'
        if q.status != 'draft_error':
            q.draft_error_reason = None
            q.draft_error_detail = None
        q.version += 1
        q.reviewed_by = None
        q.reviewed_at = None
        q.updated_at = datetime.utcnow()

        self.db.add(QuestionReviewLog(question_id=q.id, old_status='edited', new_status=q.status, actor=actor, note=payload.note))
        reconcile_question_families(self.db, q.course_id, chapter_node_id=q.chapter_node_id, commit=False)
        DuplicateDetector(self.db).save_embedding(q)
        self.db.commit()
        self.db.refresh(q)
        return q

    def transition(self, question_id: str, new_status: str, actor: str, note: str = '') -> Question:
        q = self.get_or_raise(question_id)
        old = q.status
        allowed = {
            'pending_review': {'approved', 'rejected'},
            'draft_error': {'pending_review', 'rejected'},
            'approved': {'published', 'rejected', 'pending_review'},
            'rejected': {'pending_review', 'approved'},
            'published': set(),
        }
        if new_status not in allowed.get(old, set()):
            raise ValueError(f'Invalid transition {old} -> {new_status}')
        q.status = new_status
        now = datetime.utcnow()
        if new_status in {'approved', 'rejected'}:
            q.reviewed_by = actor
            q.reviewed_at = now
        if new_status == 'published':
            q.published_at = now
        q.updated_at = now
        log = QuestionReviewLog(question_id=q.id, old_status=old, new_status=new_status, actor=actor, note=note)
        self.db.add(log)
        self.db.commit()
        self.db.refresh(q)
        return q


    def change_status(self, question_id: str, target_status: str, actor: str, note: str = '') -> Question:
        return self.transition(question_id, target_status, actor, note)


    def repair_draft_error(self, question_id: str, actor: str, note: str = 'Auto repair draft error') -> Question:
        q = self.get_or_raise(question_id)
        if q.status != 'draft_error':
            return q
        if q.status == 'published':
            raise ValueError('Published question cannot be repaired directly.')
        self._snapshot(q, actor=actor, note=note)

        q.question_family_id = build_question_family_id(
            course_id=q.course_id,
            chapter_node_id=q.chapter_node_id,
            difficulty=q.difficulty,
            concept_id=q.concept_id,
            concept_key=q.concept_key,
            concept_title=q.concept_title,
            legacy_family_id=q.question_family_id,
            topic=q.topic,
            learning_objective=q.learning_objective,
            source_node_id=q.source_node_id,
            source_chunk_id=q.source_chunk_id,
            question_text=q.question_text,
        )
        if not q.source_evidence:
            q.source_evidence = q.source_excerpt or ''

        item = {
            'question': q.question_text,
            'options': {'A': q.option_a, 'B': q.option_b, 'C': q.option_c, 'D': q.option_d},
            'correct_answer': q.correct_answer,
            'explanation': q.explanation,
            'source_ref': q.source_ref,
            'source_chunk_id': q.source_chunk_id,
            'source_node_id': q.source_node_id,
            'difficulty': q.difficulty,
        }
        randomized = normalize_and_shuffle_options(item, index=q.repair_attempt_count + 1, force_shuffle=True)
        q.pedagogy_json = remap_pedagogy_after_shuffle(
            q.pedagogy_json, randomized.source_label_by_new_label, randomized.correct_answer
        )
        q.option_a = randomized.options['A']
        q.option_b = randomized.options['B']
        q.option_c = randomized.options['C']
        q.option_d = randomized.options['D']
        q.correct_answer = randomized.correct_answer

        quality = self.checker.check({
            'question': q.question_text,
            'options': {'A': q.option_a, 'B': q.option_b, 'C': q.option_c, 'D': q.option_d},
            'correct_answer': q.correct_answer,
            'explanation': q.explanation,
            'source_ref': q.source_ref,
            'source_chunk_id': q.source_chunk_id,
        })
        duplicate_id, duplicate_score = DuplicateDetector(self.db).find_duplicate(q.course_id, q.question_text)
        if duplicate_id and duplicate_id != q.id:
            quality.passed = False
            quality.flags = (quality.flags or []) + [f'duplicate:{duplicate_score:.3f}']
            q.is_duplicate = True
            q.duplicate_of_question_id = duplicate_id
            q.duplicate_score = float(duplicate_score or 0)
        else:
            q.is_duplicate = False
            q.duplicate_of_question_id = None
            q.duplicate_score = None

        q.repair_attempt_count = int(q.repair_attempt_count or 0) + 1
        q.quality_score = quality.score
        flags = list(quality.flags or [])
        if randomized.changed and 'answer_randomized' not in flags:
            flags.append('answer_randomized')
        q.quality_flags = flags if quality.passed else (flags or [quality.reason])
        q.draft_error_reason, q.draft_error_detail = self._quality_error_payload(quality, q.duplicate_of_question_id, q.duplicate_score or 0)
        q.status = 'pending_review' if quality.passed else 'draft_error'
        if q.status != 'draft_error':
            q.draft_error_reason = None
            q.draft_error_detail = None
        q.updated_at = datetime.utcnow()
        self.db.add(QuestionReviewLog(question_id=q.id, old_status='draft_error', new_status=q.status, actor=actor, note=note))
        reconcile_question_families(self.db, q.course_id, chapter_node_id=q.chapter_node_id, commit=False)
        DuplicateDetector(self.db).save_embedding(q)
        self.db.commit()
        self.db.refresh(q)
        return q

    def keep_draft_error_anyway(self, question_id: str, actor: str, note: str = 'Teacher kept draft_error anyway') -> Question:
        q = self.get_or_raise(question_id)
        if q.status != 'draft_error':
            return q
        old = q.status
        q.status = 'pending_review'
        q.quality_flags = list((q.quality_flags or [])) + ['kept_anyway_by_teacher']
        q.draft_error_detail = {**(q.draft_error_detail or {}), 'kept_anyway_by': actor, 'kept_anyway_note': note}
        q.updated_at = datetime.utcnow()
        self.db.add(QuestionReviewLog(question_id=q.id, old_status=old, new_status=q.status, actor=actor, note=note))
        self.db.commit()
        self.db.refresh(q)
        return q

    def diversity_report(self, *, course_id: str) -> dict:
        questions = self.db.query(Question).filter(Question.course_id == course_id).all()
        return diversity_report(questions)

    def delete_question(self, question_id: str, actor: str = 'teacher') -> dict:
        q = self.get_or_raise(question_id)
        if q.status == 'published':
            raise ValueError('Published question cannot be deleted from AI Server because it may already exist in Open edX. Remove/unpublish it in Open edX first, then handle the local record separately.')

        self.db.query(QuestionEmbedding).filter(QuestionEmbedding.question_id == q.id).delete(synchronize_session=False)
        self.db.query(QuestionVersion).filter(QuestionVersion.question_id == q.id).delete(synchronize_session=False)
        self.db.query(QuestionReviewLog).filter(QuestionReviewLog.question_id == q.id).delete(synchronize_session=False)
        self.db.delete(q)
        self.db.commit()
        return {'deleted': True, 'question_id': question_id, 'actor': actor}

    def bulk_approve(self, *, actor: str, note: str = '', question_ids: list[str] | None = None, course_id: str | None = None, approve_all_pending: bool = False, user: UserContext | None = None) -> dict:
        query = self.db.query(Question)
        if user is not None:
            query = restrict_query_to_courses(query, Question, user)
        if approve_all_pending:
            if not course_id:
                raise ValueError('course_id is required when approve_all_pending=true')
            query = query.filter(Question.course_id == course_id, Question.status == 'pending_review')
            candidates = query.all()
        else:
            if not question_ids:
                raise ValueError('question_ids is required')
            candidates = query.filter(Question.id.in_(question_ids)).all()
            if user is not None:
                for q in candidates:
                    ensure_course_access(user, q.course_id)

        approved: list[str] = []
        skipped: list[dict] = []
        now = datetime.utcnow()
        for q in candidates:
            if q.status != 'pending_review':
                skipped.append({'id': q.id, 'reason': f'status={q.status}'})
                continue
            old = q.status
            q.status = 'approved'
            q.reviewed_by = actor
            q.reviewed_at = now
            q.updated_at = now
            self.db.add(QuestionReviewLog(question_id=q.id, old_status=old, new_status='approved', actor=actor, note=note or 'Bulk approve'))
            approved.append(q.id)
        self.db.commit()
        return {'approved_count': len(approved), 'approved_ids': approved, 'skipped': skipped}
