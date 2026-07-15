from __future__ import annotations

import hashlib
import json
import re
import uuid
import unicodedata
from pathlib import Path
from datetime import datetime, timedelta
from difflib import SequenceMatcher
from typing import Any

from sqlalchemy import func, or_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.course import CourseSyncState
from app.models.question import Question, QuestionReviewLog
from app.models.cost import BudgetPolicy
from app.models.question_bank import (
    BankChapterStats,
    BankOperationJob,
    BankQuestionFamily,
    BankReleaseQuestion,
    BankVersionDiff,
    BankVersionDiffItem,
    Department,
    EdxCourseChapterMapping,
    EdxCourseMapping,
    LearningMaterialVersion,
    MaterialChunk,
    ConceptVersion,
    QuestionBankRelease,
    QuestionBankVersion,
    QuizBlueprint,
    CourseQuizInstance,
    QuestionSearchDocument,
    Subject,
    SubjectOffering,
    SubjectChapter,
)
from app.modules.openedx_connector.factory import get_openedx_connector
from app.services.openedx_exporter import question_to_openedx_olx
from app.services.answer_randomizer import normalize_and_shuffle_options
from app.services.chunker import Chunker
from app.services.content_extractor import ContentExtractor
from app.services.cost_control import CostControlService
from app.services.generation_cache import question_fingerprint, sha256_text
from app.services.model_gateway import ModelGateway
from app.services.quality_checker import QualityChecker
from app.services.question_family import build_question_family_id, normalize_difficulty
from app.services.token_counter import count_tokens
from app.services.source_chunk_refs import join_source_chunk_ids, split_source_chunk_ids
from app.services.bank_dashboard_stats import BankDashboardStatsService
from app.services.bank_search import BankSearchService


from app.services.question_bank.release_publish import QuestionBankReleasePublishWorkflowService
from app.services.question_bank.quiz_creation import QuestionBankQuizCreationWorkflowService
from app.services.question_bank.generation_review import QuestionBankGenerationReviewWorkflowService
from app.services.question_bank.helpers import (
    AUTO_RETIRE_MIN_EVIDENCE_CHARS,
    AUTO_RETIRE_MIN_TOKEN_COUNT,
    AUTO_RETIRE_STRONG_CHUNK_SIMILARITY,
    AUTO_RETIRE_TOKEN_OVERLAP_THRESHOLD,
    BANK_UPLOAD_ALLOWED_EXTENSIONS,
    BANK_UPLOAD_LEGACY_OFFICE_EXTENSIONS,
    BANK_UPLOAD_MAX_BYTES,
    TERM_SEASON_LABELS,
    _bounded_similarity,
    _check,
    _evidence_tokens,
    _token_overlap_ratio,
    _ui_notice,
    bank_material_storage_dir,
    bank_text_similarity,
    chunk_policy_for_material_source,
    extract_block_course_tuple,
    extract_chapter_number,
    normalize_academic_term_code,
    normalize_code,
    normalize_question_text_for_diff,
    normalize_text,
    normalize_title_match,
    parse_openedx_course_id,
    question_lineage_root,
    safe_upload_filename,
    slugify,
    stable_concept_identity,
    title_similarity,
    upload_extension,
)
class VersionedQuestionBankService:
    """Question Bank-first service.

    v25.9.15.1 keeps mapping and publish deterministic. It never guesses a
    mapping silently: course/subject/release/chapter are checked before DB write.
    A Bank Release is only marked ``published`` after the release's questions
    are imported into its own Open edX Content Library.
    """

    def __init__(self, db: Session):
        self.db = db

    def summary(self) -> dict:
        stat_row = self.db.query(
            func.coalesce(func.sum(BankChapterStats.total_questions), 0),
            func.coalesce(func.sum(BankChapterStats.retired_count), 0),
            func.coalesce(func.sum(BankChapterStats.carry_over_count), 0),
        ).one()
        bank_questions = int(stat_row[0] or 0)
        retired_questions = int(stat_row[1] or 0)
        carry_over_questions = int(stat_row[2] or 0)
        return {
            'departments': self.db.query(Department).count(),
            'subjects': self.db.query(Subject).count(),
            'subject_offerings': self.db.query(SubjectOffering).count(),
            'chapters': self.db.query(SubjectChapter).count(),
            'bank_versions': self.db.query(QuestionBankVersion).count(),
            'releases': self.db.query(QuestionBankRelease).count(),
            'published_releases': self.db.query(QuestionBankRelease).filter(QuestionBankRelease.status == 'published').count(),
            'course_mappings': self.db.query(EdxCourseMapping).count(),
            'quiz_blueprints': self.db.query(QuizBlueprint).count(),
            'material_versions': self.db.query(LearningMaterialVersion).count(),
            'material_chunks': self.db.query(MaterialChunk).count(),
            # v25.9.16.5.21: dashboard-scale totals come from the 15k-row
            # ai_bank_chapter_stats table instead of counting ai_questions.
            'bank_questions': bank_questions,
            'bank_diffs': self.db.query(BankVersionDiff).count(),
            'carry_over_questions': carry_over_questions,
            'retired_questions': retired_questions,
        }


    # v25.9.15.6.9 - Teacher guidance dashboard helpers
    BANK_PENDING_STATUSES = {'pending_review', 'needs_review'}
    BANK_ERROR_STATUSES = {'draft_error'}
    BANK_APPROVED_STATUSES = {'approved', 'published'}

    def _bank_question_status_counts(self, questions: list[Question]) -> dict:
        active = [q for q in questions if not bool(q.is_retired)]
        approved = [q for q in active if q.status in self.BANK_APPROVED_STATUSES]
        pending = [q for q in active if q.status in self.BANK_PENDING_STATUSES]
        draft_error = [q for q in active if q.status in self.BANK_ERROR_STATUSES]
        rejected = [q for q in active if q.status == 'rejected']
        unresolved = pending + draft_error
        total = len(active)
        return {
            'total_questions': total,
            'approved_count': len(approved),
            'pending_review_count': len(pending),
            'draft_error_count': len(draft_error),
            'unresolved_count': len(unresolved),
            'rejected_count': len(rejected),
            'is_review_done': bool(approved) and not unresolved,
            'has_questions': bool(active),
            'status': 'ready' if bool(approved) and not unresolved else ('needs_fix' if draft_error else ('needs_review' if pending else ('empty' if not active else 'not_ready'))),
        }

    def _chapter_question_limit_default(self) -> int:
        # Bank-first quota: one global limit per Bài/Chapter. Reuse the legacy
        # BudgetPolicy table without migration by storing it as scope='chapter'.
        policy = self.db.query(BudgetPolicy).filter(
            BudgetPolicy.scope == 'chapter',
            BudgetPolicy.scope_id == 'default',
            BudgetPolicy.is_active == True,
        ).first()
        if not policy:
            # Compatibility fallback for older installs that only had one global
            # course policy from the old course-first UI. Treat the global/default
            # course policy as the chapter policy; do not pick arbitrary course IDs.
            policy = self.db.query(BudgetPolicy).filter(
                BudgetPolicy.scope == 'course',
                BudgetPolicy.scope_id.in_(['__bank_chapter_default__', 'default']),
                BudgetPolicy.is_active == True,
            ).first()
        if policy:
            return max(1, int(policy.max_questions_per_course or 100))
        return 100

    def _dashboard_stats(self) -> BankDashboardStatsService:
        return BankDashboardStatsService(self.db)

    def _invalidate_dashboard_cache(self) -> None:
        try:
            self._dashboard_stats().invalidate_cache()
        except Exception:
            pass

    def _search_index(self) -> BankSearchService:
        return BankSearchService(self.db)

    def _release_publish_workflow(self) -> QuestionBankReleasePublishWorkflowService:
        return QuestionBankReleasePublishWorkflowService(self)

    def _safe_refresh_chapter_stats(self, chapter_id: str | None) -> None:
        if not chapter_id:
            return
        try:
            self._dashboard_stats().rebuild_chapter_stats(chapter_id=chapter_id, commit=True)
            # v25.9.15.6.35: keep question search docs current for the same
            # chapter. This path is best-effort and bounded by chapter size.
            self._search_index().refresh_for_chapter(chapter_id, commit=True)
        except Exception:
            # Stats/search refresh must not break teacher workflows after the main
            # transaction has already succeeded. Admin can repair via
            # /admin/stats/rebuild and /admin/search/rebuild.
            try:
                self.db.rollback()
            except Exception:
                pass

    def _safe_refresh_bank_version_stats(self, bank_version_id: str | None) -> None:
        if not bank_version_id:
            return
        try:
            self._dashboard_stats().refresh_for_bank_version(bank_version_id, commit=True)
            self._search_index().refresh_for_bank_version(bank_version_id, commit=True)
        except Exception:
            try:
                self.db.rollback()
            except Exception:
                pass

    def _bank_version_is_published_locked(self, version: QuestionBankVersion) -> bool:
        if (version.status or '').lower() == 'published' or version.published_at is not None:
            return True
        return self.db.query(QuestionBankRelease.id).filter(
            QuestionBankRelease.bank_version_id == version.id,
            QuestionBankRelease.status == 'published',
        ).first() is not None

    def _raise_if_published_locked(self, version: QuestionBankVersion, *, action: str = 'thao tác này') -> None:
        if self._bank_version_is_published_locked(version):
            raise ValueError(f'Bài này đã publish sang Open edX Library; {action} đã bị khóa. Hãy clone/tạo version mới nếu cần chỉnh sửa.')

    @staticmethod
    def _summary_entity(item) -> dict:
        data = {}
        for key in (
            'id', 'code', 'name', 'description', 'status', 'department_id',
            'subject_id', 'subject_offering_id', 'chapter_no', 'title',
            'sort_order', 'term', 'version_code', 'based_on_offering_id',
            'created_by', 'approved_by',
        ):
            if hasattr(item, key):
                value = getattr(item, key)
                if isinstance(value, datetime):
                    value = value.isoformat()
                data[key] = value
        for key in ('created_at', 'updated_at', 'published_at'):
            if hasattr(item, key):
                value = getattr(item, key)
                data[key] = value.isoformat() if isinstance(value, datetime) else value
        return data

    def _chapter_stats_map(self) -> dict[str, dict]:
        return self._dashboard_stats().chapter_stats_map()

    def _offering_summary_map(self, chapter_stats: dict[str, dict] | None = None) -> dict[str, dict]:
        return self._dashboard_stats().offering_summary_map(chapter_stats)

    def _subject_summary_map(self, offering_stats: dict[str, dict] | None = None) -> dict[str, dict]:
        return self._dashboard_stats().subject_summary_map(offering_stats)

    def _department_summary_map(self, subject_stats: dict[str, dict] | None = None) -> dict[str, dict]:
        return self._dashboard_stats().department_summary_map(subject_stats)

    def dashboard_overview(self) -> dict:
        return self._dashboard_stats().dashboard_overview(use_cache=True)

    def _build_dashboard_next_actions(self, chapter_stats: dict[str, dict]) -> list[dict]:
        return self._dashboard_stats().build_dashboard_next_actions(chapter_stats)

    def department_summaries(self) -> list[dict]:
        cache_key = 'bank_department_summary:v1'
        chapters = self.db.query(SubjectChapter.id).all()
        heal = self._dashboard_stats().ensure_chapter_stats([row[0] for row in chapters], max_rebuild=500)
        cached = self._dashboard_stats()._cache_get(cache_key)
        if cached is not None and not heal.get('rebuilt_count'):
            return cached
        stats = self._department_summary_map()
        departments = self.db.query(Department).order_by(Department.code.asc()).all()
        payload = [{'department': self._summary_entity(d), 'stats': stats.get(d.id, {})} for d in departments]
        self._dashboard_stats()._cache_set(cache_key, payload)
        return payload

    def subject_summaries(self, *, department_id: str) -> list[dict]:
        cache_key = f'bank_subject_summary:{department_id}'
        subject_ids = [row[0] for row in self.db.query(Subject.id).filter(Subject.department_id == department_id).all()]
        chapter_ids = [row[0] for row in self.db.query(SubjectChapter.id).filter(SubjectChapter.subject_id.in_(subject_ids)).all()] if subject_ids else []
        heal = self._dashboard_stats().ensure_chapter_stats(chapter_ids, max_rebuild=500)
        cached = self._dashboard_stats()._cache_get(cache_key)
        if cached is not None and not heal.get('rebuilt_count'):
            return cached
        stats = self._subject_summary_map()
        subjects = self.db.query(Subject).filter(Subject.department_id == department_id).order_by(Subject.code.asc()).all()
        payload = [{'subject': self._summary_entity(s), 'stats': stats.get(s.id, {})} for s in subjects]
        self._dashboard_stats()._cache_set(cache_key, payload)
        return payload

    def subject_version_summaries(self, *, subject_id: str) -> list[dict]:
        cache_key = f'bank_offering_summary:{subject_id}'
        chapter_ids = [row[0] for row in self.db.query(SubjectChapter.id).filter(SubjectChapter.subject_id == subject_id).all()]
        heal = self._dashboard_stats().ensure_chapter_stats(chapter_ids, max_rebuild=500)
        cached = self._dashboard_stats()._cache_get(cache_key)
        if cached is not None and not heal.get('rebuilt_count'):
            return cached
        stats = self._offering_summary_map()
        offerings = self.db.query(SubjectOffering).filter(SubjectOffering.subject_id == subject_id).order_by(SubjectOffering.code.asc()).all()
        payload = [{'subject_version': self._summary_entity(o), 'stats': stats.get(o.id, {})} for o in offerings]
        self._dashboard_stats()._cache_set(cache_key, payload)
        return payload

    def chapter_summaries(self, *, subject_offering_id: str) -> list[dict]:
        cache_key = f'bank_chapter_summary:{subject_offering_id}'
        chapters = self.db.query(SubjectChapter).filter(SubjectChapter.subject_offering_id == subject_offering_id).order_by(SubjectChapter.sort_order.asc(), SubjectChapter.chapter_no.asc()).all()
        heal = self._dashboard_stats().ensure_chapter_stats([c.id for c in chapters], max_rebuild=500)
        cached = self._dashboard_stats()._cache_get(cache_key)
        if cached is not None and not heal.get('rebuilt_count'):
            return cached
        stats = self._chapter_stats_map()
        payload = [{'chapter': self._summary_entity(c), 'stats': stats.get(c.id, {})} for c in chapters]
        self._dashboard_stats()._cache_set(cache_key, payload)
        return payload

    def dashboard_search(self, *, q: str, limit: int = 20, user: Any | None = None) -> list[dict]:
        # v25.9.15.6.35: dashboard quick search now delegates to the Bank
        # Search Engine. It returns the legacy flat list so existing UI keeps
        # working while /api/question-bank-v2/search exposes grouped results.
        result = self._search_index().search_grouped(q=q, user=user, limit=limit, include_questions=True)
        return list(result.get('items') or [])

    def create_department(self, *, code: str, name: str, description: str = '') -> Department:
        item = Department(id=str(uuid.uuid4()), code=code.strip().upper(), name=name.strip(), description=description or '')
        self.db.add(item)
        self.db.commit()
        self.db.refresh(item)
        self._invalidate_dashboard_cache()
        return item

    def create_subject(self, *, department_id: str, code: str, name: str, description: str = '') -> Subject:
        item = Subject(id=str(uuid.uuid4()), department_id=department_id, code=code.strip().upper(), name=name.strip(), description=description or '')
        self.db.add(item)
        self.db.commit()
        self.db.refresh(item)
        self._invalidate_dashboard_cache()
        return item

    def create_subject_offering(
        self,
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
        """Create a subject-version offering such as DOM123_SP25.

        In the product language, ``phiên bản môn`` is the version layer of a subject.
        FPT-style terms are normalized to SP/SU/FA + 2-digit year, e.g.
        SP25 = Spring 2025, SU26 = Summer 2026, FA27 = Fall 2027.

        A new offering can be cloned from another offering. Clone is an exact
        working-copy operation: the new term gets new DB rows for chapters, bank
        versions, materials, chunks, concepts, families, and reusable approved
        questions. Release/Open edX Library records are intentionally not cloned;
        teachers create a new Release manually only after they finish editing.
        """
        subject = self.db.get(Subject, subject_id)
        if not subject:
            raise ValueError('Không tìm thấy môn học')

        source_offering_id = clone_from_offering_id or based_on_offering_id
        source_offering = self.db.get(SubjectOffering, source_offering_id) if source_offering_id else None
        if source_offering_id and (not source_offering or source_offering.subject_id != subject_id):
            raise ValueError('Phiên bản môn nguồn không thuộc môn đã chọn')

        term_info = normalize_academic_term_code(term=term, season=season, year=year, code=code or term or version_code)
        term_code = str(term_info['term_code'])
        existing_term = self.db.query(SubjectOffering).filter(
            SubjectOffering.subject_id == subject.id,
            func.upper(SubjectOffering.term) == term_code.upper(),
        ).first()
        if existing_term:
            raise ValueError(f'Mỗi học kỳ chỉ có một phiên bản môn cuối. {subject.code}_{term_code} đã tồn tại.')
        offering_code = (code or f'{subject.code}_{term_code}').strip().upper()
        if not offering_code.startswith(subject.code.upper()):
            # Keep the course code visible in the record to reduce mapping mistakes.
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
            },
        )
        self.db.add(item)
        self.db.flush()

        clone_result = None
        if source_offering:
            clone_result = self._clone_subject_offering_content(
                source=source_offering,
                target=item,
                actor=actor,
            )
            item.metadata_json = {**(item.metadata_json or {}), 'cloned_from_offering_id': source_offering.id, 'clone_result': clone_result}

        self.db.commit()
        self.db.refresh(item)
        self._invalidate_dashboard_cache()
        return item

    def _clone_subject_offering_content(
        self,
        *,
        source: SubjectOffering,
        target: SubjectOffering,
        actor: str | None = None,
    ) -> dict:
        """Clone an exact working snapshot into a new subject-version.

        Product rule: clone version môn means copy the current working content
        100% into a new term/version with fresh IDs. It does not run diff, does
        not create/publish a Release, and does not reuse Open edX component IDs.
        Release is a manual button after teachers finish editing the new term.
        """
        chapter_map: dict[str, SubjectChapter] = {}
        bank_map: dict[str, QuestionBankVersion] = {}
        material_map: dict[str, LearningMaterialVersion] = {}
        chunk_map: dict[str, str] = {}
        concept_map: dict[str, ConceptVersion] = {}
        family_map: dict[str, BankQuestionFamily] = {}
        counts = {'chapters': 0, 'bank_versions': 0, 'materials': 0, 'chunks': 0, 'concepts': 0, 'families': 0, 'questions': 0, 'releases_not_cloned': 0}

        for src in self.db.query(SubjectChapter).filter(SubjectChapter.subject_offering_id == source.id).order_by(SubjectChapter.sort_order.asc(), SubjectChapter.chapter_no.asc()).all():
            dst = SubjectChapter(
                    id=str(uuid.uuid4()),
                    subject_id=target.subject_id,
                    subject_offering_id=target.id,
                    chapter_no=src.chapter_no,
                    title=src.title,
                    description=src.description,
                    sort_order=src.sort_order,
                    status=src.status,
            )
            self.db.add(dst)
            self.db.flush()
            chapter_map[src.id] = dst
            counts['chapters'] += 1

        for src_bv in self.db.query(QuestionBankVersion).filter(QuestionBankVersion.subject_offering_id == source.id).order_by(QuestionBankVersion.created_at.asc()).all():
            dst_chapter = chapter_map.get(src_bv.chapter_id)
            if not dst_chapter:
                continue
            dst_status = 'approved' if src_bv.status in {'published', 'approved'} else 'draft'
            clone_title = f'{target.code} - {self._chapter_display_name(dst_chapter)} - {src_bv.version_code}'
            dst_bv = QuestionBankVersion(
                id=str(uuid.uuid4()),
                subject_id=target.subject_id,
                chapter_id=dst_chapter.id,
                subject_offering_id=target.id,
                version_no=src_bv.version_no,
                version_code=src_bv.version_code,
                title=clone_title,
                change_note=f'Clone từ {source.code}: {src_bv.change_note or ""}'.strip(),
                status=dst_status,
                based_on_version_id=src_bv.id,
                created_by=actor,
                approved_by=actor if dst_status == 'approved' else None,
                published_at=None,
                metadata_json={
                    **(src_bv.metadata_json or {}),
                    'cloned_from_bank_version_id': src_bv.id,
                    'cloned_from_offering_id': source.id,
                    'clone_policy': 'exact_working_copy_new_records_no_shared_ids',
                    'release_policy': 'release_not_cloned_create_manually_after_editing',
                    'release_cloned': False,
                    'diff_policy': 'only_when_material_changes_after_clone',
                    'document_change_state': 'unchanged_after_clone',
                    'diff_required': False,
                    'diff_base_bank_version_id': src_bv.id,
                },
            )
            self.db.add(dst_bv)
            self.db.flush()
            bank_map[src_bv.id] = dst_bv
            counts['bank_versions'] += 1

            for src_mat in self.db.query(LearningMaterialVersion).filter(LearningMaterialVersion.bank_version_id == src_bv.id).order_by(LearningMaterialVersion.created_at.asc()).all():
                dst_mat = LearningMaterialVersion(
                        id=str(uuid.uuid4()),
                        subject_id=target.subject_id,
                        chapter_id=dst_chapter.id,
                        subject_offering_id=target.id,
                        bank_version_id=dst_bv.id,
                        title=src_mat.title,
                        file_name=src_mat.file_name,
                        file_type=src_mat.file_type,
                        storage_path=src_mat.storage_path,
                        content_hash=src_mat.content_hash,
                        version_no=src_mat.version_no,
                        change_type='cloned_unchanged',
                        uploaded_by=actor or src_mat.uploaded_by,
                        status=src_mat.status,
                )
                self.db.add(dst_mat)
                self.db.flush()
                material_map[src_mat.id] = dst_mat
                counts['materials'] += 1
                for src_chunk in self.db.query(MaterialChunk).filter(MaterialChunk.material_version_id == src_mat.id).order_by(MaterialChunk.chunk_index.asc()).all():
                    dst_chunk = MaterialChunk(
                            id=str(uuid.uuid4()),
                            material_version_id=dst_mat.id,
                            bank_version_id=dst_bv.id,
                            subject_id=target.subject_id,
                            chapter_id=dst_chapter.id,
                            subject_offering_id=target.id,
                            chunk_index=src_chunk.chunk_index,
                            content=src_chunk.content,
                            token_count=src_chunk.token_count,
                            source_type=src_chunk.source_type,
                            page_number=src_chunk.page_number,
                            source_ref=src_chunk.source_ref,
                            content_hash=src_chunk.content_hash,
                    )
                    self.db.add(dst_chunk)
                    chunk_map[src_chunk.id] = dst_chunk.id
                    counts['chunks'] += 1

            for src_concept in self.db.query(ConceptVersion).filter(ConceptVersion.bank_version_id == src_bv.id).order_by(ConceptVersion.created_at.asc()).all():
                dst_concept = ConceptVersion(
                    id=str(uuid.uuid4()),
                    bank_version_id=dst_bv.id,
                    subject_id=target.subject_id,
                    chapter_id=dst_chapter.id,
                    subject_offering_id=target.id,
                    material_version_id=material_map.get(src_concept.material_version_id).id if src_concept.material_version_id in material_map else None,
                    concept_key=src_concept.concept_key,
                    concept_title=src_concept.concept_title,
                    description=src_concept.description,
                    learning_objective=src_concept.learning_objective,
                    source_evidence=src_concept.source_evidence,
                    source_chunk_hash=src_concept.source_chunk_hash,
                    status=src_concept.status,
                )
                self.db.add(dst_concept)
                self.db.flush()
                concept_map[src_concept.id] = dst_concept
                counts['concepts'] += 1

            for src_family in self.db.query(BankQuestionFamily).filter(BankQuestionFamily.bank_version_id == src_bv.id).order_by(BankQuestionFamily.created_at.asc()).all():
                dst_family = BankQuestionFamily(
                    id=str(uuid.uuid4()),
                    bank_version_id=dst_bv.id,
                    subject_id=target.subject_id,
                    chapter_id=dst_chapter.id,
                    subject_offering_id=target.id,
                    concept_version_id=concept_map.get(src_family.concept_version_id).id if src_family.concept_version_id in concept_map else None,
                    difficulty=src_family.difficulty,
                    family_key=src_family.family_key,
                    family_title=src_family.family_title,
                    family_fingerprint=src_family.family_fingerprint,
                    status=src_family.status,
                )
                self.db.add(dst_family)
                self.db.flush()
                family_map[src_family.id] = dst_family
                counts['families'] += 1

            questions = self.db.query(Question).filter(
                Question.bank_version_id == src_bv.id,
                Question.status.in_(['approved', 'published']),
                or_(Question.is_retired.is_(False), Question.is_retired.is_(None)),
                Question.is_duplicate.is_(False),
            ).order_by(Question.created_at.asc()).all()
            for src_q in questions:
                dst_concept = concept_map.get(src_q.concept_version_id)
                # Resolve family by fingerprint/key because older question rows store only question_family_id.
                dst_family = None
                for fam in family_map.values():
                    if fam.family_key == src_q.question_family_id or fam.family_key == getattr(src_q, 'question_family_id', None):
                        dst_family = fam
                        break
                new_q = Question(
                    id=str(uuid.uuid4()),
                    course_id=f'bank:{dst_bv.id}',
                    source_course_id=src_q.source_course_id,
                    department_id=target.department_id,
                    subject_id=target.subject_id,
                    subject_chapter_id=dst_chapter.id,
                    bank_version_id=dst_bv.id,
                    bank_release_id=None,
                    previous_question_id=src_q.id,
                    lineage_root_question_id=question_lineage_root(src_q),
                    question_revision_no=int(src_q.question_revision_no or 1) + 1,
                    is_carry_over=True,
                    is_retired=False,
                    material_version_id=material_map.get(src_q.material_version_id).id if src_q.material_version_id in material_map else None,
                    concept_version_id=dst_concept.id if dst_concept else None,
                    lesson_id=src_q.lesson_id,
                    lesson_title=src_q.lesson_title,
                    block_id=f'bank-version:{dst_bv.id}',
                    topic_id=src_q.topic_id,
                    topic=src_q.topic,
                    concept_id=dst_concept.id if dst_concept else src_q.concept_id,
                    concept_title=dst_concept.concept_title if dst_concept else src_q.concept_title,
                    concept_key=dst_concept.concept_key if dst_concept else src_q.concept_key,
                    question_family_id=dst_family.family_key if dst_family else src_q.question_family_id,
                    variant_no=src_q.variant_no,
                    source_evidence=src_q.source_evidence,
                    difficulty=normalize_difficulty(src_q.difficulty),
                    cognitive_level=src_q.cognitive_level,
                    learning_objective=src_q.learning_objective,
                    question_type=src_q.question_type,
                    question_text=src_q.question_text,
                    question_hash=src_q.question_hash,
                    option_a=src_q.option_a,
                    option_b=src_q.option_b,
                    option_c=src_q.option_c,
                    option_d=src_q.option_d,
                    correct_answer=src_q.correct_answer,
                    explanation=src_q.explanation,
                    source_ref=f'term-clone:{source.id}:{src_q.id}',
                    source_type='subject_offering_clone',
                    source_page=src_q.source_page,
                    source_timestamp_start=src_q.source_timestamp_start,
                    source_timestamp_end=src_q.source_timestamp_end,
                    source_chunk_id=join_source_chunk_ids([chunk_map.get(cid, cid) for cid in split_source_chunk_ids(src_q.source_chunk_id)]),
                    source_node_id=f'bank-version:{dst_bv.id}',
                    source_node_title=f'Clone từ {source.code}',
                    chapter_node_id=dst_chapter.id,
                    chapter_title=dst_chapter.title,
                    target_library_id=None,
                    target_library_key=None,
                    source_excerpt=src_q.source_excerpt,
                    tags=list(src_q.tags or []) + ['term-clone', f'from:{source.code}', f'to:{target.code}'],
                    ai_rationale=src_q.ai_rationale,
                    quality_score=src_q.quality_score,
                    quality_flags=list(src_q.quality_flags or []) + ['cloned_from_previous_subject_offering'],
                    draft_error_reason=None,
                    draft_error_detail=None,
                    repair_attempt_count=0,
                    is_duplicate=False,
                    duplicate_of_question_id=None,
                    duplicate_score=None,
                    generation_job_id=None,
                    model_provider=src_q.model_provider,
                    model_name=src_q.model_name,
                    status='approved',
                    version=1,
                    reviewed_by=actor,
                    reviewed_at=datetime.utcnow(),
                    published_at=None,
                    openedx_block_id=None,
                    openedx_library_problem_id=None,
                    imported_library_at=None,
                    publish_error=None,
                    publish_status=None,
                    publish_verification_json=None,
                    published_by=None,
                    openedx_publish_status=None,
                    openedx_verification_status=None,
                    openedx_delete_status=None,
                    openedx_manual_action_required=False,
                )
                self.db.add(new_q)
                counts['questions'] += 1

        counts['releases_not_cloned'] = self.db.query(QuestionBankRelease).filter(QuestionBankRelease.subject_offering_id == source.id).count()
        return {
            **counts,
            'clone_mode': 'exact_working_copy',
            'release_policy': 'Release không clone theo version môn; giáo viên bấm Chốt Release sau khi sửa xong.',
            'diff_policy': 'Không diff khi clone; chỉ diff khi tài liệu ở version mới bị thay đổi.',
        }

    def _chapter_display_name(self, chapter: SubjectChapter | None) -> str:
        if not chapter:
            return 'Bài'
        return (chapter.title or '').strip() or 'Bài'

    def _chapter_quiz_suffix(self, chapter: SubjectChapter | None) -> str:
        title = self._chapter_display_name(chapter)
        cleaned = re.sub(r'^\s*bài\s*', '', title, flags=re.IGNORECASE).strip()
        return cleaned or title or '1'

    def _next_chapter_order(self, *, subject_id: str, subject_offering_id: str | None = None) -> int:
        query = self.db.query(func.max(SubjectChapter.sort_order)).filter(SubjectChapter.subject_id == subject_id)
        if subject_offering_id:
            query = query.filter(SubjectChapter.subject_offering_id == subject_offering_id)
        value = query.scalar()
        return int(value or 0) + 1

    def create_chapter(self, *, subject_id: str, title: str, chapter_no: int | None = None, description: str = '', sort_order: int | None = None, subject_offering_id: str | None = None) -> SubjectChapter:
        if subject_offering_id:
            offering = self.db.get(SubjectOffering, subject_offering_id)
            if not offering or offering.subject_id != subject_id:
                raise ValueError('Phiên bản môn không thuộc môn đã chọn')
        clean_title = (title or '').strip()
        if not clean_title:
            raise ValueError('Vui lòng nhập bài')
        next_order = sort_order or self._next_chapter_order(subject_id=subject_id, subject_offering_id=subject_offering_id)
        internal_no = chapter_no or next_order
        item = SubjectChapter(id=str(uuid.uuid4()), subject_id=subject_id, subject_offering_id=subject_offering_id, chapter_no=internal_no, title=clean_title, description=description or '', sort_order=next_order)
        self.db.add(item)
        self.db.commit()
        self.db.refresh(item)
        self._safe_refresh_chapter_stats(item.id)
        self._invalidate_dashboard_cache()
        return item


    def _empty_block_message(self, *, entity_label: str, counts: dict[str, int]) -> str | None:
        used = {key: int(value or 0) for key, value in counts.items() if int(value or 0) > 0}
        if not used:
            return None
        human = {
            'subjects': 'môn',
            'subject_versions': 'phiên bản môn',
            'chapters': 'bài/chapter',
            'bank_versions': 'bank version',
            'materials': 'tài liệu',
            'chunks': 'chunk nội dung',
            'concepts': 'concept',
            'families': 'family',
            'questions': 'câu hỏi',
            'releases': 'Release',
            'course_mappings': 'mapping course',
            'chapter_mappings': 'mapping bài Open edX',
            'quiz_blueprints': 'blueprint quiz',
            'quiz_instances': 'Quiz Open edX đã tạo',
        }
        parts = [f"{human.get(key, key)}: {value}" for key, value in used.items()]
        return f'Không thể xóa {entity_label} vì vẫn còn dữ liệu liên kết ({"; ".join(parts)}). Hãy xóa tài liệu, câu hỏi, release, mapping hoặc quiz trước rồi thử lại.'

    def update_department(self, department_id: str, *, code: str | None = None, name: str | None = None, description: str | None = None) -> Department:
        item = self.db.get(Department, department_id)
        if not item:
            raise ValueError('Không tìm thấy bộ môn')
        if code is not None:
            clean = code.strip().upper()
            if not clean:
                raise ValueError('Mã bộ môn không được để trống')
            exists = self.db.query(Department).filter(Department.code == clean, Department.id != item.id).first()
            if exists:
                raise ValueError('Mã bộ môn đã tồn tại')
            item.code = clean
        if name is not None:
            clean_name = name.strip()
            if not clean_name:
                raise ValueError('Tên bộ môn không được để trống')
            item.name = clean_name
        if description is not None:
            item.description = description or ''
        item.updated_at = datetime.utcnow()
        self.db.commit(); self.db.refresh(item)
        self._invalidate_dashboard_cache()
        return item

    def delete_department(self, department_id: str) -> dict:
        item = self.db.get(Department, department_id)
        if not item:
            raise ValueError('Không tìm thấy bộ môn')
        msg = self._empty_block_message(entity_label='bộ môn', counts={
            'subjects': self.db.query(Subject).filter(Subject.department_id == department_id).count(),
            'subject_versions': self.db.query(SubjectOffering).filter(SubjectOffering.department_id == department_id).count(),
        })
        if msg:
            raise ValueError(msg)
        self.db.delete(item); self.db.commit()
        self._invalidate_dashboard_cache()
        return {'ok': True, 'deleted': True, 'entity_type': 'department', 'entity_id': department_id, 'message': 'Đã xóa bộ môn'}

    def update_subject(self, subject_id: str, *, code: str | None = None, name: str | None = None, description: str | None = None) -> Subject:
        item = self.db.get(Subject, subject_id)
        if not item:
            raise ValueError('Không tìm thấy môn')
        if code is not None:
            clean = code.strip().upper()
            if not clean:
                raise ValueError('Mã môn không được để trống')
            exists = self.db.query(Subject).filter(Subject.department_id == item.department_id, Subject.code == clean, Subject.id != item.id).first()
            if exists:
                raise ValueError('Mã môn đã tồn tại trong bộ môn này')
            item.code = clean
        if name is not None:
            clean_name = name.strip()
            if not clean_name:
                raise ValueError('Tên môn không được để trống')
            item.name = clean_name
        if description is not None:
            item.description = description or ''
        item.updated_at = datetime.utcnow()
        self.db.commit(); self.db.refresh(item)
        self._invalidate_dashboard_cache()
        return item

    def delete_subject(self, subject_id: str) -> dict:
        item = self.db.get(Subject, subject_id)
        if not item:
            raise ValueError('Không tìm thấy môn')
        msg = self._empty_block_message(entity_label='môn', counts={
            'subject_versions': self.db.query(SubjectOffering).filter(SubjectOffering.subject_id == subject_id).count(),
            'chapters': self.db.query(SubjectChapter).filter(SubjectChapter.subject_id == subject_id).count(),
            'bank_versions': self.db.query(QuestionBankVersion).filter(QuestionBankVersion.subject_id == subject_id).count(),
            'materials': self.db.query(LearningMaterialVersion).filter(LearningMaterialVersion.subject_id == subject_id).count(),
            'chunks': self.db.query(MaterialChunk).filter(MaterialChunk.subject_id == subject_id).count(),
            'concepts': self.db.query(ConceptVersion).filter(ConceptVersion.subject_id == subject_id).count(),
            'families': self.db.query(BankQuestionFamily).filter(BankQuestionFamily.subject_id == subject_id).count(),
            'questions': self.db.query(Question).filter(Question.subject_id == subject_id).count(),
            'releases': self.db.query(QuestionBankRelease).filter(QuestionBankRelease.subject_id == subject_id).count(),
            'course_mappings': self.db.query(EdxCourseMapping).filter(EdxCourseMapping.subject_id == subject_id).count(),
            'quiz_blueprints': self.db.query(QuizBlueprint).filter(QuizBlueprint.subject_id == subject_id).count(),
            'quiz_instances': self.db.query(CourseQuizInstance).filter(CourseQuizInstance.subject_id == subject_id).count(),
        })
        if msg:
            raise ValueError(msg)
        self.db.delete(item); self.db.commit()
        self._invalidate_dashboard_cache()
        return {'ok': True, 'deleted': True, 'entity_type': 'subject', 'entity_id': subject_id, 'message': 'Đã xóa môn'}

    def update_subject_offering(self, subject_offering_id: str, *, code: str | None = None, name: str | None = None, term: str | None = None, version_code: str | None = None, description: str | None = None) -> SubjectOffering:
        item = self.db.get(SubjectOffering, subject_offering_id)
        if not item:
            raise ValueError('Không tìm thấy phiên bản môn')
        subject = self.db.get(Subject, item.subject_id)
        if code is not None:
            clean = code.strip().upper()
            if not clean:
                raise ValueError('Mã version môn không được để trống')
            if subject and not clean.startswith(subject.code.upper()):
                clean = f'{subject.code}_{clean}'
            exists = self.db.query(SubjectOffering).filter(SubjectOffering.subject_id == item.subject_id, SubjectOffering.code == clean, SubjectOffering.id != item.id).first()
            if exists:
                raise ValueError('Mã version môn đã tồn tại trong môn này')
            item.code = clean
        if name is not None:
            item.name = name.strip()
        if term is not None:
            clean_term = term.strip().upper() or None
            if clean_term:
                duplicate_term = self.db.query(SubjectOffering).filter(
                    SubjectOffering.subject_id == item.subject_id,
                    func.upper(SubjectOffering.term) == clean_term,
                    SubjectOffering.id != item.id,
                ).first()
                if duplicate_term:
                    raise ValueError(f'Mỗi học kỳ chỉ có một phiên bản môn cuối. {clean_term} đã tồn tại cho môn này.')
            item.term = clean_term
        if version_code is not None:
            item.version_code = version_code.strip().upper() or (item.term or item.version_code)
        if description is not None:
            meta = dict(item.metadata_json or {})
            meta['description'] = description or ''
            item.metadata_json = meta
        item.updated_at = datetime.utcnow()
        self.db.commit(); self.db.refresh(item)
        self._invalidate_dashboard_cache()
        return item

    def delete_subject_offering(self, subject_offering_id: str) -> dict:
        item = self.db.get(SubjectOffering, subject_offering_id)
        if not item:
            raise ValueError('Không tìm thấy phiên bản môn')
        msg = self._empty_block_message(entity_label='phiên bản môn', counts={
            'chapters': self.db.query(SubjectChapter).filter(SubjectChapter.subject_offering_id == subject_offering_id).count(),
            'bank_versions': self.db.query(QuestionBankVersion).filter(QuestionBankVersion.subject_offering_id == subject_offering_id).count(),
            'materials': self.db.query(LearningMaterialVersion).filter(LearningMaterialVersion.subject_offering_id == subject_offering_id).count(),
            'chunks': self.db.query(MaterialChunk).filter(MaterialChunk.subject_offering_id == subject_offering_id).count(),
            'concepts': self.db.query(ConceptVersion).filter(ConceptVersion.subject_offering_id == subject_offering_id).count(),
            'families': self.db.query(BankQuestionFamily).filter(BankQuestionFamily.subject_offering_id == subject_offering_id).count(),
            'questions': self.db.query(Question).filter(Question.subject_id == item.subject_id, Question.bank_version_id.isnot(None)).join(QuestionBankVersion, Question.bank_version_id == QuestionBankVersion.id).filter(QuestionBankVersion.subject_offering_id == subject_offering_id).count(),
            'releases': self.db.query(QuestionBankRelease).filter(QuestionBankRelease.subject_offering_id == subject_offering_id).count(),
            'course_mappings': self.db.query(EdxCourseMapping).filter(EdxCourseMapping.subject_offering_id == subject_offering_id).count(),
            'quiz_blueprints': self.db.query(QuizBlueprint).filter(QuizBlueprint.subject_offering_id == subject_offering_id).count(),
            'quiz_instances': self.db.query(CourseQuizInstance).filter(CourseQuizInstance.subject_offering_id == subject_offering_id).count(),
        })
        if msg:
            raise ValueError(msg)
        self.db.delete(item); self.db.commit()
        self._invalidate_dashboard_cache()
        return {'ok': True, 'deleted': True, 'entity_type': 'subject_offering', 'entity_id': subject_offering_id, 'message': 'Đã xóa phiên bản môn'}

    def update_chapter(self, chapter_id: str, *, title: str | None = None, description: str | None = None, sort_order: int | None = None) -> SubjectChapter:
        item = self.db.get(SubjectChapter, chapter_id)
        if not item:
            raise ValueError('Không tìm thấy bài/chapter')
        if title is not None:
            clean = title.strip()
            if not clean:
                raise ValueError('Tên bài không được để trống')
            item.title = clean
        if description is not None:
            item.description = description or ''
        if sort_order is not None:
            item.sort_order = sort_order
            item.chapter_no = sort_order
        # If a chapter was renamed after a failed publish, old release/library
        # state must not be reused. Clean non-published releases so publish uses
        # the current chapter title/library key.
        reset_count = self._cleanup_stale_release_keys_for_chapter(chapter=item, reason='chapter_basic_info_updated')
        if reset_count:
            item.description = item.description or ''
        item.updated_at = datetime.utcnow()
        self.db.commit(); self.db.refresh(item)
        self._safe_refresh_chapter_stats(chapter_id)
        self._invalidate_dashboard_cache()
        return item

    def _bank_version_content_counts(self, bank_version_id: str) -> dict[str, int]:
        return {
            'materials': self.db.query(LearningMaterialVersion).filter(LearningMaterialVersion.bank_version_id == bank_version_id, LearningMaterialVersion.status != 'deleted').count(),
            'chunks': self.db.query(MaterialChunk).filter(MaterialChunk.bank_version_id == bank_version_id).count(),
            'concepts': self.db.query(ConceptVersion).filter(ConceptVersion.bank_version_id == bank_version_id).count(),
            'families': self.db.query(BankQuestionFamily).filter(BankQuestionFamily.bank_version_id == bank_version_id).count(),
            'questions': self.db.query(Question).filter(Question.bank_version_id == bank_version_id).count(),
            'releases': self.db.query(QuestionBankRelease).filter(QuestionBankRelease.bank_version_id == bank_version_id).count(),
            'diffs': self.db.query(BankVersionDiff).filter(or_(BankVersionDiff.from_bank_version_id == bank_version_id, BankVersionDiff.to_bank_version_id == bank_version_id)).count(),
            'jobs': self.db.query(BankOperationJob).filter(BankOperationJob.bank_version_id == bank_version_id).count(),
            'derived_bank_versions': self.db.query(QuestionBankVersion).filter(QuestionBankVersion.based_on_version_id == bank_version_id).count(),
        }


    def _safe_delete_material_file(self, material: LearningMaterialVersion) -> dict[str, Any]:
        """Delete the local uploaded file for a material when it is safe.

        Guardrails:
        - only local storage is deleted here; object-store providers need their
          own adapter implementation;
        - the path must resolve under settings.local_storage_path;
        - if another material row still references the same file path, skip it.
        """
        raw_path = (material.storage_path or '').strip()
        if not raw_path:
            return {'deleted': False, 'skipped': False, 'reason': 'empty_storage_path'}
        if (settings.storage_provider or 'local').lower() != 'local':
            return {'deleted': False, 'skipped': True, 'reason': 'non_local_storage_provider'}
        try:
            root = Path(settings.local_storage_path or '/app/.runtime').expanduser().resolve()
            path = Path(raw_path).expanduser()
            if not path.is_absolute():
                path = root / path
            path = path.resolve()
            if root not in path.parents and path != root:
                return {'deleted': False, 'skipped': True, 'reason': 'path_outside_local_storage', 'path': raw_path}
            # Cloned bank versions may share the same storage_path. Do not delete
            # the physical object while another material record still references it.
            refs = self.db.query(LearningMaterialVersion).filter(
                LearningMaterialVersion.id != material.id,
                LearningMaterialVersion.storage_path == raw_path,
            ).count()
            if refs:
                return {'deleted': False, 'skipped': True, 'reason': 'storage_path_still_referenced', 'references': int(refs)}
            if not path.exists():
                return {'deleted': False, 'skipped': False, 'reason': 'file_not_found', 'path': str(path)}
            if path.is_file():
                size = path.stat().st_size
                path.unlink()
                return {'deleted': True, 'skipped': False, 'bytes_deleted': int(size), 'path': str(path)}
            return {'deleted': False, 'skipped': True, 'reason': 'not_a_file', 'path': str(path)}
        except Exception as exc:
            return {'deleted': False, 'skipped': True, 'reason': 'delete_error', 'error': str(exc), 'path': raw_path}

    def _material_dependency_counts(self, material_id: str) -> dict[str, int]:
        return {
            'chunks': int(self.db.query(MaterialChunk).filter(MaterialChunk.material_version_id == material_id).count() or 0),
            'questions': int(self.db.query(Question).filter(Question.material_version_id == material_id).count() or 0),
            'concepts': int(self.db.query(ConceptVersion).filter(ConceptVersion.material_version_id == material_id).count() or 0),
            'diff_items': int(self.db.query(BankVersionDiffItem).filter(
                BankVersionDiffItem.item_type == 'material',
                or_(BankVersionDiffItem.source_id == material_id, BankVersionDiffItem.target_id == material_id),
            ).count() or 0),
            'jobs': int(self.db.query(BankOperationJob).filter(BankOperationJob.material_version_id == material_id).count() or 0),
        }

    def _material_requires_audit_tombstone(self, material: LearningMaterialVersion, counts: dict[str, int] | None = None) -> bool:
        """Return True when deleting the row would lose meaningful lineage.

        Chunks and upload jobs are reproducible/operational data, not audit lineage.
        Questions, concepts and diff items mean the material has been used in bank
        outputs or comparison history, so keep a lightweight tombstone row.
        """
        counts = counts or self._material_dependency_counts(material.id)
        return any(int(counts.get(key) or 0) > 0 for key in ('questions', 'concepts', 'diff_items'))

    def _hard_delete_material_version(self, material: LearningMaterialVersion, *, reason: str = 'unused_material') -> dict[str, Any]:
        counts = self._material_dependency_counts(material.id)
        if self._material_requires_audit_tombstone(material, counts):
            raise ValueError('Không thể xóa cứng tài liệu vì đã được dùng trong câu hỏi/concept/diff. Hãy xóa mềm để giữ lịch sử.')
        file_result = self._safe_delete_material_file(material)
        chunks_deleted = self.db.query(MaterialChunk).filter(MaterialChunk.material_version_id == material.id).delete(synchronize_session=False)
        jobs_detached = self.db.query(BankOperationJob).filter(BankOperationJob.material_version_id == material.id).update(
            {BankOperationJob.material_version_id: None},
            synchronize_session=False,
        )
        bank_version_id = material.bank_version_id
        chapter_id = material.chapter_id
        material_id = material.id
        self.db.delete(material)
        self.db.flush()
        return {
            'ok': True,
            'material_version_id': material_id,
            'bank_version_id': bank_version_id,
            'chapter_id': chapter_id,
            'deletion_mode': 'hard',
            'reason': reason,
            'chunks_deleted': int(chunks_deleted or 0),
            'jobs_detached_count': int(jobs_detached or 0),
            'file_deleted': bool(file_result.get('deleted')),
            'file_delete_skipped': bool(file_result.get('skipped')),
            'file_result': file_result,
        }

    def _soft_delete_material_version(self, material: LearningMaterialVersion, *, actor: str | None = None, reason: str = 'audit_required') -> dict[str, Any]:
        version = self.db.get(QuestionBankVersion, material.bank_version_id)
        file_result = self._safe_delete_material_file(material) if settings.bank_material_purge_deleted_files_enabled else {'deleted': False, 'skipped': True, 'reason': 'file_purge_disabled'}
        chunk_count = self.db.query(MaterialChunk).filter(MaterialChunk.material_version_id == material.id).delete(synchronize_session=False)
        jobs_detached = self.db.query(BankOperationJob).filter(BankOperationJob.material_version_id == material.id).update(
            {BankOperationJob.material_version_id: None},
            synchronize_session=False,
        )
        now = datetime.utcnow()
        material.status = 'deleted'
        material.deleted_at = now
        material.deleted_by = actor or material.deleted_by
        material.uploaded_by = actor or material.uploaded_by
        if version:
            meta = dict(version.metadata_json or {})
            meta.update({
                'latest_material_delete_at': now.isoformat(),
                'latest_material_deleted_id': material.id,
                'latest_material_deleted_file': material.file_name,
                'latest_material_delete_mode': 'soft',
                'latest_material_delete_reason': reason,
                'latest_material_file_deleted': bool(file_result.get('deleted')),
            })
            if version.based_on_version_id:
                meta.update({
                    'document_change_state': 'changed_after_clone',
                    'diff_required': True,
                    'diff_base_bank_version_id': version.based_on_version_id,
                    'diff_trigger': 'material_deleted_after_clone',
                })
            version.metadata_json = meta
        self.db.flush()
        counts = self._material_dependency_counts(material.id)
        return {
            'ok': True,
            'material_version_id': material.id,
            'bank_version_id': material.bank_version_id,
            'chapter_id': material.chapter_id,
            'deletion_mode': 'soft',
            'reason': reason,
            'chunks_deleted': int(chunk_count or 0),
            'detached_question_count': 0,
            'concepts_detached_count': 0,
            'jobs_detached_count': int(jobs_detached or 0),
            'file_deleted': bool(file_result.get('deleted')),
            'file_delete_skipped': bool(file_result.get('skipped')),
            'file_result': file_result,
            'dependency_counts': counts,
        }

    def _delete_nonblocking_material_versions_for_chapter(self, chapter_id: str) -> int:
        """Hard-delete material rows that do not represent active user content.

        Material deletion is policy-based from v25.9.16.3.6 onward: unused
        draft/failed/tombstone rows are physically removed so they do not block
        chapter deletion and do not grow storage. Audit-sensitive rows stay as
        lightweight tombstones and continue to block chapter deletion when they
        still have real dependencies.
        """
        removed = 0
        rows = self.db.query(LearningMaterialVersion).filter(LearningMaterialVersion.chapter_id == chapter_id).all()
        for material in rows:
            counts = self._material_dependency_counts(material.id)
            is_deleted_tombstone = material.status == 'deleted'
            is_empty_placeholder = (
                int(counts.get('chunks') or 0) == 0
                and not (material.storage_path or '').strip()
                and not (material.content_hash or '').strip()
                and not (material.file_name or '').strip()
                and material.status in {'active', 'draft', 'failed', 'indexed'}
            )
            is_unused_active = (
                settings.bank_material_hard_delete_unused_enabled
                and material.status in {'active', 'draft', 'failed', 'indexed'}
                and not self._material_requires_audit_tombstone(material, counts)
            )
            is_safe_deleted = is_deleted_tombstone and not self._material_requires_audit_tombstone(material, counts)
            if not (is_empty_placeholder or is_unused_active or is_safe_deleted):
                continue
            self._hard_delete_material_version(material, reason='chapter_delete_cleanup')
            removed += 1
        if removed:
            self.db.flush()
        return removed

    def _delete_empty_bank_versions_for_chapter(self, chapter_id: str) -> int:
        """Remove shell bank versions that do not contain real bank content.

        Opening a chapter workspace can create a v1.0 shell. Clone/diff/runtime
        flows can also leave metadata rows pointing to that shell. Those records
        are not user-facing content and must not block deletion of a truly empty
        chapter. Only real materials, chunks, concepts, families, questions or
        releases keep the chapter protected.
        """
        removed = 0
        versions = self.db.query(QuestionBankVersion).filter(QuestionBankVersion.chapter_id == chapter_id).all()
        real_content_keys = {'materials', 'chunks', 'concepts', 'families', 'questions', 'releases'}
        for version in versions:
            counts = self._bank_version_content_counts(version.id)
            real_counts = {
                key: int(counts.get(key) or 0)
                for key in real_content_keys
                if int(counts.get(key) or 0) > 0
            }
            if real_counts:
                continue

            # Runtime/derived rows are safe to detach from an otherwise empty
            # shell. Keeping them would surface the confusing empty-bank-version delete blocker even when the chapter has no actual content.
            diff_ids = [
                row[0]
                for row in self.db.query(BankVersionDiff.id).filter(
                    or_(BankVersionDiff.from_bank_version_id == version.id, BankVersionDiff.to_bank_version_id == version.id)
                ).all()
                if row and row[0]
            ]
            if diff_ids:
                # Diff items do not always have DB-level ON DELETE CASCADE on old
                # production databases. Delete children first to avoid FK failures
                # when removing empty shell bank versions.
                self.db.query(BankVersionDiffItem).filter(BankVersionDiffItem.diff_id.in_(diff_ids)).delete(synchronize_session=False)
                self.db.query(BankVersionDiff).filter(BankVersionDiff.id.in_(diff_ids)).delete(synchronize_session=False)

            self.db.query(BankOperationJob).filter(BankOperationJob.bank_version_id == version.id).update(
                {BankOperationJob.bank_version_id: None},
                synchronize_session=False,
            )
            self.db.query(QuestionSearchDocument).filter(QuestionSearchDocument.bank_version_id == version.id).delete(synchronize_session=False)
            self.db.query(QuestionBankVersion).filter(QuestionBankVersion.based_on_version_id == version.id).update(
                {QuestionBankVersion.based_on_version_id: None},
                synchronize_session=False,
            )
            self.db.delete(version)
            removed += 1
        if removed:
            self.db.flush()
        return removed

    def delete_chapter(self, chapter_id: str) -> dict:
        item = self.db.get(SubjectChapter, chapter_id)
        if not item:
            raise ValueError('Không tìm thấy bài/chapter')

        # Dashboard/search rows are derived cache. Clear them before checking
        # real child content so a truly empty chapter can be deleted cleanly.
        self.db.query(BankChapterStats).filter(BankChapterStats.chapter_id == chapter_id).delete(synchronize_session=False)
        removed_empty_materials = self._delete_nonblocking_material_versions_for_chapter(chapter_id)
        removed_empty_versions = self._delete_empty_bank_versions_for_chapter(chapter_id)

        msg = self._empty_block_message(entity_label='bài/chapter', counts={
            'bank_versions': self.db.query(QuestionBankVersion).filter(QuestionBankVersion.chapter_id == chapter_id).count(),
            'materials': self.db.query(LearningMaterialVersion).filter(LearningMaterialVersion.chapter_id == chapter_id, LearningMaterialVersion.status != 'deleted').count(),
            'chunks': self.db.query(MaterialChunk).filter(MaterialChunk.chapter_id == chapter_id).count(),
            'concepts': self.db.query(ConceptVersion).filter(ConceptVersion.chapter_id == chapter_id).count(),
            'families': self.db.query(BankQuestionFamily).filter(BankQuestionFamily.chapter_id == chapter_id).count(),
            'questions': self.db.query(Question).filter(Question.subject_chapter_id == chapter_id).count(),
            'releases': self.db.query(QuestionBankRelease).filter(QuestionBankRelease.chapter_id == chapter_id).count(),
            'chapter_mappings': self.db.query(EdxCourseChapterMapping).filter(EdxCourseChapterMapping.subject_chapter_id == chapter_id).count(),
            'quiz_blueprints': self.db.query(QuizBlueprint).filter(QuizBlueprint.chapter_id == chapter_id).count(),
            'quiz_instances': self.db.query(CourseQuizInstance).filter(CourseQuizInstance.chapter_id == chapter_id).count(),
        })
        if msg:
            raise ValueError(msg)
        self.db.delete(item); self.db.commit()
        self._invalidate_dashboard_cache()
        cleanup_parts = []
        if removed_empty_versions:
            cleanup_parts.append(f'{removed_empty_versions} bank version rỗng')
        if removed_empty_materials:
            cleanup_parts.append(f'{removed_empty_materials} bản ghi tài liệu rỗng/đã xóa')
        cleanup_note = f" và đã dọn {', '.join(cleanup_parts)}" if cleanup_parts else ''
        return {'ok': True, 'deleted': True, 'entity_type': 'chapter', 'entity_id': chapter_id, 'message': 'Đã xóa bài/chapter' + cleanup_note}

    def next_bank_version_no(self, subject_id: str, chapter_id: str) -> int:
        value = self.db.query(func.max(QuestionBankVersion.version_no)).filter(
            QuestionBankVersion.subject_id == subject_id,
            QuestionBankVersion.chapter_id == chapter_id,
        ).scalar()
        return int(value or 0) + 1

    def create_bank_version(self, *, subject_id: str, chapter_id: str, version_code: str, title: str = '', change_note: str = '', based_on_version_id: str | None = None, subject_offering_id: str | None = None, actor: str | None = None) -> QuestionBankVersion:
        if subject_offering_id:
            offering = self.db.get(SubjectOffering, subject_offering_id)
            if not offering or offering.subject_id != subject_id:
                raise ValueError('Phiên bản môn không thuộc môn đã chọn')
        chapter = self.db.get(SubjectChapter, chapter_id)
        offering = self.db.get(SubjectOffering, subject_offering_id) if subject_offering_id else None
        clean_version_code = version_code.strip() or 'v1.0'
        auto_title = f'{offering.code if offering else ""} - {self._chapter_display_name(chapter)} - {clean_version_code}'.strip(' -')
        item = QuestionBankVersion(
            id=str(uuid.uuid4()),
            subject_id=subject_id,
            chapter_id=chapter_id,
            version_no=self.next_bank_version_no(subject_id, chapter_id),
            subject_offering_id=subject_offering_id,
            version_code=clean_version_code,
            title=title.strip() or auto_title,
            change_note=change_note or '',
            based_on_version_id=based_on_version_id,
            created_by=actor,
            metadata_json={'architecture': 'question_bank_first', 'release_policy': 'one_release_one_openedx_library'},
        )
        self.db.add(item)
        self.db.commit()
        self.db.refresh(item)
        self._safe_refresh_chapter_stats(chapter_id)
        return item

    def create_material_version(self, *, subject_id: str, chapter_id: str, bank_version_id: str, title: str = '', file_name: str = '', file_type: str = 'unknown', storage_path: str = '', content_hash: str | None = None, version_no: int = 1, change_type: str = 'initial', actor: str | None = None) -> LearningMaterialVersion:
        version = self.db.get(QuestionBankVersion, bank_version_id)
        item = LearningMaterialVersion(
            id=str(uuid.uuid4()),
            subject_id=subject_id,
            chapter_id=chapter_id,
            subject_offering_id=getattr(version, 'subject_offering_id', None),
            bank_version_id=bank_version_id,
            title=title,
            file_name=file_name,
            file_type=file_type,
            storage_path=storage_path,
            content_hash=content_hash,
            version_no=version_no,
            change_type=change_type,
            uploaded_by=actor,
        )
        self.db.add(item)
        self.db.commit()
        self.db.refresh(item)
        self._safe_refresh_chapter_stats(chapter_id)
        return item



    def _require_same_subject_chapter_versions(self, *, from_bank_version_id: str, to_bank_version_id: str) -> tuple[QuestionBankVersion, QuestionBankVersion]:
        source = self.db.get(QuestionBankVersion, from_bank_version_id)
        target = self.db.get(QuestionBankVersion, to_bank_version_id)
        if not source:
            raise ValueError('Không tìm thấy Bank Version nguồn')
        if not target:
            raise ValueError('Không tìm thấy Bank Version đích')
        if source.id == target.id:
            raise ValueError('Không thể so sánh một Bank Version với chính nó')
        same_subject = source.subject_id == target.subject_id
        same_chapter = source.chapter_id == target.chapter_id
        cloned_lineage = target.based_on_version_id == source.id or source.based_on_version_id == target.id
        if not same_subject or (not same_chapter and not cloned_lineage):
            raise ValueError('Chỉ được diff/carry-over giữa các Bank Version cùng môn và cùng bài. Với version môn clone, hệ thống dùng lineage để nhận ra bài tương ứng.')
        if source.subject_offering_id and target.subject_offering_id and source.subject_offering_id != target.subject_offering_id and not cloned_lineage:
            raise ValueError('Chỉ được diff/carry-over giữa các version trong cùng phiên bản môn, trừ trường hợp version mới clone từ version cũ')
        if target.status in {'published', 'archived'}:
            raise ValueError(f'Bank Version đích đang ở trạng thái {target.status}; không được sửa đè')
        return source, target

    def _material_text_for_version(self, bank_version_id: str, *, max_chars: int = 120000) -> str:
        rows = self.db.query(MaterialChunk).filter(MaterialChunk.bank_version_id == bank_version_id).order_by(MaterialChunk.material_version_id.asc(), MaterialChunk.chunk_index.asc()).all()
        parts: list[str] = []
        total = 0
        for row in rows:
            text = row.content or ''
            if total + len(text) > max_chars:
                remaining = max_chars - total
                if remaining > 0:
                    parts.append(text[:remaining])
                break
            parts.append(text)
            total += len(text)
        return '\n\n'.join(parts)

    def _material_hash_set(self, bank_version_id: str) -> set[str]:
        return {r.content_hash for r in self.db.query(LearningMaterialVersion.content_hash).filter(LearningMaterialVersion.bank_version_id == bank_version_id, LearningMaterialVersion.content_hash.isnot(None)).all() if r.content_hash}

    def _active_material_chunk_rows(self, bank_version_id: str) -> list[MaterialChunk]:
        return (
            self.db.query(MaterialChunk)
            .join(LearningMaterialVersion, LearningMaterialVersion.id == MaterialChunk.material_version_id)
            .filter(
                MaterialChunk.bank_version_id == bank_version_id,
                LearningMaterialVersion.status != 'deleted',
            )
            .order_by(MaterialChunk.material_version_id.asc(), MaterialChunk.chunk_index.asc(), MaterialChunk.id.asc())
            .all()
        )

    def _material_chunks_by_ids(self, ids: list[str]) -> list[MaterialChunk]:
        clean_ids = [value for value in split_source_chunk_ids(ids) if value]
        if not clean_ids:
            return []
        return self.db.query(MaterialChunk).filter(MaterialChunk.id.in_(clean_ids)).all()

    def _question_evidence_snippets(self, question: Question) -> list[dict[str, str]]:
        snippets: list[dict[str, str]] = []
        def add(label: str, value: str | None) -> None:
            text = (value or '').strip()
            if len(normalize_question_text_for_diff(text)) >= AUTO_RETIRE_MIN_EVIDENCE_CHARS:
                snippets.append({'label': label, 'text': text})

        add('source_excerpt', question.source_excerpt)
        add('source_evidence', question.source_evidence)
        add('explanation', question.explanation)
        add('learning_objective', question.learning_objective)
        for chunk in self._material_chunks_by_ids(split_source_chunk_ids(question.source_chunk_id)):
            add(f'chunk:{chunk.id}', chunk.content)

        if question.previous_question_id:
            previous = self.db.get(Question, question.previous_question_id)
            if previous:
                add('previous_source_excerpt', previous.source_excerpt)
                add('previous_source_evidence', previous.source_evidence)
                add('previous_explanation', previous.explanation)
                for chunk in self._material_chunks_by_ids(split_source_chunk_ids(previous.source_chunk_id)):
                    add(f'previous_chunk:{chunk.id}', chunk.content)

        # Deduplicate by normalized text while preserving order. This keeps the
        # recheck deterministic and avoids comparing the same long excerpt many times.
        seen: set[str] = set()
        unique: list[dict[str, str]] = []
        for item in snippets:
            key = normalize_question_text_for_diff(item.get('text'))[:1200]
            if not key or key in seen:
                continue
            seen.add(key)
            unique.append(item)
        return unique[:12]

    def _question_still_supported_by_current_materials(self, question: Question, current_chunks: list[MaterialChunk]) -> dict[str, Any]:
        if not current_chunks:
            return {'supported': False, 'confidence': 1.0, 'reason': 'no_current_material_chunks'}

        current_hashes = {chunk.content_hash for chunk in current_chunks if chunk.content_hash}
        referenced_chunks = self._material_chunks_by_ids(split_source_chunk_ids(question.source_chunk_id))
        if question.previous_question_id:
            previous = self.db.get(Question, question.previous_question_id)
            if previous:
                referenced_chunks.extend(self._material_chunks_by_ids(split_source_chunk_ids(previous.source_chunk_id)))
        for chunk in referenced_chunks:
            if chunk.content_hash and chunk.content_hash in current_hashes:
                return {'supported': True, 'confidence': 1.0, 'reason': 'source_chunk_hash_still_exists', 'matched_chunk_hash': chunk.content_hash}

        evidence_items = self._question_evidence_snippets(question)
        if not evidence_items:
            # Do not auto-delete rows that have no usable evidence. They may be
            # legacy questions generated before source evidence was captured.
            return {'supported': True, 'confidence': 0.35, 'reason': 'no_strong_evidence_keep_safe'}

        material_text = normalize_question_text_for_diff('\n\n'.join(chunk.content or '' for chunk in current_chunks))
        best: dict[str, Any] = {'supported': False, 'confidence': 0.0, 'reason': 'evidence_not_found'}
        for item in evidence_items:
            evidence_text = item['text']
            evidence_norm = normalize_question_text_for_diff(evidence_text)
            if len(evidence_norm) >= AUTO_RETIRE_MIN_EVIDENCE_CHARS and evidence_norm in material_text:
                return {'supported': True, 'confidence': 1.0, 'reason': 'evidence_exact_text_found', 'evidence_label': item['label']}

            # Fast token-overlap check against all current material text catches
            # renamed/rechunked documents without relying on file names.
            overlap = _token_overlap_ratio(evidence_text, material_text)
            if overlap > float(best.get('confidence') or 0):
                best = {'supported': overlap >= AUTO_RETIRE_TOKEN_OVERLAP_THRESHOLD, 'confidence': round(overlap, 4), 'reason': 'evidence_token_overlap', 'evidence_label': item['label']}
            if overlap >= AUTO_RETIRE_TOKEN_OVERLAP_THRESHOLD:
                return best

            # More expensive but bounded chunk-level similarity is a fallback for
            # short paragraphs with reordered punctuation/formatting.
            for chunk in current_chunks[:500]:
                score = _bounded_similarity(evidence_text, chunk.content)
                if score > float(best.get('confidence') or 0):
                    best = {'supported': score >= AUTO_RETIRE_STRONG_CHUNK_SIMILARITY, 'confidence': round(score, 4), 'reason': 'evidence_chunk_similarity', 'evidence_label': item['label'], 'matched_chunk_id': chunk.id}
                if score >= AUTO_RETIRE_STRONG_CHUNK_SIMILARITY:
                    return best
        return best

    def auto_retire_carry_over_questions_for_changed_materials(self, *, bank_version_id: str, actor: str | None = None, reason: str | None = None, commit: bool = True) -> dict[str, Any]:
        """Retire cloned/carry-over questions whose source evidence disappeared.

        Product rule for subject-version clone: cloned questions remain approved.
        Only when materials in the cloned version change do we automatically
        re-check approved carry-over questions against the entire current material
        set of that bank version. File names are ignored: if the same text moved
        to another file, the question is retained.
        """
        version = self.db.get(QuestionBankVersion, bank_version_id)
        if not version:
            raise ValueError('Không tìm thấy Bank Version')
        if not version.based_on_version_id:
            return {'ok': True, 'bank_version_id': bank_version_id, 'skipped': True, 'reason': 'not_cloned_bank_version', 'retired_count': 0, 'kept_count': 0}

        current_chunks = self._active_material_chunk_rows(bank_version_id)
        candidates = self.db.query(Question).filter(
            Question.bank_version_id == bank_version_id,
            Question.is_carry_over.is_(True),
            Question.status.in_(['approved', 'published']),
            or_(Question.is_retired.is_(False), Question.is_retired.is_(None)),
            Question.is_duplicate.is_(False),
        ).order_by(Question.created_at.asc(), Question.id.asc()).all()

        now = datetime.utcnow()
        retired: list[dict[str, Any]] = []
        kept: list[dict[str, Any]] = []
        safe_skipped: list[dict[str, Any]] = []
        for question in candidates:
            support = self._question_still_supported_by_current_materials(question, current_chunks)
            if support.get('supported'):
                item = {'question_id': question.id, 'reason': support.get('reason'), 'confidence': support.get('confidence')}
                if support.get('reason') == 'no_strong_evidence_keep_safe':
                    safe_skipped.append(item)
                else:
                    kept.append(item)
                continue

            question.status = 'retired'
            question.is_retired = True
            question.retired_at = now
            question.retired_reason = reason or 'auto_retired_material_source_missing'
            question.quality_flags = list(question.quality_flags or []) + ['auto_retired_material_source_missing']
            # Keep Open edX lifecycle fields untouched; this bank version has not
            # been republished yet. Publish flow will ignore retired questions.
            retired.append({'question_id': question.id, 'reason': support.get('reason'), 'confidence': support.get('confidence')})

        release_removed = 0
        if retired:
            retired_ids = [row['question_id'] for row in retired]
            draft_release_ids = [
                row.id for row in self.db.query(QuestionBankRelease.id).filter(
                    QuestionBankRelease.bank_version_id == bank_version_id,
                    QuestionBankRelease.status.notin_(['published', 'archived', 'deprecated']),
                ).all()
            ]
            if draft_release_ids:
                release_removed = int(self.db.query(BankReleaseQuestion).filter(
                    BankReleaseQuestion.bank_release_id.in_(draft_release_ids),
                    BankReleaseQuestion.question_id.in_(retired_ids),
                ).delete(synchronize_session=False) or 0)

        meta = dict(version.metadata_json or {})
        history = list(meta.get('auto_material_recheck_history') or [])
        summary = {
            'checked_at': now.isoformat(),
            'actor': actor,
            'trigger': reason or meta.get('diff_trigger') or 'material_changed_after_clone',
            'candidate_count': len(candidates),
            'kept_count': len(kept),
            'safe_skipped_count': len(safe_skipped),
            'retired_count': len(retired),
            'release_removed_count': release_removed,
            'current_material_chunk_count': len(current_chunks),
        }
        history.append(summary)
        meta.update({
            'document_change_state': 'auto_rechecked_after_material_change',
            'diff_required': False,
            'last_auto_material_recheck': summary,
            'auto_material_recheck_history': history[-10:],
        })
        version.metadata_json = meta

        if commit:
            self.db.commit()
            self._safe_refresh_bank_version_stats(bank_version_id)
        return {
            'ok': True,
            'bank_version_id': bank_version_id,
            **summary,
            'kept_question_ids': [row['question_id'] for row in kept],
            'safe_skipped_question_ids': [row['question_id'] for row in safe_skipped],
            'retired_question_ids': [row['question_id'] for row in retired],
            'message': f'Đã kiểm tra lại câu hỏi clone: giữ {len(kept) + len(safe_skipped)}, tự loại {len(retired)} câu không còn căn cứ trong tài liệu hiện tại.',
        }

    def _concept_map(self, bank_version_id: str) -> dict[str, ConceptVersion]:
        return {row.concept_key: row for row in self.db.query(ConceptVersion).filter(ConceptVersion.bank_version_id == bank_version_id).all()}

    def _question_candidates_for_version(self, bank_version_id: str) -> list[Question]:
        return self.db.query(Question).filter(
            Question.bank_version_id == bank_version_id,
            Question.status.in_(['approved', 'published']),
            Question.is_retired.is_(False),
            Question.is_duplicate.is_(False),
        ).order_by(Question.difficulty.asc(), Question.question_family_id.asc().nullslast(), Question.variant_no.asc().nullslast(), Question.created_at.asc()).all()

    def preview_bank_version_diff(self, *, from_bank_version_id: str, to_bank_version_id: str, actor: str | None = None, persist: bool = False) -> dict:
        source, target = self._require_same_subject_chapter_versions(from_bank_version_id=from_bank_version_id, to_bank_version_id=to_bank_version_id)
        source_material_hashes = self._material_hash_set(source.id)
        target_material_hashes = self._material_hash_set(target.id)
        exact_shared_materials = len(source_material_hashes & target_material_hashes)
        source_text = self._material_text_for_version(source.id)
        target_text = self._material_text_for_version(target.id)
        material_similarity = bank_text_similarity(source_text, target_text)

        source_concepts = self._concept_map(source.id)
        target_concepts = self._concept_map(target.id)
        unchanged_concepts = sorted(set(source_concepts) & set(target_concepts))
        removed_concepts = sorted(set(source_concepts) - set(target_concepts))
        new_concepts = sorted(set(target_concepts) - set(source_concepts))
        changed_concepts: list[str] = []
        for key in list(unchanged_concepts):
            src = source_concepts[key]
            dst = target_concepts[key]
            sim = bank_text_similarity((src.description or '') + ' ' + (src.learning_objective or ''), (dst.description or '') + ' ' + (dst.learning_objective or ''))
            if sim and sim < 0.72:
                changed_concepts.append(key)

        target_hashes = {r.question_hash for r in self.db.query(Question.question_hash).filter(Question.bank_version_id == target.id, Question.question_hash.isnot(None)).all() if r.question_hash}
        target_lineage_roots = {r.lineage_root_question_id for r in self.db.query(Question.lineage_root_question_id).filter(Question.bank_version_id == target.id, Question.lineage_root_question_id.isnot(None)).all() if r.lineage_root_question_id}
        source_questions = self._question_candidates_for_version(source.id)
        carry_over_candidates: list[Question] = []
        retire_candidates: list[Question] = []
        review_candidates: list[Question] = []
        already_exists: list[Question] = []
        removed_concept_set = set(removed_concepts)
        changed_concept_set = set(changed_concepts)
        unchanged_concept_set = set(unchanged_concepts)
        for question in source_questions:
            root = question_lineage_root(question)
            concept_key = stable_concept_identity(question)
            if (question.question_hash and question.question_hash in target_hashes) or root in target_lineage_roots:
                already_exists.append(question)
            elif concept_key in removed_concept_set:
                retire_candidates.append(question)
            elif concept_key in changed_concept_set:
                review_candidates.append(question)
            elif concept_key in unchanged_concept_set or material_similarity >= 0.72:
                carry_over_candidates.append(question)
            else:
                review_candidates.append(question)

        summary = {
            'from_bank_version_id': source.id,
            'to_bank_version_id': target.id,
            'from_version_code': source.version_code,
            'to_version_code': target.version_code,
            'material_similarity': material_similarity,
            'source_material_count': len(source_material_hashes),
            'target_material_count': len(target_material_hashes),
            'exact_shared_material_count': exact_shared_materials,
            'unchanged_concept_count': len(unchanged_concepts),
            'changed_concept_count': len(changed_concepts),
            'new_concept_count': len(new_concepts),
            'removed_concept_count': len(removed_concepts),
            'source_approved_question_count': len(source_questions),
            'carry_over_candidate_count': len(carry_over_candidates),
            'retire_candidate_count': len(retire_candidates),
            'review_candidate_count': len(review_candidates),
            'already_exists_count': len(already_exists),
            'recommendation': 'carry_over_then_review' if carry_over_candidates else 'generate_or_review_required',
            'changed_concepts': changed_concepts[:50],
            'new_concepts': new_concepts[:50],
            'removed_concepts': removed_concepts[:50],
        }
        diff = None
        if persist:
            fingerprint_payload = {
                'from_bank_version_id': source.id,
                'to_bank_version_id': target.id,
                'source_material_hashes': sorted(source_material_hashes),
                'target_material_hashes': sorted(target_material_hashes),
                'changed_concepts': changed_concepts,
                'new_concepts': new_concepts,
                'removed_concepts': removed_concepts,
            }
            idempotency_key = hashlib.sha256(
                json.dumps(fingerprint_payload, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode('utf-8')
            ).hexdigest()
            existing = self.db.query(BankVersionDiff).filter(
                BankVersionDiff.from_bank_version_id == source.id,
                BankVersionDiff.to_bank_version_id == target.id,
                BankVersionDiff.idempotency_key == idempotency_key,
            ).order_by(BankVersionDiff.created_at.desc()).first()
            if existing:
                return {
                    'ok': True,
                    'diff_id': existing.id,
                    'summary': existing.summary_json or summary,
                    'material_similarity': existing.material_similarity,
                    'carry_over_candidates': [q.id for q in carry_over_candidates],
                    'retire_candidates': [q.id for q in retire_candidates],
                    'review_candidates': [q.id for q in review_candidates],
                    'already_exists': [q.id for q in already_exists],
                    'idempotent_reuse': True,
                    'message': 'Đã sử dụng lại bản so sánh đã lưu cho cùng nội dung phiên bản.',
                }
            diff = BankVersionDiff(
                id=str(uuid.uuid4()),
                from_bank_version_id=source.id,
                to_bank_version_id=target.id,
                status='preview',
                material_similarity=material_similarity,
                idempotency_key=idempotency_key,
                summary_json=summary,
                created_by=actor,
                created_at=datetime.utcnow(),
            )
            self.db.add(diff)
            try:
                self.db.flush()
            except IntegrityError:
                # Another request may persist the same deterministic diff between
                # our read and flush. Roll back the failed insert and reuse the
                # row protected by the database unique constraint.
                self.db.rollback()
                existing = self.db.query(BankVersionDiff).filter(
                    BankVersionDiff.from_bank_version_id == source.id,
                    BankVersionDiff.to_bank_version_id == target.id,
                    BankVersionDiff.idempotency_key == idempotency_key,
                ).order_by(BankVersionDiff.created_at.desc()).first()
                if existing:
                    return {
                        'ok': True,
                        'diff_id': existing.id,
                        'summary': existing.summary_json or summary,
                        'material_similarity': existing.material_similarity,
                        'carry_over_candidates': [q.id for q in carry_over_candidates],
                        'retire_candidates': [q.id for q in retire_candidates],
                        'review_candidates': [q.id for q in review_candidates],
                        'already_exists': [q.id for q in already_exists],
                        'idempotent_reuse': True,
                        'message': 'Đã sử dụng lại bản so sánh được tạo đồng thời cho cùng nội dung phiên bản.',
                    }
                raise
            for question in carry_over_candidates:
                self.db.add(BankVersionDiffItem(id=str(uuid.uuid4()), diff_id=diff.id, item_type='question', source_id=question.id, target_id=None, change_type='carry_over_candidate', confidence=0.95 if stable_concept_identity(question) in unchanged_concept_set else material_similarity, reason='Concept giữ nguyên hoặc tài liệu rất giống; có thể carry-over nhưng vẫn giữ audit lineage.', metadata_json={'question_text': question.question_text[:300], 'difficulty': question.difficulty, 'family': question.question_family_id}))
            for question in retire_candidates:
                self.db.add(BankVersionDiffItem(id=str(uuid.uuid4()), diff_id=diff.id, item_type='question', source_id=question.id, target_id=None, change_type='retire_candidate', confidence=0.9, reason='Concept nguồn không còn trong Bank Version mới.', metadata_json={'question_text': question.question_text[:300], 'difficulty': question.difficulty, 'concept_key': stable_concept_identity(question)}))
            for question in review_candidates:
                self.db.add(BankVersionDiffItem(id=str(uuid.uuid4()), diff_id=diff.id, item_type='question', source_id=question.id, target_id=None, change_type='needs_review', confidence=0.55, reason='Concept/tài liệu có thay đổi hoặc chưa đủ chắc để carry-over tự động.', metadata_json={'question_text': question.question_text[:300], 'difficulty': question.difficulty, 'concept_key': stable_concept_identity(question)}))
            for key in new_concepts:
                self.db.add(BankVersionDiffItem(id=str(uuid.uuid4()), diff_id=diff.id, item_type='concept', source_id=None, target_id=target_concepts[key].id, change_type='new', confidence=1.0, reason='Concept mới trong Bank Version đích.', metadata_json={'concept_key': key, 'concept_title': target_concepts[key].concept_title}))
            for key in removed_concepts:
                self.db.add(BankVersionDiffItem(id=str(uuid.uuid4()), diff_id=diff.id, item_type='concept', source_id=source_concepts[key].id, target_id=None, change_type='removed', confidence=1.0, reason='Concept nguồn không còn trong Bank Version đích.', metadata_json={'concept_key': key, 'concept_title': source_concepts[key].concept_title}))
            self.db.commit()
            self.db.refresh(diff)
        return {
            'ok': True,
            'diff_id': diff.id if diff else None,
            'summary': summary,
            'material_similarity': material_similarity,
            'carry_over_candidates': [q.id for q in carry_over_candidates],
            'retire_candidates': [q.id for q in retire_candidates],
            'review_candidates': [q.id for q in review_candidates],
            'already_exists': [q.id for q in already_exists],
            'message': 'Đã so sánh Bank Version. Có thể carry-over câu còn đúng, retire câu không còn phù hợp và review phần thay đổi.',
        }


    def create_bank_version_diff(self, *, from_bank_version_id: str, to_bank_version_id: str, actor: str | None = None) -> dict:
        return self.preview_bank_version_diff(
            from_bank_version_id=from_bank_version_id,
            to_bank_version_id=to_bank_version_id,
            actor=actor,
            persist=True,
        )

    def _ensure_target_concept_for_question(self, *, target: QuestionBankVersion, source_question: Question) -> ConceptVersion:
        key = stable_concept_identity(source_question)
        row = self.db.query(ConceptVersion).filter(ConceptVersion.bank_version_id == target.id, ConceptVersion.concept_key == key).first()
        if row:
            return row
        row = ConceptVersion(
            id=str(uuid.uuid4()),
            bank_version_id=target.id,
            subject_id=target.subject_id,
            chapter_id=target.chapter_id,
            subject_offering_id=target.subject_offering_id,
            material_version_id=None,
            concept_key=key,
            concept_title=source_question.concept_title or source_question.topic or 'Concept carry-over',
            description='Carry-over từ version trước; câu được chấp nhận theo chính sách version isolation.',
            learning_objective=source_question.learning_objective or '',
            source_evidence=source_question.source_evidence or source_question.source_excerpt or '',
            source_chunk_hash=None,
            status='active',
        )
        self.db.add(row)
        self.db.flush()
        return row

    def _ensure_target_family_for_question(self, *, target: QuestionBankVersion, concept: ConceptVersion, source_question: Question) -> BankQuestionFamily:
        diff = normalize_difficulty(source_question.difficulty)
        family_key = build_question_family_id(
            course_id=f'bank:{target.id}',
            chapter_node_id=target.chapter_id,
            difficulty=diff,
            concept_id=concept.id,
            concept_key=concept.concept_key,
            concept_title=concept.concept_title,
            topic=source_question.topic,
            learning_objective=source_question.learning_objective,
            question_text=source_question.question_text,
        )
        row = self.db.query(BankQuestionFamily).filter(BankQuestionFamily.bank_version_id == target.id, BankQuestionFamily.difficulty == diff, BankQuestionFamily.family_key == family_key).first()
        if row:
            return row
        row = BankQuestionFamily(
            id=str(uuid.uuid4()),
            bank_version_id=target.id,
            subject_id=target.subject_id,
            chapter_id=target.chapter_id,
            subject_offering_id=target.subject_offering_id,
            concept_version_id=concept.id,
            difficulty=diff,
            family_key=family_key,
            family_title=concept.concept_title,
            family_fingerprint=sha256_text(f'{target.id}|{concept.concept_key}|{diff}', 64),
            status='active',
        )
        self.db.add(row)
        self.db.flush()
        return row

    def carry_over_questions(self, *, from_bank_version_id: str, to_bank_version_id: str, question_ids: list[str] | None = None, require_review: bool = False, actor: str | None = None, diff_id: str | None = None) -> dict:
        source, target = self._require_same_subject_chapter_versions(from_bank_version_id=from_bank_version_id, to_bank_version_id=to_bank_version_id)
        candidates_query = self.db.query(Question).filter(Question.bank_version_id == source.id, Question.status.in_(['approved', 'published']), Question.is_retired.is_(False), Question.is_duplicate.is_(False))
        if question_ids:
            candidates_query = candidates_query.filter(Question.id.in_(question_ids))
        candidates = candidates_query.order_by(Question.difficulty.asc(), Question.question_family_id.asc().nullslast(), Question.variant_no.asc().nullslast()).all()
        target_hashes = {r.question_hash for r in self.db.query(Question.question_hash).filter(Question.bank_version_id == target.id, Question.question_hash.isnot(None)).all() if r.question_hash}
        target_roots = {r.lineage_root_question_id for r in self.db.query(Question.lineage_root_question_id).filter(Question.bank_version_id == target.id, Question.lineage_root_question_id.isnot(None)).all() if r.lineage_root_question_id}
        created: list[Question] = []
        skipped: list[dict] = []
        for source_question in candidates:
            root = question_lineage_root(source_question)
            if (source_question.question_hash and source_question.question_hash in target_hashes) or root in target_roots:
                skipped.append({'question_id': source_question.id, 'reason': 'already_exists_in_target'})
                continue
            concept = self._ensure_target_concept_for_question(target=target, source_question=source_question)
            family = self._ensure_target_family_for_question(target=target, concept=concept, source_question=source_question)
            q = Question(
                id=str(uuid.uuid4()),
                course_id=f'bank:{target.id}',
                source_course_id=source_question.source_course_id,
                department_id=source_question.department_id,
                subject_id=target.subject_id,
                subject_chapter_id=target.chapter_id,
                bank_version_id=target.id,
                material_version_id=None,
                concept_version_id=concept.id,
                previous_question_id=source_question.id,
                lineage_root_question_id=root,
                question_revision_no=int(source_question.question_revision_no or 1) + 1,
                is_carry_over=True,
                lesson_id=source_question.lesson_id,
                lesson_title=source_question.lesson_title,
                block_id=f'bank-version:{target.id}',
                topic=source_question.topic,
                concept_id=concept.id,
                concept_title=concept.concept_title,
                concept_key=concept.concept_key,
                question_family_id=family.family_key,
                variant_no=self._next_variant_no(bank_version_id=target.id, family_key=family.family_key),
                source_evidence=source_question.source_evidence,
                difficulty=normalize_difficulty(source_question.difficulty),
                cognitive_level=source_question.cognitive_level,
                learning_objective=source_question.learning_objective,
                question_type=source_question.question_type,
                question_text=source_question.question_text,
                question_hash=source_question.question_hash,
                option_a=source_question.option_a,
                option_b=source_question.option_b,
                option_c=source_question.option_c,
                option_d=source_question.option_d,
                correct_answer=source_question.correct_answer,
                explanation=source_question.explanation,
                source_ref=f'carry-over:{source.id}:{source_question.id}',
                source_type='bank_carry_over',
                source_page=source_question.source_page,
                source_timestamp_start=source_question.source_timestamp_start,
                source_timestamp_end=source_question.source_timestamp_end,
                source_chunk_id=source_question.source_chunk_id,
                source_node_id=f'bank-version:{target.id}',
                source_node_title=f'Carry-over từ {source.version_code}',
                chapter_node_id=target.chapter_id,
                chapter_title=source_question.chapter_title,
                source_excerpt=source_question.source_excerpt,
                tags=list(source_question.tags or []) + ['carry-over', f'from:{source.version_code}', f'to:{target.version_code}'],
                ai_rationale=source_question.ai_rationale,
                quality_score=source_question.quality_score,
                quality_flags=list(source_question.quality_flags or []) + ['carry_over_from_previous_bank_version'],
                model_provider=source_question.model_provider,
                model_name=source_question.model_name,
                status='approved',
                reviewed_by=actor,
                reviewed_at=datetime.utcnow(),
            )
            self.db.add(q)
            self.db.flush()
            created.append(q)
            target_hashes.add(q.question_hash) if q.question_hash else None
            target_roots.add(root)
            if diff_id:
                self.db.add(BankVersionDiffItem(id=str(uuid.uuid4()), diff_id=diff_id, item_type='question', source_id=source_question.id, target_id=q.id, change_type='carried_over', confidence=1.0, reason='Đã carry-over sang Bank Version mới, không sửa đè câu cũ.', metadata_json={'carry_over_status': 'approved', 'require_review_ignored': bool(require_review)}))
        if diff_id:
            diff = self.db.get(BankVersionDiff, diff_id)
            if diff:
                diff.status = 'applied'
                diff.applied_by = actor
                diff.applied_at = datetime.utcnow()
        target.metadata_json = {**(target.metadata_json or {}), 'last_carry_over_at': datetime.utcnow().isoformat(), 'last_carry_over_from': source.id, 'last_carry_over_created': len(created), 'last_carry_over_skipped': len(skipped)}
        self.db.commit()
        self._safe_refresh_chapter_stats(target.chapter_id)
        return {'ok': True, 'created_count': len(created), 'skipped_count': len(skipped), 'created_question_ids': [q.id for q in created], 'skipped': skipped, 'message': 'Đã clone câu còn dùng lại được sang version mới và chấp nhận luôn. Version nguồn không bị thay đổi.'}

    def retire_questions(self, *, bank_version_id: str, question_ids: list[str], reason: str, actor: str | None = None) -> dict:
        """Record that source questions are excluded from the target version.

        v25.9.15.3.2 semantics: versions are fully isolated snapshots.
        If a question from v1 is not reusable in v2, it is simply not cloned into
        v2. We never create a retired snapshot in v2 and never mutate v1. The
        exclusion is stored in target.metadata_json/diff items for audit only.
        If a provided question already belongs to the target version, we can mark
        that target-local row retired because that does not affect other versions.
        """
        target = self.db.get(QuestionBankVersion, bank_version_id)
        if not target:
            raise ValueError('Không tìm thấy Bank Version đích')
        if target.status in {'published', 'archived'}:
            raise ValueError(f'Bank Version đích đang ở trạng thái {target.status}; không được chỉnh sửa. Hãy tạo version mới.')

        excluded: list[str] = []
        retired: list[str] = []
        skipped: list[dict] = []
        now = datetime.utcnow()

        for qid in question_ids:
            source_question = self.db.get(Question, qid)
            if not source_question:
                skipped.append({'question_id': qid, 'reason': 'not_found'})
                continue
            if source_question.bank_version_id == target.id:
                source_question.status = 'retired'
                source_question.is_retired = True
                source_question.retired_reason = reason or 'retired_in_target_version'
                source_question.retired_at = now
                source_question.quality_flags = list(source_question.quality_flags or []) + ['retired_in_target_bank_version_only']
                retired.append(source_question.id)
                continue
            if source_question.subject_id != target.subject_id or source_question.subject_chapter_id != target.chapter_id:
                skipped.append({'question_id': source_question.id, 'reason': 'different_subject_or_chapter'})
                continue
            excluded.append(source_question.id)

        metadata = dict(target.metadata_json or {})
        previous = list(metadata.get('excluded_source_question_ids') or [])
        merged = list(dict.fromkeys(previous + excluded))
        metadata.update({
            'last_exclusion_at': now.isoformat(),
            'last_exclusion_count': len(excluded),
            'excluded_source_question_ids': merged,
            'excluded_reason': reason or 'not_carried_over_to_target_version',
            'version_isolation_policy': 'not_reusable_questions_are_not_cloned',
        })
        target.metadata_json = metadata
        # No target question row is created for excluded source questions.
        # Diff/exclusion audit lives in Bank Version metadata to avoid FK issues.
        self.db.commit()
        self._safe_refresh_chapter_stats(target.chapter_id)
        return {
            'ok': True,
            'retired_count': len(retired),
            'retired_question_ids': retired,
            'source_question_ids': excluded,
            'excluded_count': len(excluded),
            'excluded_question_ids': excluded,
            'skipped': skipped,
            'message': 'Đã ghi nhận không clone các câu không còn phù hợp vào version mới. Version nguồn không bị thay đổi.',
        }

    def _require_bank_version(self, bank_version_id: str) -> QuestionBankVersion:
        version = self.db.get(QuestionBankVersion, bank_version_id)
        if not version:
            raise ValueError('Không tìm thấy Bank Version')
        if version.status in {'archived'}:
            raise ValueError(f'Bank Version đang ở trạng thái {version.status}; hãy tạo version mới nếu tài liệu thay đổi.')
        return version

    def _require_mutable_bank_version(self, bank_version_id: str) -> QuestionBankVersion:
        # Alias rõ nghĩa dùng cho upload/xóa tài liệu. Giữ riêng tên này để các luồng UI
        # gọi xóa tài liệu không bị lỗi AttributeError khi service được refactor.
        version = self._require_bank_version(bank_version_id)
        self._raise_if_published_locked(version, action='không thể thay đổi tài liệu/câu hỏi của bài')
        return version

    def upload_material_bytes(
        self,
        *,
        bank_version_id: str,
        filename: str,
        raw: bytes,
        content_type: str = '',
        title: str = '',
        change_type: str = 'initial',
        actor: str | None = None,
        replace_existing: bool = False,
    ) -> dict:
        version = self._require_mutable_bank_version(bank_version_id)
        subject = self.db.get(Subject, version.subject_id)
        chapter = self.db.get(SubjectChapter, version.chapter_id)
        if not subject or not chapter:
            raise ValueError('Bank Version thiếu Subject hoặc Chapter')
        if not raw:
            raise ValueError('File rỗng, không có nội dung để xử lý.')
        if len(raw) > BANK_UPLOAD_MAX_BYTES:
            raise ValueError('File quá lớn. Giới hạn hiện tại là 50MB/file.')
        filename = safe_upload_filename(filename)
        ext = upload_extension(filename)
        if ext in BANK_UPLOAD_LEGACY_OFFICE_EXTENSIONS:
            raise ValueError(f'File .{ext} là định dạng Office cũ. Vui lòng chuyển sang .docx/.xlsx hoặc PDF trước khi upload.')
        if ext not in BANK_UPLOAD_ALLOWED_EXTENSIONS:
            raise ValueError(f'Định dạng .{ext or "unknown"} chưa được hỗ trợ. Hỗ trợ: {", ".join(sorted(BANK_UPLOAD_ALLOWED_EXTENSIONS))}.')

        raw_hash = hashlib.sha256(raw).hexdigest()
        existing = self.db.query(LearningMaterialVersion).filter(
            LearningMaterialVersion.bank_version_id == version.id,
            LearningMaterialVersion.content_hash == raw_hash,
            LearningMaterialVersion.status != 'deleted',
        ).first()
        if existing and not replace_existing:
            meta = version.metadata_json or {}
            return {
                'ok': True,
                'reused_existing': True,
                'material_version': existing,
                'chunks_created': self.db.query(MaterialChunk).filter(MaterialChunk.material_version_id == existing.id).count(),
                'tokens_indexed': int(self.db.query(func.coalesce(func.sum(MaterialChunk.token_count), 0)).filter(MaterialChunk.material_version_id == existing.id).scalar() or 0),
                'diff_required': bool(meta.get('diff_required')),
                'diff_base_bank_version_id': meta.get('diff_base_bank_version_id') or version.based_on_version_id,
                'document_change_state': meta.get('document_change_state') or 'unchanged',
                'message': 'File này đã tồn tại trong Bank Version; không tạo bản trùng.',
            }

        material_id = str(uuid.uuid4())
        storage_dir = bank_material_storage_dir(version.id)
        storage_dir.mkdir(parents=True, exist_ok=True)
        storage_path = storage_dir / f'{material_id}-{filename}'
        storage_path.write_bytes(raw)

        extractor = ContentExtractor()
        try:
            items = extractor.extract_asset({
                'asset_id': f'bank-material:{material_id}',
                'url': f'bank-material://{version.id}/{material_id}/{filename}',
                'source_ref': f'bank-material://{version.id}/{material_id}/{filename}',
                'filename': filename,
                'display_name': filename,
                'mime_type': content_type or '',
                'bytes': raw,
                'strict': True,
            }, parent_block_id=f'bank-version:{version.id}')
        except ValueError:
            raise
        except Exception as exc:
            raise ValueError(f'Không đọc được file {filename}: {exc}') from exc
        if not items:
            raise ValueError(
                f'File {filename} không tách được text. Nếu là scan/ảnh, hãy bật OCR cho đúng loại file '
                '(PDF/PPTX/DOCX), tăng FILE_OCR_MAX_PAGES hoặc DOCX_OCR_MAX_IMAGES nếu tài liệu dài, '
                'hoặc upload bản DOCX/PDF có text/transcript.'
            )

        next_version_no = int((self.db.query(func.max(LearningMaterialVersion.version_no)).filter(LearningMaterialVersion.bank_version_id == version.id).scalar() or 0) + 1)
        material = LearningMaterialVersion(
            id=material_id,
            subject_id=version.subject_id,
            chapter_id=version.chapter_id,
            subject_offering_id=version.subject_offering_id,
            bank_version_id=version.id,
            title=title.strip() or filename,
            file_name=filename,
            file_type=ext or 'file',
            storage_path=str(storage_path),
            content_hash=raw_hash,
            version_no=next_version_no,
            change_type=change_type or 'initial',
            uploaded_by=actor,
            status='indexed',
        )
        self.db.add(material)
        self.db.flush()

        chunker = Chunker()
        chunks_created = 0
        tokens_indexed = 0
        source_types: set[str] = set()
        for item in items:
            source_type = (item.source_type or ext or 'file').lower()
            source_types.add(source_type)
            max_tokens, overlap_tokens = chunk_policy_for_material_source(source_type)
            text_chunks = chunker.chunk_text(item.content, max_tokens=max_tokens, overlap_tokens=overlap_tokens)
            if not text_chunks and item.content.strip():
                text_chunks = [item.content]
            for text in text_chunks:
                chunks_created += 1
                source_ref = item.source_ref or f'bank-material://{version.id}/{material_id}/{filename}'
                if len(text_chunks) > 1:
                    source_ref = f'{source_ref}#chunk={chunks_created}'
                token_count = count_tokens(text)
                tokens_indexed += token_count
                self.db.add(MaterialChunk(
                    id=str(uuid.uuid4()),
                    material_version_id=material.id,
                    bank_version_id=version.id,
                    subject_id=version.subject_id,
                    chapter_id=version.chapter_id,
                    subject_offering_id=version.subject_offering_id,
                    chunk_index=chunks_created,
                    content=text,
                    token_count=token_count,
                    source_type=source_type,
                    page_number=item.page_number,
                    source_ref=source_ref,
                    content_hash=sha256_text(text, 64),
                ))
        uploaded_at = datetime.utcnow().isoformat()
        meta = {
            **(version.metadata_json or {}),
            'latest_material_upload_at': uploaded_at,
            'latest_material_id': material.id,
            'latest_material_filename': filename,
            'latest_material_change_type': change_type or 'initial',
            'material_chunks_created': chunks_created,
            'material_tokens_indexed': tokens_indexed,
        }
        diff_required = bool(version.based_on_version_id)
        if diff_required:
            meta.update({
                'document_change_state': 'changed_after_clone',
                'diff_required': True,
                'diff_base_bank_version_id': version.based_on_version_id,
                'diff_trigger': 'material_uploaded_after_clone',
                'diff_trigger_material_id': material.id,
                'diff_trigger_filename': filename,
                'diff_triggered_at': uploaded_at,
                'release_policy': 'create_release_manually_after_reviewing_changed_material',
            })
        version.metadata_json = meta
        self.db.commit()
        self.db.refresh(material)
        auto_retire_result = None
        if diff_required:
            auto_retire_result = self.auto_retire_carry_over_questions_for_changed_materials(
                bank_version_id=version.id,
                actor=actor,
                reason='material_uploaded_after_clone',
                commit=True,
            )
        else:
            self._safe_refresh_chapter_stats(version.chapter_id)
        self.db.refresh(version)
        return {
            'ok': True,
            'reused_existing': False,
            'material_version': material,
            'chunks_created': chunks_created,
            'tokens_indexed': tokens_indexed,
            'source_types': sorted(source_types),
            'diff_required': False if auto_retire_result else diff_required,
            'diff_base_bank_version_id': version.based_on_version_id if diff_required else None,
            'document_change_state': version.metadata_json.get('document_change_state') if version.metadata_json else None,
            'auto_retire_result': auto_retire_result,
            'message': 'Tải tài liệu và tách nội dung vào Bank Version thành công.' + (f' {auto_retire_result.get("message")}' if auto_retire_result else ''),
        }


    def delete_material_version(self, *, material_version_id: str, actor: str | None = None, force_hard: bool = False) -> dict:
        material = self.db.get(LearningMaterialVersion, material_version_id)
        if not material or material.status == 'deleted':
            raise ValueError('Không tìm thấy tài liệu')
        version = self._require_mutable_bank_version(material.bank_version_id)
        counts = self._material_dependency_counts(material.id)

        # Draft/failed/unused uploads should not become tombstones and should not
        # consume disk. Keep tombstones only when the material has real lineage.
        can_hard_delete = not self._material_requires_audit_tombstone(material, counts)
        if force_hard and not can_hard_delete:
            raise ValueError('Không thể xóa cứng tài liệu vì đã được dùng trong câu hỏi/concept/diff. Hãy giữ xóa mềm để bảo toàn lịch sử.')

        if settings.bank_material_hard_delete_unused_enabled and can_hard_delete:
            result = self._hard_delete_material_version(material, reason='unused_material_deleted_by_user')
            self.db.commit()
            self._safe_refresh_chapter_stats(version.chapter_id)
            result['detached_question_count'] = 0
            result['concepts_detached_count'] = 0
            result['message'] = 'Đã xóa cứng tài liệu chưa dùng và dọn file/chunk liên quan.'
            return result

        result = self._soft_delete_material_version(material, actor=actor, reason='audit_lineage_required')
        self.db.commit()
        auto_retire_result = None
        if version.based_on_version_id:
            auto_retire_result = self.auto_retire_carry_over_questions_for_changed_materials(
                bank_version_id=version.id,
                actor=actor,
                reason='material_deleted_after_clone',
                commit=True,
            )
        else:
            self._safe_refresh_chapter_stats(version.chapter_id)
        result['auto_retire_result'] = auto_retire_result
        result['message'] = 'Đã xóa tài liệu khỏi bài. File/chunk đã được dọn; metadata được giữ để bảo toàn lịch sử câu hỏi/release.' + (f' {auto_retire_result.get("message")}' if auto_retire_result else '')
        return result

    def bank_material_cleanup_health(self) -> dict[str, Any]:
        deleted_query = self.db.query(LearningMaterialVersion).filter(LearningMaterialVersion.status == 'deleted')
        active_query = self.db.query(LearningMaterialVersion).filter(LearningMaterialVersion.status != 'deleted')
        deleted_count = int(deleted_query.count() or 0)
        deleted_rows = deleted_query.order_by(LearningMaterialVersion.deleted_at.asc().nullsfirst(), LearningMaterialVersion.created_at.asc()).limit(2000).all()
        deleted_files = 0
        deleted_file_bytes = 0
        skipped_shared_or_external = 0
        for material in deleted_rows[:2000]:
            path = (material.storage_path or '').strip()
            if not path:
                continue
            if (settings.storage_provider or 'local').lower() != 'local':
                skipped_shared_or_external += 1
                continue
            try:
                root = Path(settings.local_storage_path or '/app/.runtime').expanduser().resolve()
                p = Path(path).expanduser()
                if not p.is_absolute():
                    p = root / p
                p = p.resolve()
                if root not in p.parents and p != root:
                    skipped_shared_or_external += 1
                    continue
                if p.is_file():
                    deleted_files += 1
                    deleted_file_bytes += int(p.stat().st_size)
            except Exception:
                skipped_shared_or_external += 1
        orphan_chunks = self.db.query(MaterialChunk).outerjoin(
            LearningMaterialVersion,
            LearningMaterialVersion.id == MaterialChunk.material_version_id,
        ).filter(LearningMaterialVersion.id.is_(None)).count()
        return {
            'ok': True,
            'policy': {
                'hard_delete_unused_enabled': bool(settings.bank_material_hard_delete_unused_enabled),
                'retention_days': int(settings.bank_material_deleted_retention_days),
                'file_purge_enabled': bool(settings.bank_material_purge_deleted_files_enabled),
                'storage_provider': settings.storage_provider,
            },
            'active_materials': int(active_query.count() or 0),
            'deleted_tombstones': int(deleted_count),
            'deleted_tombstones_with_local_file': int(deleted_files),
            'deleted_local_file_bytes_estimate': int(deleted_file_bytes),
            'deleted_files_skipped_shared_or_external_sample': int(skipped_shared_or_external),
            'sample_size': int(len(deleted_rows)),
            'orphan_chunks': int(orphan_chunks or 0),
        }

    def purge_deleted_materials(self, *, retention_days: int | None = None, dry_run: bool = True, limit: int | None = None, bank_version_id: str | None = None, chapter_id: str | None = None) -> dict[str, Any]:
        safe_limit = max(1, min(int(limit or settings.bank_material_cleanup_default_limit or 500), 5000))
        days = settings.bank_material_deleted_retention_days if retention_days is None else int(retention_days)
        cutoff = datetime.utcnow() if days <= 0 else datetime.utcnow() - timedelta(days=days)
        query = self.db.query(LearningMaterialVersion).filter(LearningMaterialVersion.status == 'deleted')
        query = query.filter(or_(LearningMaterialVersion.deleted_at.is_(None), LearningMaterialVersion.deleted_at <= cutoff))
        if bank_version_id:
            query = query.filter(LearningMaterialVersion.bank_version_id == bank_version_id)
        if chapter_id:
            query = query.filter(LearningMaterialVersion.chapter_id == chapter_id)
        rows = query.order_by(LearningMaterialVersion.deleted_at.asc().nullsfirst(), LearningMaterialVersion.created_at.asc()).limit(safe_limit).all()
        scanned = 0
        purgable = []
        blocked = []
        totals = {'chunks_deleted': 0, 'jobs_detached_count': 0, 'files_deleted': 0, 'files_skipped': 0, 'bytes_deleted': 0}
        for material in rows:
            scanned += 1
            counts = self._material_dependency_counts(material.id)
            blocking_counts = {k: int(counts.get(k) or 0) for k in ('questions', 'concepts', 'diff_items') if int(counts.get(k) or 0) > 0}
            if blocking_counts:
                blocked.append({'material_version_id': material.id, 'file_name': material.file_name, 'blocking_counts': blocking_counts})
                continue
            if dry_run:
                purgable.append({'material_version_id': material.id, 'file_name': material.file_name, 'bank_version_id': material.bank_version_id, 'chapter_id': material.chapter_id, 'counts': counts})
                continue
            result = self._hard_delete_material_version(material, reason='deleted_material_retention_purge')
            purgable.append(result)
            totals['chunks_deleted'] += int(result.get('chunks_deleted') or 0)
            totals['jobs_detached_count'] += int(result.get('jobs_detached_count') or 0)
            if result.get('file_deleted'):
                totals['files_deleted'] += 1
                totals['bytes_deleted'] += int(((result.get('file_result') or {}).get('bytes_deleted') or 0))
            if result.get('file_delete_skipped'):
                totals['files_skipped'] += 1
        orphan_chunks = int(self.db.query(MaterialChunk).outerjoin(
            LearningMaterialVersion,
            LearningMaterialVersion.id == MaterialChunk.material_version_id,
        ).filter(LearningMaterialVersion.id.is_(None)).count() or 0)
        orphan_chunks_deleted = 0
        if not dry_run and orphan_chunks:
            orphan_rows = self.db.query(MaterialChunk).outerjoin(
                LearningMaterialVersion,
                LearningMaterialVersion.id == MaterialChunk.material_version_id,
            ).filter(LearningMaterialVersion.id.is_(None)).limit(safe_limit).all()
            for chunk in orphan_rows:
                self.db.delete(chunk)
                orphan_chunks_deleted += 1
        if not dry_run:
            self.db.commit()
            if chapter_id:
                self._safe_refresh_chapter_stats(chapter_id)
        totals['orphan_chunks_found'] = int(orphan_chunks)
        totals['orphan_chunks_deleted'] = int(orphan_chunks_deleted)
        return {
            'ok': True,
            'dry_run': bool(dry_run),
            'retention_days': int(days),
            'cutoff': cutoff.isoformat(),
            'scanned': int(scanned),
            'purgable_count': int(len(purgable)),
            'blocked_count': int(len(blocked)),
            'purgable': purgable[:100],
            'blocked': blocked[:100],
            'totals': totals,
            'message': 'Đã kiểm tra tài liệu đã xóa mềm.' if dry_run else 'Đã purge tài liệu đã xóa mềm đủ điều kiện.',
        }

    def _generation_review_workflow(self) -> QuestionBankGenerationReviewWorkflowService:
        return QuestionBankGenerationReviewWorkflowService(self)

    def _bank_generation_content(self, *args, **kwargs):
        return self._generation_review_workflow()._bank_generation_content(*args, **kwargs)

    def _chunks_to_generation_content(self, *args, **kwargs):
        return self._generation_review_workflow()._chunks_to_generation_content(*args, **kwargs)

    def _split_count_evenly(self, *args, **kwargs):
        return self._generation_review_workflow()._split_count_evenly(*args, **kwargs)

    def _balanced_material_generation_plan(self, *args, **kwargs):
        return self._generation_review_workflow()._balanced_material_generation_plan(*args, **kwargs)

    def _difficulty_counts(self, *args, **kwargs):
        return self._generation_review_workflow()._difficulty_counts(*args, **kwargs)

    def _get_or_create_concept_version(self, *args, **kwargs):
        return self._generation_review_workflow()._get_or_create_concept_version(*args, **kwargs)

    def _get_or_create_bank_family(self, *args, **kwargs):
        return self._generation_review_workflow()._get_or_create_bank_family(*args, **kwargs)

    def _next_variant_no(self, *args, **kwargs):
        return self._generation_review_workflow()._next_variant_no(*args, **kwargs)

    def _chapter_question_count(self, *args, **kwargs):
        return self._generation_review_workflow()._chapter_question_count(*args, **kwargs)

    async def preview_generate_from_bank_version(self, *args, **kwargs):
        return await self._generation_review_workflow().preview_generate_from_bank_version(*args, **kwargs)

    async def generate_from_bank_version(self, *args, **kwargs):
        return await self._generation_review_workflow().generate_from_bank_version(*args, **kwargs)

    def _require_bank_question(self, *args, **kwargs):
        return self._generation_review_workflow()._require_bank_question(*args, **kwargs)

    def update_bank_question(self, *args, **kwargs):
        return self._generation_review_workflow().update_bank_question(*args, **kwargs)

    def review_bank_question(self, *args, **kwargs):
        return self._generation_review_workflow().review_bank_question(*args, **kwargs)

    def bulk_review_bank_questions(self, *args, **kwargs):
        return self._generation_review_workflow().bulk_review_bank_questions(*args, **kwargs)

    def mark_document_diff_resolved(self, *args, **kwargs):
        return self._generation_review_workflow().mark_document_diff_resolved(*args, **kwargs)

    def release_readiness(self, *, bank_version_id: str) -> dict:
        return self._release_publish_workflow().release_readiness(bank_version_id=bank_version_id)

    def list_course_quiz_instances(self, *, openedx_course_id: str | None = None, bank_release_id: str | None = None, limit: int = 100) -> list[CourseQuizInstance]:
        return self._release_publish_workflow().list_course_quiz_instances(openedx_course_id=openedx_course_id, bank_release_id=bank_release_id, limit=limit)

    async def rollback_course_quiz_instance(self, *, instance_id: str, mode: str = 'safe', note: str = '', actor: str | None = None) -> dict:
        return await self._release_publish_workflow().rollback_course_quiz_instance(instance_id=instance_id, mode=mode, note=note, actor=actor)

    def _normalize_release_term_slug(self, value: str | None) -> str:
        return self._release_publish_workflow()._normalize_release_term_slug(value)

    def _release_offering_term_slug(self, *, subject: Subject, version: QuestionBankVersion) -> str:
        return self._release_publish_workflow()._release_offering_term_slug(subject=subject, version=version)

    def release_library_key(self, *, subject: Subject, chapter: SubjectChapter, version: QuestionBankVersion) -> str:
        return self._release_publish_workflow().release_library_key(subject=subject, chapter=chapter, version=version)

    def _release_library_key_needs_term_upgrade(self, *, library_key: str | None, subject: Subject, version: QuestionBankVersion) -> bool:
        return self._release_publish_workflow()._release_library_key_needs_term_upgrade(library_key=library_key, subject=subject, version=version)

    def _library_key_same(self, left: str | None, right: str | None) -> bool:
        return self._release_publish_workflow()._library_key_same(left, right)

    def _reset_release_openedx_state_for_key_change(self, *, release: QuestionBankRelease, expected_library_key: str, reason: str) -> None:
        return self._release_publish_workflow()._reset_release_openedx_state_for_key_change(release=release, expected_library_key=expected_library_key, reason=reason)

    def _cleanup_stale_release_keys_for_chapter(self, *, chapter_id: str, expected_library_key: str) -> None:
        return self._release_publish_workflow()._cleanup_stale_release_keys_for_chapter(chapter_id=chapter_id, expected_library_key=expected_library_key)

    def _release_questions_for_version(self, version: QuestionBankVersion) -> list[Question]:
        return self._release_publish_workflow()._release_questions_for_version(version)

    def create_release(self, *, bank_version_id: str, title: str | None = None, actor: str | None = None) -> QuestionBankRelease:
        return self._release_publish_workflow().create_release(bank_version_id=bank_version_id, title=title, actor=actor)

    def cancel_failed_release(self, *, release_id: str, actor: str | None = None, note: str = '') -> QuestionBankRelease:
        return self._release_publish_workflow().cancel_failed_release(release_id=release_id, actor=actor, note=note)

    def _course_mapping_validation(self, *, openedx_course_id: str, subject_id: str, subject_offering_id: str | None = None, department_id: str | None = None, term: str | None = None, openedx_course_title: str | None = None) -> dict:
        checks: list[dict] = []
        subject = self.db.get(Subject, subject_id)
        offering = self.db.get(SubjectOffering, subject_offering_id) if subject_offering_id else None
        if subject_offering_id and (not offering or offering.subject_id != subject_id):
            checks.append(_check('subject_offering_match', 'fail', 'Phiên bản môn không thuộc môn đã chọn.', blocking=True))
        elif offering:
            checks.append(_check('subject_offering_match', 'pass', f'Đang map vào version triển khai {offering.code}.', blocking=False))
        if not subject:
            checks.append(_check('subject_exists', 'fail', 'Không tìm thấy môn học đã chọn.'))
            return self._validation_result(checks)
        department = self.db.get(Department, department_id) if department_id else None
        if department_id and not department:
            checks.append(_check('department_exists', 'fail', 'Không tìm thấy bộ môn đã chọn.'))
        if department and subject.department_id != department.id:
            checks.append(_check('subject_department_match', 'fail', f'Môn {subject.code} không thuộc bộ môn đã chọn.'))
        parsed = parse_openedx_course_id(openedx_course_id)
        if not parsed['ok']:
            checks.append(_check('course_id_format', 'fail', 'Course ID phải có dạng course-v1:ORG+COURSE+RUN.'))
        else:
            checks.append(_check('course_id_format', 'pass', f'Course ID hợp lệ: org={parsed["org"]}, code={parsed["course_code"]}, run={parsed["run"]}.'))
            if normalize_code(parsed['course_code']) == normalize_code(subject.code):
                checks.append(_check('course_code_match', 'pass', f'Mã course {parsed["course_code"]} khớp môn {subject.code}.'))
            else:
                checks.append(_check('course_code_match', 'fail', f'Mã course là {parsed["course_code"]}, nhưng môn đã chọn là {subject.code}. Không map để tránh dán nhầm ngân hàng đề.'))
            expected_term = term or (offering.term if offering else None)
            if expected_term and parsed.get('run'):
                try:
                    normalized_expected = str(normalize_academic_term_code(term=expected_term)['term_code'])
                except Exception:
                    normalized_expected = expected_term
                if normalize_code(normalized_expected) == normalize_code(parsed.get('run')):
                    checks.append(_check('term_match', 'pass', f'Kỳ course {parsed.get("run")} khớp phiên bản môn {normalized_expected}.', blocking=False))
                else:
                    checks.append(_check('term_match', 'warn', f'Kỳ/phiên bản môn là {normalized_expected}, nhưng course run là {parsed.get("run")}. Cần kiểm tra tránh map nhầm kỳ.', blocking=False))
        existing = self.db.query(EdxCourseMapping).filter(EdxCourseMapping.openedx_course_id == openedx_course_id.strip()).first()
        if existing:
            if existing.subject_id == subject.id:
                checks.append(_check('existing_mapping', 'warn', 'Course này đã được map vào môn này. Nếu lưu lại sẽ bị từ chối để tránh trùng mapping.', {'mapping_id': existing.id}, blocking=True))
            else:
                checks.append(_check('existing_mapping', 'fail', 'Course này đã được map vào môn khác. Không tự ghi đè mapping cũ.', {'mapping_id': existing.id, 'subject_id': existing.subject_id}))
        if openedx_course_title:
            sim = title_similarity(openedx_course_title, subject.name)
            if sim >= 0.55:
                checks.append(_check('course_title_similarity', 'pass', f'Tên course khá khớp với tên môn ({sim:.0%}).', {'similarity': sim}, blocking=False))
            elif sim >= 0.35:
                checks.append(_check('course_title_similarity', 'warn', f'Tên course hơi khác tên môn ({sim:.0%}). Cần kiểm tra lại.', {'similarity': sim}, blocking=False))
            else:
                checks.append(_check('course_title_similarity', 'warn', f'Tên course khác tên môn ({sim:.0%}). Cần xác nhận thủ công trước khi tạo quiz.', {'similarity': sim}, blocking=False))
        return self._validation_result(checks)

    def validate_course_mapping(self, **kwargs) -> dict:
        return self._course_mapping_validation(**kwargs)

    def create_course_mapping(self, *, openedx_course_id: str, subject_id: str, subject_offering_id: str | None = None, department_id: str | None = None, term: str | None = None, actor: str | None = None, allow_warnings: bool = False, openedx_course_title: str | None = None) -> EdxCourseMapping:
        validation = self._course_mapping_validation(openedx_course_id=openedx_course_id, subject_id=subject_id, subject_offering_id=subject_offering_id, department_id=department_id, term=term, openedx_course_title=openedx_course_title)
        if not validation['can_create_mapping']:
            raise ValueError(validation['message'])
        if validation['risk_level'] == 'medium' and not allow_warnings:
            raise ValueError('Mapping có cảnh báo. Hãy kiểm tra lại và gửi allow_warnings=true nếu vẫn muốn lưu.')
        item = EdxCourseMapping(
            id=str(uuid.uuid4()),
            openedx_course_id=openedx_course_id.strip(),
            subject_id=subject_id,
            subject_offering_id=subject_offering_id,
            department_id=department_id,
            term=term,
            created_by=actor,
            validation_status=validation['risk_level'],
            validation_json=validation,
            validated_at=datetime.utcnow(),
        )
        self.db.add(item)
        self.db.commit()
        self.db.refresh(item)
        return item

    def _chapter_mapping_validation(self, *, course_mapping_id: str, subject_chapter_id: str, bank_release_id: str | None = None, openedx_parent_node_id: str | None = None, openedx_node_title: str | None = None) -> dict:
        checks: list[dict] = []
        mapping = self.db.get(EdxCourseMapping, course_mapping_id)
        chapter = self.db.get(SubjectChapter, subject_chapter_id)
        if not mapping:
            checks.append(_check('course_mapping_exists', 'fail', 'Không tìm thấy mapping course.'))
        if not chapter:
            checks.append(_check('subject_chapter_exists', 'fail', 'Không tìm thấy chapter trong ngân hàng đề.'))
        if not mapping or not chapter:
            return self._validation_result(checks)
        if mapping.subject_id != chapter.subject_id:
            checks.append(_check('chapter_subject_match', 'fail', 'Chapter đã chọn không thuộc môn đang map với course.'))
        if mapping.subject_offering_id and chapter.subject_offering_id and mapping.subject_offering_id != chapter.subject_offering_id:
            checks.append(_check('chapter_offering_match', 'fail', 'Chapter đã chọn không thuộc phiên bản môn đang map với course.'))
        release = self.db.get(QuestionBankRelease, bank_release_id) if bank_release_id else None
        if not bank_release_id:
            checks.append(_check('release_required', 'fail', 'Phải chọn Bank Release để map chapter.'))
        elif not release:
            checks.append(_check('release_exists', 'fail', 'Không tìm thấy Bank Release.'))
        else:
            if release.subject_id != mapping.subject_id:
                checks.append(_check('release_subject_match', 'fail', 'Release không thuộc môn đang map với course.'))
            if release.chapter_id != chapter.id:
                checks.append(_check('release_chapter_match', 'fail', 'Release không thuộc chapter đã chọn.'))
            if release.status != 'published':
                checks.append(_check('release_published', 'fail', f'Release hiện là {release.status}; chỉ được map release đã publish thật sang Open edX Library.'))
            else:
                checks.append(_check('release_published', 'pass', f'Release {release.release_code} đã published.'))
            if not release.openedx_library_key:
                checks.append(_check('release_library_key', 'fail', 'Release chưa có Open edX Library key.'))
            else:
                checks.append(_check('release_library_key', 'pass', f'Library: {release.openedx_library_key}', {'openedx_library_key': release.openedx_library_key}, blocking=False))
        if openedx_parent_node_id:
            parsed_course = parse_openedx_course_id(mapping.openedx_course_id)
            parsed_block = extract_block_course_tuple(openedx_parent_node_id)
            if not parsed_block['ok']:
                checks.append(_check('openedx_node_format', 'fail', 'Node Open edX phải là block-v1 usage key hợp lệ.'))
            else:
                if parsed_course['ok'] and (
                    normalize_code(parsed_course['org']) != normalize_code(parsed_block['org'])
                    or normalize_code(parsed_course['course_code']) != normalize_code(parsed_block['course_code'])
                    or normalize_code(parsed_course['run']) != normalize_code(parsed_block['run'])
                ):
                    checks.append(_check('openedx_node_course_match', 'fail', 'Node đã chọn không thuộc course đang map.'))
                else:
                    checks.append(_check('openedx_node_course_match', 'pass', 'Node thuộc đúng course.'))
                if parsed_block.get('block_type') not in {'chapter', 'sequential', 'vertical'}:
                    checks.append(_check('openedx_node_type', 'warn', f'Node type là {parsed_block.get("block_type")}; nên chọn chapter/sequential/vertical.', {'block_type': parsed_block.get('block_type')}, blocking=False))
            synced = self.db.query(CourseSyncState).filter(
                CourseSyncState.course_id == mapping.openedx_course_id,
                CourseSyncState.block_id == openedx_parent_node_id,
            ).first()
            title = openedx_node_title or (synced.display_name if synced else None)
            if synced:
                checks.append(_check('openedx_node_synced', 'pass', f'Đã tìm thấy node trong cây sync: {synced.display_name}', {'block_type': synced.block_type}, blocking=False))
            else:
                checks.append(_check('openedx_node_synced', 'warn', 'Chưa thấy node này trong dữ liệu sync AI Server. Nên sync course trước khi tạo quiz.', blocking=False))
            if title:
                sim = title_similarity(title, chapter.title)
                chapter_no_in_title = re.search(r'\b(?:bài|bai|chapter)\s*([0-9]+(?:\.[0-9]+)*)\b', title.lower())
                bank_chapter_label = re.search(r'\b(?:bài|bai|chapter)\s*([0-9]+(?:\.[0-9]+)*)\b', (chapter.title or '').lower())
                if chapter_no_in_title and bank_chapter_label and chapter_no_in_title.group(1) != bank_chapter_label.group(1):
                    checks.append(_check('chapter_number_match', 'fail', f'Node Open edX có vẻ là Bài {chapter_no_in_title.group(1)}, nhưng ngân hàng là {self._chapter_display_name(chapter)}.'))
                elif sim >= 0.45:
                    checks.append(_check('chapter_title_match', 'pass', f'Tên chapter khá khớp ({sim:.0%}).', {'similarity': sim}, blocking=False))
                else:
                    checks.append(_check('chapter_title_match', 'warn', f'Tên node Open edX khác tên chapter ngân hàng ({sim:.0%}). Cần kiểm tra lại.', {'similarity': sim}, blocking=False))
        else:
            checks.append(_check('openedx_node_required', 'fail', 'Phải chọn node chapter/sequential/vertical từ cây Open edX, không để trống.'))
        existing = self.db.query(EdxCourseChapterMapping).filter(
            EdxCourseChapterMapping.course_mapping_id == course_mapping_id,
            EdxCourseChapterMapping.subject_chapter_id == subject_chapter_id,
        ).first()
        if existing:
            checks.append(_check('existing_chapter_mapping', 'fail', 'Chapter này đã được map cho course. Không tạo trùng mapping.', {'mapping_id': existing.id}))
        return self._validation_result(checks)

    def validate_course_chapter_mapping(self, **kwargs) -> dict:
        return self._chapter_mapping_validation(**kwargs)

    def create_course_chapter_mapping(self, *, course_mapping_id: str, subject_chapter_id: str, bank_release_id: str | None = None, openedx_parent_node_id: str | None = None, openedx_node_title: str | None = None, enabled: bool = True, allow_warnings: bool = False) -> EdxCourseChapterMapping:
        validation = self._chapter_mapping_validation(course_mapping_id=course_mapping_id, subject_chapter_id=subject_chapter_id, bank_release_id=bank_release_id, openedx_parent_node_id=openedx_parent_node_id, openedx_node_title=openedx_node_title)
        if not validation['can_create_mapping']:
            raise ValueError(validation['message'])
        if validation['risk_level'] == 'medium' and not allow_warnings:
            raise ValueError('Mapping chapter có cảnh báo. Hãy kiểm tra lại và gửi allow_warnings=true nếu vẫn muốn lưu.')
        item = EdxCourseChapterMapping(
            id=str(uuid.uuid4()),
            course_mapping_id=course_mapping_id,
            subject_chapter_id=subject_chapter_id,
            bank_release_id=bank_release_id,
            openedx_parent_node_id=openedx_parent_node_id,
            enabled=enabled,
            validation_status=validation['risk_level'],
            validation_json=validation,
            validated_at=datetime.utcnow(),
        )
        self.db.add(item)
        self.db.commit()
        self.db.refresh(item)
        return item

    def _quiz_creation_workflow(self) -> QuestionBankQuizCreationWorkflowService:
        return QuestionBankQuizCreationWorkflowService(self)

    def _latest_published_release_for_chapter(self, chapter_id: str) -> QuestionBankRelease | None:
        return self._quiz_creation_workflow()._latest_published_release_for_chapter(chapter_id)

    def _release_component_ready(self, release: QuestionBankRelease | None) -> tuple[bool, int, int]:
        return self._quiz_creation_workflow()._release_component_ready(release)

    def _offering_published_release_status(self, offering: SubjectOffering) -> dict:
        return self._quiz_creation_workflow()._offering_published_release_status(offering)

    @staticmethod
    def _quiz_action_for_chapter_title(title: str | None) -> str:
        return QuestionBankQuizCreationWorkflowService._quiz_action_for_chapter_title(title)

    @staticmethod
    def _normalize_quiz_chapter_plan(chapter_plan: list[dict] | None) -> dict[str, str]:
        return QuestionBankQuizCreationWorkflowService._normalize_quiz_chapter_plan(chapter_plan)

    @staticmethod
    def _quiz_action_requires_release(action: str | None) -> bool:
        return QuestionBankQuizCreationWorkflowService._quiz_action_requires_release(action)

    @staticmethod
    def _quiz_action_label(action: str | None) -> str:
        return QuestionBankQuizCreationWorkflowService._quiz_action_label(action)

    @staticmethod
    def _quiz_production_status_for_mapping(*, action: str | None, section: dict | None, release_info: dict | None) -> dict:
        return QuestionBankQuizCreationWorkflowService._quiz_production_status_for_mapping(action=action, section=section, release_info=release_info)

    async def _load_openedx_sections_for_quiz(self, course_id: str) -> tuple[list[dict], list[str]]:
        return await self._quiz_creation_workflow()._load_openedx_sections_for_quiz(course_id)

    def _match_chapter_to_section(self, chapter: SubjectChapter, sections: list[dict], used_section_ids: set[str]) -> tuple[dict | None, float, str]:
        return self._quiz_creation_workflow()._match_chapter_to_section(chapter, sections, used_section_ids)

    def _format_offering_candidate(self, *, offering: SubjectOffering, subject: Subject, course_meta: dict, validation: dict, release_status: dict) -> dict:
        return self._quiz_creation_workflow()._format_offering_candidate(offering=offering, subject=subject, course_meta=course_meta, validation=validation, release_status=release_status)

    def _select_offering_for_course(self, *, course_id: str, selected_subject_offering_id: str | None = None) -> dict:
        return self._quiz_creation_workflow()._select_offering_for_course(course_id=course_id, selected_subject_offering_id=selected_subject_offering_id)

    async def preview_quiz_auto_map(self, *, openedx_course_id: str, selected_subject_offering_id: str | None = None, chapter_plan: list[dict] | None = None) -> dict:
        return await self._quiz_creation_workflow().preview_quiz_auto_map(openedx_course_id=openedx_course_id, selected_subject_offering_id=selected_subject_offering_id, chapter_plan=chapter_plan)

    async def apply_quiz_auto_map(self, *, openedx_course_id: str, selected_subject_offering_id: str | None = None, chapter_plan: list[dict] | None = None, actor: str | None = None) -> dict:
        return await self._quiz_creation_workflow().apply_quiz_auto_map(openedx_course_id=openedx_course_id, selected_subject_offering_id=selected_subject_offering_id, chapter_plan=chapter_plan, actor=actor)

    def _validation_result(self, checks: list[dict]) -> dict:
        return self._quiz_creation_workflow()._validation_result(checks)

    def _target_counts_for_quiz(self, total_questions: int, easy: int, medium: int, hard: int) -> dict[str, int]:
        return self._quiz_creation_workflow()._target_counts_for_quiz(total_questions, easy, medium, hard)

    def _published_release_question_rows(self, release: QuestionBankRelease) -> list[BankReleaseQuestion]:
        return self._quiz_creation_workflow()._published_release_question_rows(release)

    def _build_release_quiz_plan(self, *, release_id: str, openedx_course_id: str, parent_node_id: str | None = None, total_questions: int = 15, difficulty_easy: int = 50, difficulty_medium: int = 30, difficulty_hard: int = 20, max_families_per_bank: int = 2) -> dict:
        return self._quiz_creation_workflow()._build_release_quiz_plan(release_id=release_id, openedx_course_id=openedx_course_id, parent_node_id=parent_node_id, total_questions=total_questions, difficulty_easy=difficulty_easy, difficulty_medium=difficulty_medium, difficulty_hard=difficulty_hard, max_families_per_bank=max_families_per_bank)

    def preview_quiz_from_release(self, *, release_id: str, openedx_course_id: str, parent_node_id: str | None = None, total_questions: int = 15, difficulty_easy: int = 50, difficulty_medium: int = 30, difficulty_hard: int = 20, max_families_per_bank: int = 2) -> dict:
        return self._quiz_creation_workflow().preview_quiz_from_release(release_id=release_id, openedx_course_id=openedx_course_id, parent_node_id=parent_node_id, total_questions=total_questions, difficulty_easy=difficulty_easy, difficulty_medium=difficulty_medium, difficulty_hard=difficulty_hard, max_families_per_bank=max_families_per_bank)

    async def create_quiz_from_release(self, *, release_id: str, openedx_course_id: str, parent_node_id: str | None = None, quiz_title: str, unit_title: str | None = None, total_questions: int = 15, difficulty_easy: int = 50, difficulty_medium: int = 30, difficulty_hard: int = 20, max_families_per_bank: int = 2, actor: str | None = None, custom_timer_enabled: bool = True, time_limit_minutes: int = 15, retake_cooldown_minutes: int = 0, native_timed_exam: bool = False, assessment_type: str = 'quiz') -> dict:
        return await self._quiz_creation_workflow().create_quiz_from_release(release_id=release_id, openedx_course_id=openedx_course_id, parent_node_id=parent_node_id, quiz_title=quiz_title, unit_title=unit_title, total_questions=total_questions, difficulty_easy=difficulty_easy, difficulty_medium=difficulty_medium, difficulty_hard=difficulty_hard, max_families_per_bank=max_families_per_bank, actor=actor, custom_timer_enabled=custom_timer_enabled, time_limit_minutes=time_limit_minutes, retake_cooldown_minutes=retake_cooldown_minutes, native_timed_exam=native_timed_exam, assessment_type=assessment_type)


    def create_quiz_blueprint(self, *, subject_id: str, chapter_id: str, title: str, total_questions: int, difficulty_easy: int, difficulty_medium: int, difficulty_hard: int, max_families_per_bank: int = 2, pick_count_per_slot: int = 1) -> QuizBlueprint:
        total_pct = difficulty_easy + difficulty_medium + difficulty_hard
        if total_pct != 100:
            raise ValueError('Tỷ lệ EASY/MEDIUM/HARD phải bằng 100')
        item = QuizBlueprint(id=str(uuid.uuid4()), subject_id=subject_id, chapter_id=chapter_id, subject_offering_id=None, title=title, total_questions=total_questions, difficulty_easy=difficulty_easy, difficulty_medium=difficulty_medium, difficulty_hard=difficulty_hard, max_families_per_bank=max_families_per_bank, pick_count_per_slot=pick_count_per_slot)
        self.db.add(item)
        self.db.commit()
        self.db.refresh(item)
        return item


    def release_publish_audit(self, *, release_id: str) -> dict:
        return self._release_publish_workflow().release_publish_audit(release_id=release_id)

    def _release_publish_course_id(self, release: QuestionBankRelease, subject: Subject, course_id_for_org: str | None = None) -> str:
        return self._release_publish_workflow()._release_publish_course_id(release, subject, course_id_for_org)

    async def publish_release_to_openedx(self, *, release_id: str, actor: str | None = None, course_id_for_org: str | None = None, force_reimport: bool = False) -> dict:
        return await self._release_publish_workflow().publish_release_to_openedx(release_id=release_id, actor=actor, course_id_for_org=course_id_for_org, force_reimport=force_reimport)
