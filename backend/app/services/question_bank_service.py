from __future__ import annotations

import hashlib
import json
import re
import uuid
import re
import unicodedata
from pathlib import Path
from datetime import datetime
from difflib import SequenceMatcher
from typing import Any

from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.course import CourseSyncState
from app.models.question import Question, QuestionReviewLog
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
    CourseQuizInstance,
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


def slugify(value: str, fallback: str = 'item') -> str:
    text = (value or '').strip().lower()
    text = re.sub(r'[^a-z0-9]+', '-', text)
    text = re.sub(r'-+', '-', text).strip('-')
    return text or fallback


def normalize_text(value: str | None) -> str:
    return re.sub(r'\s+', ' ', (value or '').strip().lower())


def normalize_code(value: str | None) -> str:
    return re.sub(r'[^a-z0-9]', '', (value or '').lower())




def normalize_title_match(value: str | None) -> str:
    text = unicodedata.normalize('NFD', value or '')
    text = ''.join(ch for ch in text if unicodedata.category(ch) != 'Mn')
    text = text.lower()
    text = re.sub(r'[^a-z0-9]+', ' ', text)
    text = re.sub(r'\s+', ' ', text).strip()
    return text


def extract_chapter_number(value: str | None) -> str | None:
    text = normalize_title_match(value)
    match = re.search(r'\b(?:bai|chapter|section)\s*([0-9]+(?:\.[0-9]+)*)\b', text)
    if match:
        return match.group(1)
    match = re.search(r'^([0-9]+(?:\.[0-9]+)*)\b', text)
    return match.group(1) if match else None

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

    def _chapter_stats_map(self) -> dict[str, dict]:
        chapters = self.db.query(SubjectChapter).all()
        bank_versions = self.db.query(QuestionBankVersion).all()
        releases = self.db.query(QuestionBankRelease).all()
        materials = self.db.query(LearningMaterialVersion).filter(LearningMaterialVersion.status != 'deleted').all()
        questions = self.db.query(Question).filter(Question.bank_version_id.isnot(None)).all()
        versions_by_chapter: dict[str, list[QuestionBankVersion]] = {}
        questions_by_chapter: dict[str, list[Question]] = {}
        releases_by_chapter: dict[str, list[QuestionBankRelease]] = {}
        materials_by_chapter: dict[str, list[LearningMaterialVersion]] = {}
        version_to_chapter = {v.id: v.chapter_id for v in bank_versions}
        for v in bank_versions:
            versions_by_chapter.setdefault(v.chapter_id, []).append(v)
        for q in questions:
            chapter_id = version_to_chapter.get(q.bank_version_id or '') or q.subject_chapter_id
            if chapter_id:
                questions_by_chapter.setdefault(chapter_id, []).append(q)
        for r in releases:
            chapter_id = version_to_chapter.get(r.bank_version_id or '') or r.chapter_id
            if chapter_id:
                releases_by_chapter.setdefault(chapter_id, []).append(r)
        for m in materials:
            materials_by_chapter.setdefault(m.chapter_id, []).append(m)
        out: dict[str, dict] = {}
        for chapter in chapters:
            qstats = self._bank_question_status_counts(questions_by_chapter.get(chapter.id, []))
            rels = releases_by_chapter.get(chapter.id, [])
            published = [r for r in rels if r.status == 'published']
            out[chapter.id] = {
                **qstats,
                'chapter_id': chapter.id,
                'subject_id': chapter.subject_id,
                'subject_offering_id': chapter.subject_offering_id,
                'title': chapter.title,
                'material_count': len(materials_by_chapter.get(chapter.id, [])),
                'bank_version_count': len(versions_by_chapter.get(chapter.id, [])),
                'release_count': len(rels),
                'published_release_count': len(published),
                'release_status': 'published' if published else ('ready_to_release' if qstats['is_review_done'] else ('has_release' if rels else 'none')),
                'ready_to_release': qstats['is_review_done'] and not published,
                'question_limit': 100,
                'remaining_quota': max(0, 100 - qstats['total_questions']),
            }
        return out

    def _offering_summary_map(self, chapter_stats: dict[str, dict] | None = None) -> dict[str, dict]:
        chapter_stats = chapter_stats or self._chapter_stats_map()
        offerings = self.db.query(SubjectOffering).all()
        chapters = self.db.query(SubjectChapter).all()
        out: dict[str, dict] = {}
        for offering in offerings:
            own_chapters = [c for c in chapters if c.subject_offering_id == offering.id]
            stats = [chapter_stats.get(c.id, {}) for c in own_chapters]
            chapter_count = len(own_chapters)
            done = len([s for s in stats if s.get('is_review_done')])
            unresolved = sum(int(s.get('unresolved_count') or 0) for s in stats)
            draft_error = sum(int(s.get('draft_error_count') or 0) for s in stats)
            total_questions = sum(int(s.get('total_questions') or 0) for s in stats)
            approved = sum(int(s.get('approved_count') or 0) for s in stats)
            pending = sum(int(s.get('pending_review_count') or 0) for s in stats)
            published_releases = sum(int(s.get('published_release_count') or 0) for s in stats)
            ready_to_release = sum(1 for s in stats if s.get('ready_to_release'))
            is_done = chapter_count > 0 and done == chapter_count
            out[offering.id] = {
                'subject_offering_id': offering.id,
                'subject_id': offering.subject_id,
                'code': offering.code,
                'name': offering.name,
                'chapter_count': chapter_count,
                'review_done_chapter_count': done,
                'review_not_done_chapter_count': max(0, chapter_count - done),
                'total_questions': total_questions,
                'approved_count': approved,
                'pending_review_count': pending,
                'draft_error_count': draft_error,
                'unresolved_count': unresolved,
                'published_release_count': published_releases,
                'ready_to_release_chapter_count': ready_to_release,
                'is_review_done': is_done,
                'status': 'ready' if is_done else ('needs_fix' if draft_error else ('needs_review' if unresolved else ('empty' if chapter_count == 0 else 'not_ready'))),
            }
        return out

    def _subject_summary_map(self, offering_stats: dict[str, dict] | None = None) -> dict[str, dict]:
        offering_stats = offering_stats or self._offering_summary_map()
        subjects = self.db.query(Subject).all()
        offerings = self.db.query(SubjectOffering).all()
        out: dict[str, dict] = {}
        for subject in subjects:
            own = [o for o in offerings if o.subject_id == subject.id]
            stats = [offering_stats.get(o.id, {}) for o in own]
            version_count = len(own)
            done = len([s for s in stats if s.get('is_review_done')])
            unresolved = sum(int(s.get('unresolved_count') or 0) for s in stats)
            draft_error = sum(int(s.get('draft_error_count') or 0) for s in stats)
            total_questions = sum(int(s.get('total_questions') or 0) for s in stats)
            approved = sum(int(s.get('approved_count') or 0) for s in stats)
            pending = sum(int(s.get('pending_review_count') or 0) for s in stats)
            ready_to_release = sum(int(s.get('ready_to_release_chapter_count') or 0) for s in stats)
            is_done = version_count > 0 and done == version_count
            out[subject.id] = {
                'subject_id': subject.id,
                'department_id': subject.department_id,
                'code': subject.code,
                'name': subject.name,
                'subject_version_count': version_count,
                'review_done_version_count': done,
                'review_not_done_version_count': max(0, version_count - done),
                'total_questions': total_questions,
                'approved_count': approved,
                'pending_review_count': pending,
                'draft_error_count': draft_error,
                'unresolved_count': unresolved,
                'ready_to_release_chapter_count': ready_to_release,
                'is_review_done': is_done,
                'status': 'ready' if is_done else ('needs_fix' if draft_error else ('needs_review' if unresolved else ('empty' if version_count == 0 else 'not_ready'))),
            }
        return out

    def _department_summary_map(self, subject_stats: dict[str, dict] | None = None) -> dict[str, dict]:
        subject_stats = subject_stats or self._subject_summary_map()
        departments = self.db.query(Department).all()
        subjects = self.db.query(Subject).all()
        out: dict[str, dict] = {}
        for department in departments:
            own = [s for s in subjects if s.department_id == department.id]
            stats = [subject_stats.get(s.id, {}) for s in own]
            subject_count = len(own)
            done = len([s for s in stats if s.get('is_review_done')])
            unresolved = sum(int(s.get('unresolved_count') or 0) for s in stats)
            draft_error = sum(int(s.get('draft_error_count') or 0) for s in stats)
            total_questions = sum(int(s.get('total_questions') or 0) for s in stats)
            approved = sum(int(s.get('approved_count') or 0) for s in stats)
            pending = sum(int(s.get('pending_review_count') or 0) for s in stats)
            ready_to_release = sum(int(s.get('ready_to_release_chapter_count') or 0) for s in stats)
            is_done = subject_count > 0 and done == subject_count
            out[department.id] = {
                'department_id': department.id,
                'code': department.code,
                'name': department.name,
                'subject_count': subject_count,
                'review_done_subject_count': done,
                'review_not_done_subject_count': max(0, subject_count - done),
                'total_questions': total_questions,
                'approved_count': approved,
                'pending_review_count': pending,
                'draft_error_count': draft_error,
                'unresolved_count': unresolved,
                'ready_to_release_chapter_count': ready_to_release,
                'is_review_done': is_done,
                'status': 'ready' if is_done else ('needs_fix' if draft_error else ('needs_review' if unresolved else ('empty' if subject_count == 0 else 'not_ready'))),
            }
        return out

    def dashboard_overview(self) -> dict:
        chapter_stats = self._chapter_stats_map()
        offering_stats = self._offering_summary_map(chapter_stats)
        subject_stats = self._subject_summary_map(offering_stats)
        department_stats = self._department_summary_map(subject_stats)
        chapters_needing_work = [s for s in chapter_stats.values() if int(s.get('unresolved_count') or 0) > 0]
        chapters_ready = [s for s in chapter_stats.values() if s.get('ready_to_release')]
        departments_with_work = len([s for s in department_stats.values() if int(s.get('unresolved_count') or 0) > 0])
        subjects_with_work = len([s for s in subject_stats.values() if int(s.get('unresolved_count') or 0) > 0])
        subject_versions_with_work = len([s for s in offering_stats.values() if int(s.get('unresolved_count') or 0) > 0])
        departments_total = len(department_stats)
        subjects_total = len(subject_stats)
        subject_versions_total = len(offering_stats)
        return {
            'ok': True,
            'departments_total': departments_total,
            'departments_done': max(0, departments_total - departments_with_work),
            'departments_not_done': departments_with_work,
            'subjects_total': subjects_total,
            'subjects_done': max(0, subjects_total - subjects_with_work),
            'subjects_not_done': subjects_with_work,
            'subject_versions_total': subject_versions_total,
            'subject_versions_done': max(0, subject_versions_total - subject_versions_with_work),
            'subject_versions_not_done': subject_versions_with_work,
            'chapters_total': len(chapter_stats),
            'chapters_needing_review': len(chapters_needing_work),
            'chapters_ready_to_release': len(chapters_ready),
            'total_questions': sum(int(s.get('total_questions') or 0) for s in chapter_stats.values()),
            'approved_count': sum(int(s.get('approved_count') or 0) for s in chapter_stats.values()),
            'pending_review_count': sum(int(s.get('pending_review_count') or 0) for s in chapter_stats.values()),
            'draft_error_count': sum(int(s.get('draft_error_count') or 0) for s in chapter_stats.values()),
            'next_actions': self._build_dashboard_next_actions(chapter_stats),
        }

    def _build_dashboard_next_actions(self, chapter_stats: dict[str, dict]) -> list[dict]:
        chapters = {c.id: c for c in self.db.query(SubjectChapter).all()}
        offerings = {o.id: o for o in self.db.query(SubjectOffering).all()}
        subjects = {s.id: s for s in self.db.query(Subject).all()}
        actions: list[dict] = []
        for stat in chapter_stats.values():
            chapter = chapters.get(stat.get('chapter_id'))
            if not chapter:
                continue
            offering = offerings.get(chapter.subject_offering_id or '')
            subject = subjects.get(chapter.subject_id)
            label = ' / '.join([x for x in [subject.code if subject else None, offering.code if offering else None, chapter.title] if x])
            if int(stat.get('draft_error_count') or 0) > 0:
                actions.append({'type': 'fix_errors', 'title': label, 'message': f"Còn {stat.get('draft_error_count')} câu lỗi cần sửa hoặc bỏ.", 'href': f"/bank/chapters/{chapter.id}", 'priority': 1})
            elif int(stat.get('pending_review_count') or 0) > 0:
                actions.append({'type': 'review_questions', 'title': label, 'message': f"Còn {stat.get('pending_review_count')} câu chưa duyệt.", 'href': f"/bank/chapters/{chapter.id}", 'priority': 2})
            elif stat.get('ready_to_release'):
                actions.append({'type': 'create_release', 'title': label, 'message': 'Đã duyệt xong, có thể chốt bộ đề.', 'href': f"/bank/chapters/{chapter.id}", 'priority': 3})
        return sorted(actions, key=lambda x: (x['priority'], x['title']))[:12]

    def department_summaries(self) -> list[dict]:
        stats = self._department_summary_map()
        departments = self.db.query(Department).order_by(Department.code.asc()).all()
        return [{'department': d, 'stats': stats.get(d.id, {})} for d in departments]

    def subject_summaries(self, *, department_id: str) -> list[dict]:
        stats = self._subject_summary_map()
        subjects = self.db.query(Subject).filter(Subject.department_id == department_id).order_by(Subject.code.asc()).all()
        return [{'subject': s, 'stats': stats.get(s.id, {})} for s in subjects]

    def subject_version_summaries(self, *, subject_id: str) -> list[dict]:
        stats = self._offering_summary_map()
        offerings = self.db.query(SubjectOffering).filter(SubjectOffering.subject_id == subject_id).order_by(SubjectOffering.code.asc()).all()
        return [{'subject_version': o, 'stats': stats.get(o.id, {})} for o in offerings]

    def chapter_summaries(self, *, subject_offering_id: str) -> list[dict]:
        stats = self._chapter_stats_map()
        chapters = self.db.query(SubjectChapter).filter(SubjectChapter.subject_offering_id == subject_offering_id).order_by(SubjectChapter.sort_order.asc(), SubjectChapter.chapter_no.asc()).all()
        return [{'chapter': c, 'stats': stats.get(c.id, {})} for c in chapters]

    def dashboard_search(self, *, q: str, limit: int = 20) -> list[dict]:
        query = normalize_text(q)
        if not query:
            return []
        chapter_stats = self._chapter_stats_map()
        offering_stats = self._offering_summary_map(chapter_stats)
        subject_stats = self._subject_summary_map(offering_stats)
        department_stats = self._department_summary_map(subject_stats)
        departments = {d.id: d for d in self.db.query(Department).all()}
        subjects = {s.id: s for s in self.db.query(Subject).all()}
        offerings = {o.id: o for o in self.db.query(SubjectOffering).all()}
        chapters = {c.id: c for c in self.db.query(SubjectChapter).all()}
        results: list[dict] = []
        def match(text: str) -> bool:
            norm = normalize_text(text)
            tokens = [t for t in query.split(' ') if t]
            return all(t in norm for t in tokens)
        for d in departments.values():
            if match(f"{d.code} {d.name}"):
                st = department_stats.get(d.id, {})
                results.append({'type': 'department', 'title': d.name, 'subtitle': f"{d.code} · {st.get('subject_count', 0)} môn · {st.get('unresolved_count', 0)} câu chưa xử lý", 'href': f"/bank/departments/{d.id}/subjects", 'stats': st})
        for s in subjects.values():
            if match(f"{s.code} {s.name} {departments.get(s.department_id).name if departments.get(s.department_id) else ''}"):
                st = subject_stats.get(s.id, {})
                results.append({'type': 'subject', 'title': f"{s.code} - {s.name}", 'subtitle': f"{st.get('subject_version_count', 0)} phiên bản · {st.get('unresolved_count', 0)} câu chưa xử lý", 'href': f"/bank/subjects/{s.id}/versions", 'stats': st})
        for o in offerings.values():
            subj = subjects.get(o.subject_id)
            if match(f"{o.code} {o.name} {o.term or ''} {subj.code if subj else ''} {subj.name if subj else ''}"):
                st = offering_stats.get(o.id, {})
                results.append({'type': 'subject_version', 'title': o.code, 'subtitle': f"{subj.code if subj else ''} · {st.get('chapter_count', 0)} bài · {st.get('unresolved_count', 0)} câu chưa xử lý", 'href': f"/bank/subject-versions/{o.id}/chapters", 'stats': st})
        for c in chapters.values():
            off = offerings.get(c.subject_offering_id or '')
            subj = subjects.get(c.subject_id)
            if match(f"{c.title} {off.code if off else ''} {subj.code if subj else ''} {subj.name if subj else ''}"):
                st = chapter_stats.get(c.id, {})
                results.append({'type': 'chapter', 'title': f"{subj.code if subj else ''} > {off.code if off else ''} > {c.title}", 'subtitle': f"{st.get('total_questions', 0)} câu | {st.get('approved_count', 0)} đã duyệt | {st.get('unresolved_count', 0)} chưa xử lý", 'href': f"/bank/chapters/{c.id}", 'stats': st})
        return results[:max(1, min(limit, 50))]

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
        return f'Không thể xóa {entity_label} vì bên trong chưa trống ({"; ".join(parts)}). Hãy xóa nội dung con trước.'

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
            item.term = term.strip().upper() or None
        if version_code is not None:
            item.version_code = version_code.strip().upper() or (item.term or item.version_code)
        if description is not None:
            meta = dict(item.metadata_json or {})
            meta['description'] = description or ''
            item.metadata_json = meta
        item.updated_at = datetime.utcnow()
        self.db.commit(); self.db.refresh(item)
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
        item.updated_at = datetime.utcnow()
        self.db.commit(); self.db.refresh(item)
        return item

    def delete_chapter(self, chapter_id: str) -> dict:
        item = self.db.get(SubjectChapter, chapter_id)
        if not item:
            raise ValueError('Không tìm thấy bài/chapter')
        msg = self._empty_block_message(entity_label='bài/chapter', counts={
            'bank_versions': self.db.query(QuestionBankVersion).filter(QuestionBankVersion.chapter_id == chapter_id).count(),
            'materials': self.db.query(LearningMaterialVersion).filter(LearningMaterialVersion.chapter_id == chapter_id).count(),
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
        return {'ok': True, 'deleted': True, 'entity_type': 'chapter', 'entity_id': chapter_id, 'message': 'Đã xóa bài/chapter'}

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

    def _require_mutable_bank_version(self, bank_version_id: str) -> QuestionBankVersion:
        # Alias rõ nghĩa dùng cho upload/xóa tài liệu. Giữ riêng tên này để các luồng UI
        # gọi xóa tài liệu không bị lỗi AttributeError khi service được refactor.
        return self._require_bank_version(bank_version_id)

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
        return {
            'ok': True,
            'reused_existing': False,
            'material_version': material,
            'chunks_created': chunks_created,
            'tokens_indexed': tokens_indexed,
            'source_types': sorted(source_types),
            'diff_required': diff_required,
            'diff_base_bank_version_id': version.based_on_version_id if diff_required else None,
            'document_change_state': version.metadata_json.get('document_change_state') if version.metadata_json else None,
            'message': 'Tải tài liệu và tách nội dung vào Bank Version thành công.' + (' Version này clone từ kỳ trước nên đã đánh dấu cần kiểm tra khác biệt tài liệu.' if diff_required else ''),
        }


    def delete_material_version(self, *, material_version_id: str, actor: str | None = None) -> dict:
        material = self.db.get(LearningMaterialVersion, material_version_id)
        if not material or material.status == 'deleted':
            raise ValueError('Không tìm thấy tài liệu')
        version = self._require_mutable_bank_version(material.bank_version_id)
        chunk_count = self.db.query(MaterialChunk).filter(MaterialChunk.material_version_id == material.id).count()
        detached = self.db.query(Question).filter(Question.material_version_id == material.id).update(
            {Question.material_version_id: None},
            synchronize_session=False,
        )
        self.db.query(MaterialChunk).filter(MaterialChunk.material_version_id == material.id).delete(synchronize_session=False)
        # Giữ audit nhẹ bằng trạng thái deleted thay vì xóa cứng record tài liệu.
        material.status = 'deleted'
        material.uploaded_by = actor or material.uploaded_by
        meta = dict(version.metadata_json or {})
        meta.update({
            'latest_material_delete_at': datetime.utcnow().isoformat(),
            'latest_material_deleted_id': material.id,
            'latest_material_deleted_file': material.file_name,
        })
        if version.based_on_version_id:
            meta.update({
                'document_change_state': 'changed_after_clone',
                'diff_required': True,
                'diff_base_bank_version_id': version.based_on_version_id,
                'diff_trigger': 'material_deleted_after_clone',
            })
        version.metadata_json = meta
        self.db.commit()
        return {
            'ok': True,
            'material_version_id': material.id,
            'bank_version_id': version.id,
            'chunks_deleted': int(chunk_count or 0),
            'detached_question_count': int(detached or 0),
            'message': 'Đã xóa tài liệu khỏi bài. Câu hỏi cũ được giữ lại để giáo viên quyết định duyệt/bỏ.',
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
                "Source: " + str(row.source_ref or f'bank-material:{row.material_version_id}') + "\n"
                + "Type: " + str(row.source_type or 'file') + "\n"
                + "ChunkId: " + str(row.id) + "\n"
                + "BlockId: " + str(row.material_version_id) + "\n"
                + (f"Page: {row.page_number}\n" if row.page_number else "")
                + str(row.content or '')
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
        subject = self.db.get(Subject, version.subject_id)
        chapter = self.db.get(SubjectChapter, version.chapter_id)
        if not subject or not chapter:
            raise ValueError('Bank Version thiếu Subject hoặc Chapter')
        if question_count < 1 or question_count > 100:
            raise ValueError('Số câu tạo thêm phải trong khoảng 1-100')
        if int(difficulty_easy or 0) + int(difficulty_medium or 0) + int(difficulty_hard or 0) != 100:
            raise ValueError('Tổng tỷ lệ EASY/MEDIUM/HARD phải bằng 100%')
        effective_target = min(100, int(target_question_count or 100))
        chapter_total = self._chapter_question_count(chapter_id=version.chapter_id)
        remaining = max(0, effective_target - chapter_total)
        if question_count > remaining:
            raise ValueError(f'Vượt chỉ tiêu của bài. Hiện có {chapter_total}/{effective_target} câu, chỉ còn được tạo thêm {remaining} câu.')
        content, chunks, content_tokens = self._bank_generation_content(bank_version_id=version.id, material_version_ids=material_version_ids)
        if not content.strip() or not chunks:
            raise ValueError('Bank Version chưa có tài liệu/chunk. Hãy upload tài liệu trước khi tạo câu hỏi.')
        counts = self._difficulty_counts(total_questions=question_count, easy=difficulty_easy, medium=difficulty_medium, hard=difficulty_hard)
        model_calls = len([value for value in counts.values() if int(value or 0) > 0]) or 1
        # Estimate nhanh, không gọi GPT thật. Input tính theo số lần gọi EASY/MEDIUM/HARD + schema/system overhead.
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
        subject = self.db.get(Subject, version.subject_id)
        chapter = self.db.get(SubjectChapter, version.chapter_id)
        if not subject or not chapter:
            raise ValueError('Bank Version thiếu Subject hoặc Chapter')
        if question_count < 1 or question_count > 100:
            raise ValueError('Số câu tạo thêm phải trong khoảng 1-100')
        if int(difficulty_easy or 0) + int(difficulty_medium or 0) + int(difficulty_hard or 0) != 100:
            raise ValueError('Tổng tỷ lệ EASY/MEDIUM/HARD phải bằng 100%')
        meta = dict(version.metadata_json or {})
        effective_target = min(100, int(target_question_count or meta.get('target_question_count') or 100))
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
                    prompt_cache_key='qbank:' + sha256_text(f'{version.id}:{difficulty}:{content}:{settings.openai_model}', 56),
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
                # Bank-first dùng MaterialChunk riêng, không phải ContentChunk của course-first.
                # Nếu model trả về source_chunk_id theo bank chunk thì không đưa field đó vào
                # QualityChecker course-first, tránh bị false draft_error invalid_source_chunk.
                bank_source_chunk_ids = split_source_chunk_ids(item.get('source_chunk_id') or item.get('bank_chunk_id'))
                if bank_source_chunk_ids and all(chunk_id in chunk_ids for chunk_id in bank_source_chunk_ids):
                    joined_chunk_ids = join_source_chunk_ids(bank_source_chunk_ids)
                    item['source_ref'] = item.get('source_ref') or f'bank-chunks:{joined_chunk_ids}'
                    item['source_chunk_id'] = None
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
                self.db.add(QuestionReviewLog(
                    id=str(uuid.uuid4()),
                    question_id=q.id,
                    old_status='generated',
                    new_status=status,
                    actor=actor or 'system',
                    note='Tạo câu hỏi từ tài liệu trong ngân hàng đề',
                ))
                questions_created.append(q)

        version.metadata_json = {
            **(version.metadata_json or {}),
            'last_bank_generate_at': datetime.utcnow().isoformat(),
            'last_bank_generate_requested_questions': question_count,
            'last_bank_generate_created_questions': len(questions_created),
            'last_bank_generate_input_tokens': input_tokens,
            'last_bank_generate_errors': errors,
            'last_bank_generate_by': actor,
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


    def _require_bank_question(self, question_id: str, bank_version_id: str | None = None) -> Question:
        question = self.db.get(Question, question_id)
        if not question or not question.bank_version_id:
            raise ValueError('Không tìm thấy câu hỏi trong ngân hàng đề')
        if bank_version_id and question.bank_version_id != bank_version_id:
            raise ValueError('Câu hỏi không thuộc Bank Version đang chọn')
        return question

    def update_bank_question(self, *, bank_version_id: str, question_id: str, payload, actor: str | None = None):
        version = self._require_bank_version(bank_version_id)
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
        return question

    def review_bank_question(self, *, bank_version_id: str, question_id: str, action: str = 'approve', note: str = '', actor: str | None = None) -> dict:
        version = self._require_bank_version(bank_version_id)
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
        return {
            'ok': True,
            'question': question,
            'old_status': old_status,
            'new_status': target_status,
            'message': 'Đã duyệt câu hỏi.' if target_status == 'approved' else ('Đã từ chối câu hỏi.' if target_status == 'rejected' else 'Đã đưa câu hỏi về trạng thái chờ duyệt.'),
        }

    def bulk_review_bank_questions(self, *, bank_version_id: str, action: str = 'approve', question_ids: list[str] | None = None, approve_all_pending: bool = False, note: str = '', actor: str | None = None) -> dict:
        version = self._require_bank_version(bank_version_id)
        action = (action or '').strip().lower()
        if action not in {'approve', 'reject', 'back_to_review'}:
            raise ValueError('Hành động duyệt không hợp lệ')
        query = self.db.query(Question).filter(Question.bank_version_id == version.id)
        if approve_all_pending:
            query = query.filter(Question.status.in_(['pending_review', 'needs_review']))
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
        return {
            'ok': True,
            'bank_version_id': version.id,
            'diff_required': False,
            'document_change_state': 'diff_resolved',
            'message': 'Đã đánh dấu tài liệu đã được kiểm tra. Có thể chốt Release nếu câu hỏi đã duyệt đủ.',
        }

    def release_readiness(self, *, bank_version_id: str) -> dict:
        version = self._require_bank_version(bank_version_id)
        meta = version.metadata_json or {}
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
                'chapter_question_limit': 100,
                'chapter_total_count': self._chapter_question_count(chapter_id=version.chapter_id),
                'chapter_remaining_quota': max(0, 100 - self._chapter_question_count(chapter_id=version.chapter_id)),
                'difficulty_counts': {
                    'easy': len([q for q in approved if (q.difficulty or '').lower() == 'easy']),
                    'medium': len([q for q in approved if (q.difficulty or '').lower() == 'medium']),
                    'hard': len([q for q in approved if (q.difficulty or '').lower() == 'hard']),
                },
            },
            'recommended_actions': actions,
            'message': 'Đủ điều kiện chốt bộ đề.' if can_create else 'Chưa thể chốt bộ đề. Phải duyệt hoặc bỏ hết tất cả câu hỏi trước.',
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
        }

    def _release_offering_term_slug(self, *, subject: Subject, version: QuestionBankVersion) -> str | None:
        """Return the subject offering/term part used in Open edX Library keys.

        FPT rule: library keys for question-bank releases must include the
        subject version/term. Example:
            WEB107_FA26 / Bài 2.1 / v1.0
            -> lib:FPT:web107-FA26-b-i-2-1-v1-0

        Older builds produced keys without the term, for example:
            lib:FPT:web107-b-i-2-1-v1-0
        """
        offering = self.db.get(SubjectOffering, version.subject_offering_id) if version.subject_offering_id else None
        if not offering:
            return None

        raw_term = (offering.term or '').strip()
        if not raw_term:
            offering_code = (offering.code or '').strip()
            subject_code = (subject.code or '').strip()
            if offering_code and subject_code and offering_code.upper().startswith(subject_code.upper()):
                raw_term = offering_code[len(subject_code):].strip(' _-')
            else:
                raw_term = offering_code

        if not raw_term:
            return None

        # Keep FPT term readable in the key: FA26/SU25/SP25, not fa26/su25.
        term = re.sub(r'[^A-Za-z0-9]+', '-', raw_term).strip('-').upper()
        return term or None

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

    def _release_questions_for_version(self, version: QuestionBankVersion) -> list[Question]:
        return self.db.query(Question).filter(
            Question.bank_version_id == version.id,
            Question.status.in_(['approved', 'published']),
        ).order_by(Question.difficulty.asc(), Question.question_family_id.asc().nullslast(), Question.created_at.asc()).all()

    def create_release(self, *, bank_version_id: str, release_code: str | None = None, title: str = '', include_approved_questions: bool = True, actor: str | None = None, force: bool = False) -> QuestionBankRelease:
        version = self.db.get(QuestionBankVersion, bank_version_id)
        if not version:
            raise ValueError('Không tìm thấy Bank Version')
        subject = self.db.get(Subject, version.subject_id)
        chapter = self.db.get(SubjectChapter, version.chapter_id)
        if not subject or not chapter:
            raise ValueError('Bank Version thiếu Subject hoặc Chapter')
        readiness = self.release_readiness(bank_version_id=version.id)
        if not force and not readiness.get('can_create_release'):
            raise ValueError('Chưa thể chốt Release: ' + readiness.get('message', 'Cần xử lý xong câu hỏi/tài liệu trước khi chốt.'))
        chapter_code = slugify(self._chapter_display_name(chapter), 'chapter')
        code = release_code or f'{subject.code}-{chapter_code}-{version.version_code}'
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
            title=title or f'{subject.code} - {self._chapter_display_name(chapter)} - {version.version_code}',
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
            'disabled_reason': None if item.get('all_ready') else (
                'Chưa publish Release đủ tất cả bài' if item.get('chapter_count') else 'Version môn chưa có bài'
            ),
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
        candidates.sort(key=lambda item: (item['all_ready'], item['course_run_match'], item['score']), reverse=True)
        selected = None
        explicit_selection = bool(selected_subject_offering_id)
        if selected_subject_offering_id:
            selected_item = next((item for item in candidates if item.get('offering_id') == selected_subject_offering_id), None)
            if not selected_item:
                warnings.append('Version môn được chọn không thuộc môn trong Course ID.')
            elif not selected_item.get('all_ready'):
                warnings.append('Version môn được chọn chưa có Release published đủ tất cả bài nên chưa thể tạo Quiz.')
            else:
                selected = selected_item['offering']
        if not selected and not explicit_selection:
            for item in candidates:
                if item['all_ready'] and (item['course_run_match'] or not selected):
                    selected = item['offering']
                    break
        if not selected and candidates:
            warnings.append('Không có phiên bản môn nào có Release published đủ tất cả bài.')
        return selected, candidates, warnings

    async def preview_quiz_auto_map(self, *, openedx_course_id: str, selected_subject_offering_id: str | None = None) -> dict:
        course_id = (openedx_course_id or '').strip()
        parsed = parse_openedx_course_id(course_id)
        blocking_errors: list[str] = []
        warnings: list[str] = []
        if not parsed.get('ok'):
            return {'ok': False, 'openedx_course_id': course_id, 'mode': 'preview', 'subject': None, 'offering': None, 'course_mapping': None, 'summary': {}, 'sections': [], 'mappings': [], 'warnings': [], 'blocking_errors': ['Course ID phải có dạng course-v1:ORG+COURSE+RUN.'], 'can_apply': False, 'message': 'Course ID không hợp lệ.'}
        subject = self.db.query(Subject).filter(func.lower(Subject.code) == str(parsed.get('course_code')).lower()).first()
        if not subject:
            # Case-insensitive + punctuation-insensitive fallback.
            all_subjects = self.db.query(Subject).all()
            subject = next((item for item in all_subjects if normalize_code(item.code) == normalize_code(parsed.get('course_code'))), None)
        if not subject:
            return {'ok': False, 'openedx_course_id': course_id, 'mode': 'preview', 'subject': None, 'offering': None, 'course_mapping': None, 'summary': {'course_code': parsed.get('course_code'), 'course_run': parsed.get('run')}, 'sections': [], 'mappings': [], 'warnings': [], 'blocking_errors': [f'Không tìm thấy môn có mã {parsed.get("course_code")}.'], 'can_apply': False, 'message': 'Không tìm thấy môn phù hợp với Course ID.'}
        department = self.db.get(Department, subject.department_id) if subject.department_id else None
        offering, candidates, candidate_warnings = self._select_offering_for_course(course_id=course_id, subject=subject, selected_subject_offering_id=selected_subject_offering_id)
        warnings.extend(candidate_warnings)
        if not offering:
            blocking_errors.append('Chưa có phiên bản môn phù hợp có Release published đủ tất cả các bài. Hãy chốt/publish Release cho toàn bộ bài trước khi tạo Quiz.')
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
                'message': 'Chưa đủ Release published để tự map course.',
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
            section, score, reason = self._match_chapter_to_section(chapter, sections, used_sections)
            if section:
                used_sections.add(str(section.get('block_id') or ''))
            release_info = release_by_chapter.get(chapter.id) or {}
            ready = bool(section and release_info.get('ready'))
            if not section:
                blocking_errors.append(f'{self._chapter_display_name(chapter)} chưa tìm thấy Section cùng tên trong course.')
            if not release_info.get('ready'):
                blocking_errors.append(f'{self._chapter_display_name(chapter)} chưa có Release published đủ component.')
            mappings.append({
                'chapter_id': chapter.id,
                'chapter_title': self._chapter_display_name(chapter),
                'release_id': release_info.get('release_id'),
                'release_code': release_info.get('release_code'),
                'openedx_library_key': release_info.get('openedx_library_key'),
                'openedx_section_id': section.get('block_id') if section else None,
                'openedx_section_title': section.get('display_name') if section else None,
                'match_score': round(float(score or 0), 4),
                'match_reason': reason,
                'ready': ready,
                'course_chapter_mapping_id': None,
            })
        existing = self.db.query(EdxCourseMapping).filter(EdxCourseMapping.openedx_course_id == course_id).first()
        if existing and existing.subject_id != subject.id:
            blocking_errors.append('Course này đã được map sang môn khác. Không tự ghi đè để tránh gắn nhầm đề.')
        can_apply = not blocking_errors and bool(mappings)
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
            'message': 'Đã tự tìm được version môn và Section phù hợp. Có thể lưu mapping.' if can_apply else 'Chưa thể tự map. Hãy xử lý các lỗi bên dưới.',
        }

    async def apply_quiz_auto_map(self, *, openedx_course_id: str, selected_subject_offering_id: str | None = None, actor: str | None = None) -> dict:
        preview = await self.preview_quiz_auto_map(openedx_course_id=openedx_course_id, selected_subject_offering_id=selected_subject_offering_id)
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
        return {
            **preview,
            'ok': True,
            'mode': 'applied',
            'course_mapping': {'id': mapping.id, 'openedx_course_id': mapping.openedx_course_id, 'status': mapping.status},
            'mappings': saved_mappings,
            'can_apply': True,
            'message': f'Đã tự map {len(saved_mappings)} Section Open edX vào {len(saved_mappings)} bài của {offering.get("code")}.',
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

        # Group by difficulty + family. A family is never split across slots.
        grouped: dict[str, dict[str, list[BankReleaseQuestion]]] = {'easy': {}, 'medium': {}, 'hard': {}}
        for row in rows:
            question = questions[row.question_id]
            diff = normalize_difficulty(row.difficulty or question.difficulty)
            family_id = str(row.question_family_id or question.question_family_id or f'family-{question.id}').strip()
            grouped.setdefault(diff, {}).setdefault(family_id, []).append(row)

        requested = self._target_counts_for_quiz(total_questions, difficulty_easy, difficulty_medium, difficulty_hard)
        available = {diff: len(grouped.get(diff, {})) for diff in ('easy', 'medium', 'hard')}
        effective = {diff: min(requested[diff], available[diff]) for diff in ('easy', 'medium', 'hard')}
        nonempty = [diff for diff, count in available.items() if count]
        for diff in nonempty:
            if effective[diff] == 0:
                effective[diff] = 1
        desired_total = min(max(sum(requested.values()), len(nonempty)), sum(available.values()))
        while sum(effective.values()) < desired_total:
            candidates = [diff for diff in ('easy', 'medium', 'hard') if effective[diff] < available[diff]]
            if not candidates:
                break
            chosen = max(candidates, key=lambda diff: (available[diff] - effective[diff], requested[diff] - effective[diff]))
            effective[chosen] += 1
        while sum(effective.values()) > desired_total:
            candidates = [diff for diff in ('easy', 'medium', 'hard') if effective[diff] > 1]
            if not candidates:
                break
            chosen = max(candidates, key=lambda diff: effective[diff] - requested[diff])
            effective[chosen] -= 1

        slots: list[dict] = []
        coverage: list[dict] = []
        slot_no = 1
        assigned_question_ids: set[str] = set()
        assigned_components: set[str] = set()
        warnings: list[str] = []
        max_families = max(1, int(max_families_per_bank or 2))
        for diff in ('easy', 'medium', 'hard'):
            families = list(grouped.get(diff, {}).items())
            families.sort(key=lambda item: (-len(item[1]), item[0]))
            target_slots = effective[diff]
            if not families:
                coverage.append({'difficulty': diff.upper(), 'target_slots': requested[diff], 'selected_slots': 0, 'available_families': 0, 'status': 'no_questions'})
                continue
            buckets = [[] for _ in range(max(target_slots, 1))]
            loads = [0 for _ in buckets]
            family_counts = [0 for _ in buckets]
            for family_id, family_rows in families:
                # Prefer buckets with fewer families first, then fewer variants.
                candidates = [idx for idx in range(len(buckets)) if family_counts[idx] < max_families]
                if not candidates:
                    candidates = list(range(len(buckets)))
                    warnings.append(f'{diff.upper()} có nhiều family hơn giới hạn {max_families} family/slot; một số slot sẽ chứa nhiều family hơn để không bỏ câu.')
                idx = min(candidates, key=lambda i: (loads[i], family_counts[i], i))
                buckets[idx].append((family_id, family_rows))
                loads[idx] += len(family_rows)
                family_counts[idx] += 1
            for bucket in buckets:
                if not bucket:
                    continue
                slot_question_ids: list[str] = []
                problem_ids: list[str] = []
                family_payloads: list[dict] = []
                for family_id, family_rows in bucket:
                    qids: list[str] = []
                    for row in family_rows:
                        question = questions[row.question_id]
                        component = str(row.openedx_library_problem_id or '').strip().strip('"\'')
                        if question.id in assigned_question_ids:
                            raise ValueError(f'Câu hỏi {question.id} bị đưa vào nhiều slot; hệ thống từ chối tạo quiz.')
                        if component in assigned_components:
                            raise ValueError(f'Open edX component {component} bị đưa vào nhiều slot; hệ thống từ chối tạo quiz.')
                        assigned_question_ids.add(question.id)
                        assigned_components.add(component)
                        slot_question_ids.append(question.id)
                        problem_ids.append(component)
                        qids.append(question.id)
                    sample_question = questions[family_rows[0].question_id]
                    family_payloads.append({
                        'family_id': family_id,
                        'family_name': sample_question.concept_title or sample_question.topic or family_id,
                        'concept_id': sample_question.concept_id,
                        'concept_title': sample_question.concept_title,
                        'variant_count': len(qids),
                        'question_ids': qids,
                    })
                slots.append({
                    'slot_no': slot_no,
                    'difficulty': diff.upper(),
                    'pick_count': 1,
                    'library_key': release.openedx_library_key,
                    'openedx_problem_ids': problem_ids,
                    'question_ids': slot_question_ids,
                    'families': family_payloads,
                    'family_names': [item['family_name'] for item in family_payloads],
                    'variant_count': len(slot_question_ids),
                    'rule': f'random 1/{max(len(slot_question_ids), 1)} variants',
                    'warning': '',
                })
                slot_no += 1
            coverage.append({'difficulty': diff.upper(), 'target_slots': requested[diff], 'selected_slots': len([s for s in slots if s['difficulty'] == diff.upper()]), 'available_families': len(families), 'status': 'ok'})
        if not slots:
            raise ValueError('Release không đủ câu hỏi/component để tạo bất kỳ Problem Bank slot nào.')
        if len(slots) != int(total_questions):
            warnings.append(f'Yêu cầu {total_questions} slot, thực tế tạo {len(slots)} slot vì không lặp/tách family.')
        plan = {
            'ok': True,
            'planner_engine': 'bank_release_deterministic_v1',
            'uses_llm': False,
            'release_id': release.id,
            'release_code': release.release_code,
            'openedx_library_key': release.openedx_library_key,
            'requested_total_questions': int(total_questions),
            'total_questions': len(slots),
            'target_counts': {k.upper(): v for k, v in requested.items()},
            'effective_target_counts': {k.upper(): effective[k] for k in effective},
            'coverage': coverage,
            'slots': slots,
            'warnings': list(dict.fromkeys(warnings)),
            'assigned_question_count': len(assigned_question_ids),
            'assigned_component_count': len(assigned_components),
            'hard_guard': {'valid': True, 'summary': 'Release plan hợp lệ: không trùng question_id hoặc Open edX component giữa các slot'},
            'message': f'Tạo kế hoạch từ Bank Release {release.release_code}: {len(slots)} Problem Bank slot, {len(assigned_components)} component.',
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
        # FPT convention: if the source Section/Chapter is "Bài 1" then the created
        # Subsection is "Quiz 1" and the Unit is always "Quiz". Keep this as a
        # backend rule so old frontends or API callers cannot accidentally create
        # "AI Learning Check" / "Quiz tự luyện" names anymore.
        quiz_suffix = self._chapter_quiz_suffix(chapter)
        final_quiz_title = f'Quiz {quiz_suffix}'.strip()
        final_unit_title = 'Quiz'
        timer_config = {
            'custom_timer_enabled': bool(custom_timer_enabled),
            'time_limit_minutes': int(time_limit_minutes or 15),
            'duration_seconds': int(time_limit_minutes or 15) * 60,
            'retake_cooldown_minutes': int(retake_cooldown_minutes or 0),
            'cooldown_seconds': int(retake_cooldown_minutes or 0) * 60,
            'auto_submit_on_timeout': bool(auto_submit_on_timeout),
            'lock_after_timeout': bool(lock_after_timeout),
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
            metadata_json={'plan': plan, 'validation': validation, 'actor': actor, 'created_from': 'bank_release', 'timer_config': timer_config},
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
                    'grade_as': 'Quiz',
                    'format': 'Quiz',
                    'graded': True,
                },
            )
            if quiz_result.get('ok') is not True:
                raise RuntimeError(f'Open edX không tạo Quiz node thành công: {quiz_result}')
            unit_node_id = quiz_result.get('leaf_unit_node_id') or quiz_result.get('unit_node_id')
            if not unit_node_id:
                raise RuntimeError('Open edX không trả leaf_unit_node_id sau khi tạo Quiz')
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
                'quiz_result': quiz_result,
                'problem_bank_result': insert_result,
                'timer_config': {
                    **timer_config,
                    'course_id': course_id,
                    'unit_usage_key': unit_node_id,
                    'sequence_usage_key': (quiz_result.get('created_nodes') or [{}])[-2].get('usage_key') if isinstance(quiz_result.get('created_nodes'), list) and len(quiz_result.get('created_nodes')) >= 2 else None,
                    'unit_reset_plugin_result': quiz_result.get('timer_config_result'),
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
                'message': 'Đã tạo Quiz và native Problem Bank từ Bank Release trên Open edX.',
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
        expected_library_key = self.release_library_key(subject=subject, chapter=chapter, version=version)
        previous_library_key = release.openedx_library_key
        if not release.openedx_library_key or self._release_library_key_needs_term_upgrade(library_key=release.openedx_library_key, subject=subject, version=version):
            release.openedx_library_key = expected_library_key
        library_key = release.openedx_library_key
        library_key_changed = bool(previous_library_key and previous_library_key != library_key)
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
