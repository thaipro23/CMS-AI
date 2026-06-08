from __future__ import annotations

import hashlib
import json
import re
import uuid
from pathlib import Path
from datetime import datetime
from difflib import SequenceMatcher
from typing import Any

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.course import CourseSyncState
from app.models.question import Question
from app.models.question_bank import (
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
    Subject,
    SubjectOffering,
    SubjectChapter,
)
from app.modules.openedx_connector.factory import get_openedx_connector
from app.services.openedx_exporter import question_to_openedx_olx
from app.services.answer_randomizer import normalize_and_shuffle_options
from app.services.chunker import Chunker
from app.services.content_extractor import ContentExtractor
from app.services.generation_cache import question_fingerprint, sha256_text
from app.services.model_gateway import ModelGateway
from app.services.quality_checker import QualityChecker
from app.services.question_family import build_question_family_id, normalize_difficulty
from app.services.token_counter import count_tokens


def slugify(value: str, fallback: str = 'item') -> str:
    text = (value or '').strip().lower()
    text = re.sub(r'[^a-z0-9]+', '-', text)
    text = re.sub(r'-+', '-', text).strip('-')
    return text or fallback


def normalize_text(value: str | None) -> str:
    return re.sub(r'\s+', ' ', (value or '').strip().lower())


def normalize_code(value: str | None) -> str:
    return re.sub(r'[^a-z0-9]', '', (value or '').lower())


def parse_openedx_course_id(course_id: str) -> dict[str, str | None]:
    text = (course_id or '').strip()
    match = re.match(r'^course-v1:([^+]+)\+([^+]+)\+(.+)$', text)
    if not match:
        return {'ok': False, 'org': None, 'course_code': None, 'run': None}
    return {'ok': True, 'org': match.group(1), 'course_code': match.group(2), 'run': match.group(3)}


TERM_SEASON_LABELS = {
    'SP': {'en': 'Spring', 'vi': 'Xuân'},
    'SU': {'en': 'Summer', 'vi': 'Hè'},
    'FA': {'en': 'Fall', 'vi': 'Fall/Đông'},
}

def normalize_academic_term_code(*, term: str | None = None, season: str | None = None, year: int | str | None = None, code: str | None = None) -> dict[str, str | int | None]:
    """Normalize FPT-style academic term codes.

    Term is the version layer of a subject version, not an Open edX course run.
    Supported seasons: SP (Spring/Xuân), SU (Summer/Hè), FA (Fall/Đông).
    Examples: SP25, SU26, FA27. The numeric suffix is the 2-digit year.
    """
    raw = (term or code or '').strip().upper().replace('_', '').replace('-', '').replace(' ', '')
    parsed_season = None
    parsed_year = None
    match = re.match(r'^(SP|SU|FA)(\d{2}|\d{4})$', raw)
    if match:
        parsed_season = match.group(1)
        parsed_year = int(match.group(2))
    if season:
        s = season.strip().upper()
        aliases = {'SPRING': 'SP', 'XUAN': 'SP', 'XUÂN': 'SP', 'SUMMER': 'SU', 'HE': 'SU', 'HÈ': 'SU', 'FALL': 'FA', 'AUTUMN': 'FA', 'THU': 'FA', 'DONG': 'FA', 'ĐÔNG': 'FA'}
        parsed_season = aliases.get(s, s[:2])
    if year is not None and str(year).strip():
        y = int(str(year).strip())
        parsed_year = y
    if parsed_season not in TERM_SEASON_LABELS:
        raise ValueError('Kỳ chỉ hỗ trợ SP/Spring, SU/Summer, FA/Fall. Ví dụ: SP25, SU26, FA27.')
    if parsed_year is None:
        raise ValueError('Thiếu năm của kỳ. Ví dụ: SP25 nghĩa là Spring 2025.')
    year2 = parsed_year % 100
    year_full = 2000 + year2 if parsed_year < 100 else parsed_year
    term_code = f'{parsed_season}{year2:02d}'
    labels = TERM_SEASON_LABELS[parsed_season]
    return {
        'term_code': term_code,
        'season': parsed_season,
        'season_name': labels['en'],
        'season_name_vi': labels['vi'],
        'year': year_full,
        'year_short': f'{year2:02d}',
        'display_name': f"{labels['en']} {year_full}",
        'display_name_vi': f"{labels['vi']} {year_full}",
    }


def extract_block_course_tuple(block_id: str | None) -> dict[str, str | None]:
    text = (block_id or '').strip()
    match = re.match(r'^block-v1:([^+]+)\+([^+]+)\+([^+]+)\+type@([^+]+)\+block@(.+)$', text)
    if not match:
        return {'ok': False, 'org': None, 'course_code': None, 'run': None, 'block_type': None}
    return {'ok': True, 'org': match.group(1), 'course_code': match.group(2), 'run': match.group(3), 'block_type': match.group(4)}


def title_similarity(a: str | None, b: str | None) -> float:
    a_norm = normalize_text(a)
    b_norm = normalize_text(b)
    if not a_norm or not b_norm:
        return 0.0
    return SequenceMatcher(None, a_norm, b_norm).ratio()



BANK_UPLOAD_ALLOWED_EXTENSIONS = {
    'pdf', 'pptx', 'ppt', 'docx', 'xlsx', 'xlsm', 'csv', 'tsv',
    'txt', 'md', 'markdown', 'html', 'htm', 'json', 'xml', 'vtt', 'srt',
}
BANK_UPLOAD_LEGACY_OFFICE_EXTENSIONS = {'doc', 'xls'}
BANK_UPLOAD_MAX_BYTES = 50 * 1024 * 1024


def safe_upload_filename(filename: str) -> str:
    name = (filename or 'uploaded-file').replace('\\', '/').rsplit('/', 1)[-1].strip()
    name = re.sub(r'[^0-9A-Za-zÀ-ỹ._ -]+', '_', name)
    return name[:180] or 'uploaded-file'


def upload_extension(filename: str) -> str:
    name = filename.rsplit('.', 1)
    return name[1].lower() if len(name) == 2 else ''


def chunk_policy_for_material_source(source_type: str) -> tuple[int, int]:
    source = (source_type or '').lower()
    if source in {'csv', 'tsv', 'xlsx', 'xlsm'}:
        return 1100, 80
    if source in {'pdf', 'pptx', 'ppt', 'docx'}:
        return 1000, 120
    if source in {'srt', 'vtt'}:
        return 900, 100
    return 1000, 100


def bank_material_storage_dir(bank_version_id: str) -> Path:
    root = Path(settings.local_storage_path or '/tmp/ai-openedx-storage')
    return root / 'question-bank' / str(bank_version_id)


def _check(code: str, status: str, message: str, detail: dict | None = None, blocking: bool | None = None) -> dict[str, Any]:
    if blocking is None:
        blocking = status == 'fail'
    return {'code': code, 'status': status, 'message': message, 'blocking': bool(blocking), 'detail': detail or {}}


def question_lineage_root(question: Question) -> str:
    return question.lineage_root_question_id or question.previous_question_id or question.id


def normalize_question_text_for_diff(value: str | None) -> str:
    return re.sub(r'[^a-z0-9à-ỹ]+', ' ', (value or '').lower()).strip()


def bank_text_similarity(a: str | None, b: str | None) -> float:
    a_norm = normalize_question_text_for_diff(a)
    b_norm = normalize_question_text_for_diff(b)
    if not a_norm or not b_norm:
        return 0.0
    if a_norm == b_norm:
        return 1.0
    # Avoid O(n^2) huge comparisons from full documents by capping the strings.
    return SequenceMatcher(None, a_norm[:12000], b_norm[:12000]).ratio()


def stable_concept_identity(question: Question) -> str:
    return slugify(question.concept_key or question.concept_title or question.topic or question.learning_objective or 'unknown-concept', 'concept')


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
            'bank_questions': self.db.query(Question).filter(Question.bank_version_id.isnot(None)).count(),
            'bank_diffs': self.db.query(BankVersionDiff).count(),
            'carry_over_questions': self.db.query(Question).filter(Question.is_carry_over.is_(True)).count(),
            'retired_questions': self.db.query(Question).filter(Question.is_retired.is_(True)).count(),
        }

    def create_department(self, *, code: str, name: str, description: str = '') -> Department:
        item = Department(id=str(uuid.uuid4()), code=code.strip().upper(), name=name.strip(), description=description or '')
        self.db.add(item)
        self.db.commit()
        self.db.refresh(item)
        return item

    def create_subject(self, *, department_id: str, code: str, name: str, description: str = '') -> Subject:
        item = Subject(id=str(uuid.uuid4()), department_id=department_id, code=code.strip().upper(), name=name.strip(), description=description or '')
        self.db.add(item)
        self.db.commit()
        self.db.refresh(item)
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

        A new offering can be cloned from another offering. Clone means new DB
        rows are created for chapters, bank versions, materials, chunks,
        concepts, families, and reusable approved questions. No IDs and no Open
        edX Library/component IDs are reused.
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
                'clone_policy': 'new_records_no_shared_ids',
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
                clone_chapters=clone_chapters,
                clone_materials=clone_materials,
                clone_questions=clone_questions,
            )
            item.metadata_json = {**(item.metadata_json or {}), 'cloned_from_offering_id': source_offering.id, 'clone_result': clone_result}

        self.db.commit()
        self.db.refresh(item)
        return item

    def _clone_subject_offering_content(
        self,
        *,
        source: SubjectOffering,
        target: SubjectOffering,
        actor: str | None = None,
        clone_chapters: bool = True,
        clone_materials: bool = True,
        clone_questions: bool = True,
    ) -> dict:
        """Clone a complete subject-version snapshot into a new subject-version.

        This avoids re-uploading unchanged material and avoids manually creating
        Bài 1/Bài 2/Bài 3 again. Everything is copied as a new row, while
        lineage fields point back to the source records for audit.
        """
        chapter_map: dict[str, SubjectChapter] = {}
        bank_map: dict[str, QuestionBankVersion] = {}
        material_map: dict[str, LearningMaterialVersion] = {}
        concept_map: dict[str, ConceptVersion] = {}
        family_map: dict[str, BankQuestionFamily] = {}
        counts = {'chapters': 0, 'bank_versions': 0, 'materials': 0, 'chunks': 0, 'concepts': 0, 'families': 0, 'questions': 0, 'releases_skipped': 0}

        if clone_chapters:
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
            dst_bv = QuestionBankVersion(
                id=str(uuid.uuid4()),
                subject_id=target.subject_id,
                chapter_id=dst_chapter.id,
                subject_offering_id=target.id,
                version_no=src_bv.version_no,
                version_code=src_bv.version_code,
                title=src_bv.title,
                change_note=f'Clone từ {source.code}: {src_bv.change_note or ""}'.strip(),
                status=dst_status,
                based_on_version_id=src_bv.id,
                created_by=actor,
                approved_by=actor if dst_status == 'approved' else None,
                published_at=None,
                metadata_json={**(src_bv.metadata_json or {}), 'cloned_from_bank_version_id': src_bv.id, 'cloned_from_offering_id': source.id, 'clone_policy': 'new_records_no_shared_ids'},
            )
            self.db.add(dst_bv)
            self.db.flush()
            bank_map[src_bv.id] = dst_bv
            counts['bank_versions'] += 1

            if clone_materials:
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
                        change_type='cloned_from_previous_term',
                        uploaded_by=actor or src_mat.uploaded_by,
                        status=src_mat.status,
                    )
                    self.db.add(dst_mat)
                    self.db.flush()
                    material_map[src_mat.id] = dst_mat
                    counts['materials'] += 1
                    for src_chunk in self.db.query(MaterialChunk).filter(MaterialChunk.material_version_id == src_mat.id).order_by(MaterialChunk.chunk_index.asc()).all():
                        self.db.add(MaterialChunk(
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
                        ))
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

            if clone_questions:
                questions = self.db.query(Question).filter(
                    Question.bank_version_id == src_bv.id,
                    Question.status.in_(['approved', 'published']),
                    Question.is_retired.is_(False),
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
                        source_chunk_id=src_q.source_chunk_id,
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

        counts['releases_skipped'] = self.db.query(QuestionBankRelease).filter(QuestionBankRelease.subject_offering_id == source.id).count()
        return counts

    def create_chapter(self, *, subject_id: str, chapter_no: int, title: str, description: str = '', sort_order: int | None = None, subject_offering_id: str | None = None) -> SubjectChapter:
        if subject_offering_id:
            offering = self.db.get(SubjectOffering, subject_offering_id)
            if not offering or offering.subject_id != subject_id:
                raise ValueError('Phiên bản môn không thuộc môn đã chọn')
        item = SubjectChapter(id=str(uuid.uuid4()), subject_id=subject_id, subject_offering_id=subject_offering_id, chapter_no=chapter_no, title=title.strip(), description=description or '', sort_order=sort_order or chapter_no)
        self.db.add(item)
        self.db.commit()
        self.db.refresh(item)
        return item

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
        item = QuestionBankVersion(
            id=str(uuid.uuid4()),
            subject_id=subject_id,
            chapter_id=chapter_id,
            version_no=self.next_bank_version_no(subject_id, chapter_id),
            subject_offering_id=subject_offering_id,
            version_code=version_code.strip() or 'v1.0',
            title=title.strip(),
            change_note=change_note or '',
            based_on_version_id=based_on_version_id,
            created_by=actor,
            metadata_json={'architecture': 'question_bank_first', 'release_policy': 'one_release_one_openedx_library'},
        )
        self.db.add(item)
        self.db.commit()
        self.db.refresh(item)
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
        if source.subject_id != target.subject_id or source.chapter_id != target.chapter_id:
            raise ValueError('Chỉ được diff/carry-over giữa các Bank Version cùng môn và cùng chapter')
        if source.subject_offering_id and target.subject_offering_id and source.subject_offering_id != target.subject_offering_id:
            raise ValueError('Chỉ được diff/carry-over giữa các version trong cùng phiên bản môn triển khai')
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

    def _concept_map(self, bank_version_id: str) -> dict[str, ConceptVersion]:
        return {row.concept_key: row for row in self.db.query(ConceptVersion).filter(ConceptVersion.bank_version_id == bank_version_id).all()}

    def _question_candidates_for_version(self, bank_version_id: str) -> list[Question]:
        return self.db.query(Question).filter(
            Question.bank_version_id == bank_version_id,
            Question.status.in_(['approved', 'published']),
            Question.is_retired.is_(False),
            Question.is_duplicate.is_(False),
        ).order_by(Question.difficulty.asc(), Question.question_family_id.asc().nullslast(), Question.variant_no.asc().nullslast(), Question.created_at.asc()).all()

    def preview_bank_version_diff(self, *, from_bank_version_id: str, to_bank_version_id: str, actor: str | None = None, persist: bool = True) -> dict:
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
            diff = BankVersionDiff(
                id=str(uuid.uuid4()),
                from_bank_version_id=source.id,
                to_bank_version_id=target.id,
                status='preview',
                material_similarity=material_similarity,
                summary_json=summary,
                created_by=actor,
                created_at=datetime.utcnow(),
            )
            self.db.add(diff)
            self.db.flush()
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
        if version.status in {'published', 'archived'}:
            raise ValueError(f'Bank Version đang ở trạng thái {version.status}; hãy tạo version mới nếu tài liệu thay đổi.')
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
        version = self._require_bank_version(bank_version_id)
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
            return {
                'ok': True,
                'reused_existing': True,
                'material_version': existing,
                'chunks_created': self.db.query(MaterialChunk).filter(MaterialChunk.material_version_id == existing.id).count(),
                'tokens_indexed': int(self.db.query(func.coalesce(func.sum(MaterialChunk.token_count), 0)).filter(MaterialChunk.material_version_id == existing.id).scalar() or 0),
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
            raise ValueError(f'File {filename} không tách được text. Nếu là scan/ảnh, cần bật OCR hoặc upload transcript.')

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
        version.metadata_json = {
            **(version.metadata_json or {}),
            'latest_material_upload_at': datetime.utcnow().isoformat(),
            'latest_material_id': material.id,
            'latest_material_filename': filename,
            'material_chunks_created': chunks_created,
            'material_tokens_indexed': tokens_indexed,
        }
        self.db.commit()
        self.db.refresh(material)
        return {
            'ok': True,
            'reused_existing': False,
            'material_version': material,
            'chunks_created': chunks_created,
            'tokens_indexed': tokens_indexed,
            'source_types': sorted(source_types),
            'message': 'Tải tài liệu và tách nội dung vào Bank Version thành công.',
        }

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
                f"[bank_chunk_id={row.id}; material_id={row.material_version_id}; source={row.source_ref}; page={row.page_number or ''}]\n{row.content}"
            )
        return '\n\n---\n\n'.join(parts), selected, total

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

    async def generate_from_bank_version(
        self,
        *,
        bank_version_id: str,
        question_count: int,
        difficulty_easy: int = 50,
        difficulty_medium: int = 30,
        difficulty_hard: int = 20,
        material_version_ids: list[str] | None = None,
        provider: str = 'openai',
        actor: str | None = None,
        approve_after_generate: bool = False,
    ) -> dict:
        version = self._require_bank_version(bank_version_id)
        subject = self.db.get(Subject, version.subject_id)
        chapter = self.db.get(SubjectChapter, version.chapter_id)
        if not subject or not chapter:
            raise ValueError('Bank Version thiếu Subject hoặc Chapter')
        if question_count < 1 or question_count > 200:
            raise ValueError('question_count phải trong khoảng 1-200')
        content, chunks, input_tokens = self._bank_generation_content(bank_version_id=version.id, material_version_ids=material_version_ids)
        if not content.strip() or not chunks:
            raise ValueError('Bank Version chưa có tài liệu/chunk. Hãy upload tài liệu trước khi generate.')
        counts = self._difficulty_counts(total_questions=question_count, easy=difficulty_easy, medium=difficulty_medium, hard=difficulty_hard)
        scope_title = f'{subject.code} · {chapter.title} · {version.version_code}'
        questions_created: list[Question] = []
        raw_usage_parts: list[dict] = []
        errors: list[dict] = []
        gateway = ModelGateway()
        checker = QualityChecker(self.db)
        chunk_ids = [row.id for row in chunks]
        first_material_id = chunks[0].material_version_id if chunks else None

        for difficulty, count in counts.items():
            if count <= 0:
                continue
            try:
                items, usage = await gateway.generate_questions(
                    content=content,
                    question_count=count,
                    scope_title=scope_title,
                    target_difficulty=difficulty,
                    provider=provider,
                    prompt_cache_key=f'bank:{version.id}:{difficulty}:{sha256_text(content, 24)}',
                )
                raw_usage_parts.append({'difficulty': difficulty, 'requested': count, 'usage': usage})
            except Exception as exc:
                errors.append({'difficulty': difficulty, 'error': f'{type(exc).__name__}: {str(exc) or repr(exc)}'})
                continue

            for index, raw_item in enumerate(items or []):
                item = dict(raw_item or {})
                item['difficulty'] = normalize_difficulty(item.get('difficulty') or difficulty)
                randomized = normalize_and_shuffle_options(item, index=index, force_shuffle=True)
                item['options'] = randomized.options
                item['correct_answer'] = randomized.correct_answer
                if not item.get('source_ref'):
                    item['source_ref'] = f'bank-version:{version.id}'
                if not item.get('source_type'):
                    item['source_type'] = 'bank_material'
                if not item.get('source_excerpt'):
                    item['source_excerpt'] = item.get('source_evidence') or ''
                quality = checker.check(item)
                status = 'approved' if (quality.passed and approve_after_generate) else ('pending_review' if quality.passed else 'draft_error')
                question_text = str(item.get('question') or item.get('question_text') or '').strip()
                if not question_text:
                    continue
                concept = self._get_or_create_concept_version(version=version, material_version_id=first_material_id, item=item, chunk_ids=chunk_ids)
                family = self._get_or_create_bank_family(version=version, concept=concept, difficulty=item['difficulty'], item=item)
                q_hash = question_fingerprint(
                    question_text,
                    course_id=f'bank:{version.id}',
                    source_node_id=family.family_key,
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
                    material_version_id=first_material_id,
                    concept_version_id=concept.id,
                    lesson_id=None,
                    lesson_title=scope_title,
                    block_id=f'bank-version:{version.id}',
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
                    source_ref=item.get('source_ref') or f'bank-version:{version.id}',
                    source_type=item.get('source_type') or 'bank_material',
                    source_page=item.get('source_page'),
                    source_timestamp_start=item.get('source_timestamp_start'),
                    source_timestamp_end=item.get('source_timestamp_end'),
                    source_chunk_id=None,
                    source_node_id=f'bank-version:{version.id}',
                    source_node_title=scope_title,
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
                questions_created.append(q)

        version.metadata_json = {
            **(version.metadata_json or {}),
            'last_bank_generate_at': datetime.utcnow().isoformat(),
            'last_bank_generate_requested_questions': question_count,
            'last_bank_generate_created_questions': len(questions_created),
            'last_bank_generate_input_tokens': input_tokens,
            'last_bank_generate_errors': errors,
        }
        self.db.commit()
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
            'questions': [q.id for q in questions_created],
            'usage': raw_usage_parts,
            'errors': errors,
            'message': 'Đã generate câu hỏi từ Bank Version. Câu hỏi cần review trước khi tạo Release.' if questions_created else 'Không tạo được câu hỏi mới.',
        }

    def release_library_key(self, *, subject: Subject, chapter: SubjectChapter, version: QuestionBankVersion) -> str:
        subject_slug = slugify(subject.code or subject.name, 'subject')
        chapter_slug = f'bai-{chapter.chapter_no}' if chapter.chapter_no else slugify(chapter.title, 'chapter')
        version_slug = slugify(version.version_code.replace('.', '-'), 'v1')
        return f'lib:FPT:{subject_slug}-{chapter_slug}-{version_slug}'

    def _release_questions_for_version(self, version: QuestionBankVersion) -> list[Question]:
        return self.db.query(Question).filter(
            Question.bank_version_id == version.id,
            Question.status.in_(['approved', 'published']),
        ).order_by(Question.difficulty.asc(), Question.question_family_id.asc().nullslast(), Question.created_at.asc()).all()

    def create_release(self, *, bank_version_id: str, release_code: str | None = None, title: str = '', include_approved_questions: bool = True, actor: str | None = None) -> QuestionBankRelease:
        version = self.db.get(QuestionBankVersion, bank_version_id)
        if not version:
            raise ValueError('Không tìm thấy Bank Version')
        subject = self.db.get(Subject, version.subject_id)
        chapter = self.db.get(SubjectChapter, version.chapter_id)
        if not subject or not chapter:
            raise ValueError('Bank Version thiếu Subject hoặc Chapter')
        code = release_code or f'{subject.code}-B{chapter.chapter_no}-{version.version_code}'
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
            title=title or f'{subject.code} - Bài {chapter.chapter_no} - {version.version_code}',
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
            metadata_json={'one_bank_release_one_openedx_library': True, 'shared_across_courses': True, 'publish_wiring': 'pending_openedx_import'},
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
        return release

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
                chapter_no_in_title = re.search(r'\b(?:bài|bai|chapter)\s*0*([0-9]+)\b', title.lower())
                if chapter_no_in_title and int(chapter_no_in_title.group(1)) != int(chapter.chapter_no):
                    checks.append(_check('chapter_number_match', 'fail', f'Node Open edX có vẻ là Bài {chapter_no_in_title.group(1)}, nhưng ngân hàng là Bài {chapter.chapter_no}.'))
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

    def create_quiz_blueprint(self, *, subject_id: str, chapter_id: str, title: str, total_questions: int, difficulty_easy: int, difficulty_medium: int, difficulty_hard: int, max_families_per_bank: int = 2, pick_count_per_slot: int = 1) -> QuizBlueprint:
        total_pct = difficulty_easy + difficulty_medium + difficulty_hard
        if total_pct != 100:
            raise ValueError('Tỷ lệ EASY/MEDIUM/HARD phải bằng 100')
        item = QuizBlueprint(id=str(uuid.uuid4()), subject_id=subject_id, chapter_id=chapter_id, subject_offering_id=None, title=title, total_questions=total_questions, difficulty_easy=difficulty_easy, difficulty_medium=difficulty_medium, difficulty_hard=difficulty_hard, max_families_per_bank=max_families_per_bank, pick_count_per_slot=pick_count_per_slot)
        self.db.add(item)
        self.db.commit()
        self.db.refresh(item)
        return item

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
        library_key = release.openedx_library_key or self.release_library_key(subject=subject, chapter=chapter, version=version)
        release.openedx_library_key = library_key
        release.status = 'publish_in_progress'
        release.metadata_json = {**(release.metadata_json or {}), 'publish_started_at': datetime.utcnow().isoformat(), 'publish_course_id_for_org': course_id}
        self.db.commit()

        metadata_base = {
            'library_key': library_key,
            'library_org': 'FPT',
            'org': 'FPT',
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
                f'chapter:Bài {chapter.chapter_no}',
                f'bank-release:{release.release_code}',
            ],
        }
        imported_now: list[dict] = []
        errors: list[dict] = []
        try:
            library_result = await connector.ensure_problem_library(
                course_id=course_id,
                chapter_node_id=f'bank-release:{release.id}',
                display_name=release.title or f'{subject.code} - Bài {chapter.chapter_no} - {version.version_code}',
                metadata=metadata_base,
            )
            if library_result.get('stub') is True or str(library_result.get('status', '')).startswith('local_stub'):
                raise RuntimeError('Open edX connector trả về stub khi ensure library. Không đánh dấu published.')
            for question in questions:
                item = existing_items[question.id]
                if item.openedx_library_problem_id and not force_reimport:
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
                if not question.openedx_library_problem_id:
                    question.openedx_library_problem_id = problem_id
                if not question.target_library_key:
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
            }
            version.status = 'published'
            version.published_at = release.published_at
            self.db.commit()
            self.db.refresh(release)
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
            raise RuntimeError(release.metadata_json['error']) from exc
