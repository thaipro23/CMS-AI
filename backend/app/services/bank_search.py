from __future__ import annotations

import re
import unicodedata
from datetime import datetime
from typing import Any

from sqlalchemy import and_, func, or_
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.question import Question, QuestionReviewLog
from app.models.question_bank import (
    Department,
    QuestionSearchDocument,
    Subject,
    SubjectChapter,
    SubjectOffering,
)
from app.services.business_rbac import BusinessRBACService


def normalize_search_text(value: str | None) -> str:
    text = unicodedata.normalize('NFD', value or '')
    text = ''.join(ch for ch in text if unicodedata.category(ch) != 'Mn')
    text = text.lower()
    text = re.sub(r'[^a-z0-9]+', ' ', text)
    return re.sub(r'\s+', ' ', text).strip()


def preview_text(value: str | None, max_length: int = 240) -> str:
    text = re.sub(r'\s+', ' ', (value or '').strip())
    if len(text) <= max_length:
        return text
    return text[: max_length - 1].rstrip() + '…'


class BankSearchService:
    """Bank-first global search engine.

    v25.9.15.6.35 moves search away from Python-wide table scans. Hierarchy
    entities use DB filters/trigram indexes; questions search via compact
    ai_question_search_documents instead of reading full ai_questions rows.
    """

    def __init__(self, db: Session):
        self.db = db

    def _limit(self, limit: int | None) -> int:
        max_limit = int(getattr(settings, 'bank_search_max_results', 50) or 50)
        return max(1, min(int(limit or 20), max(1, min(max_limit, 100))))

    def _tokens(self, query: str) -> list[str]:
        normalized = normalize_search_text(query)
        return [token for token in normalized.split(' ') if token]

    def _like_all_tokens(self, *columns):
        filters = []
        for token in self._current_tokens:
            pattern = f'%{token}%'
            filters.append(or_(*[func.lower(col).like(pattern) for col in columns]))
        return filters

    def _search_text_filters(self, column):
        return [column.like(f'%{token}%') for token in self._current_tokens]

    def _apply_department_scope(self, query, user: Any):
        return BusinessRBACService(self.db).apply_department_filter(query, user)

    def _apply_subject_scope(self, query, user: Any):
        return BusinessRBACService(self.db).apply_subject_filter(query, user)

    def _apply_offering_scope(self, query, user: Any):
        return BusinessRBACService(self.db).apply_subject_offering_filter(query, user)

    def _apply_chapter_scope(self, query, user: Any):
        return BusinessRBACService(self.db).apply_chapter_filter(query, user)

    def _apply_document_scope(self, query, user: Any):
        return BusinessRBACService(self.db).apply_hierarchy_filter(query, QuestionSearchDocument, user)

    def build_document_from_question(self, question: Question) -> QuestionSearchDocument:
        search_parts = [
            question.question_text,
            question.option_a,
            question.option_b,
            question.option_c,
            question.option_d,
            question.correct_answer,
            question.explanation,
            question.concept_title,
            question.concept_key,
            question.question_family_id,
            question.difficulty,
            question.status,
            question.topic,
            question.learning_objective,
            question.source_ref,
            question.source_excerpt,
            question.draft_error_reason,
        ]
        doc = self.db.get(QuestionSearchDocument, question.id)
        if not doc:
            doc = QuestionSearchDocument(question_id=question.id)
        doc.bank_version_id = question.bank_version_id
        doc.subject_id = question.subject_id
        doc.subject_offering_id = None
        if question.bank_version_id:
            # Avoid a relationship/migration; this read is cheap and keeps the
            # document scoped to the exact subject version for future filters.
            from app.models.question_bank import QuestionBankVersion
            version = self.db.get(QuestionBankVersion, question.bank_version_id)
            doc.subject_offering_id = version.subject_offering_id if version else None
        doc.chapter_id = question.subject_chapter_id
        doc.status = question.status or 'draft'
        doc.difficulty = question.difficulty or 'easy'
        doc.question_text_preview = preview_text(question.question_text, 500)
        doc.concept_title = question.concept_title
        doc.question_family_id = question.question_family_id
        doc.search_text = normalize_search_text(' '.join(str(part or '') for part in search_parts))
        doc.updated_at = datetime.utcnow()
        return doc

    def upsert_question(self, question_id: str, *, commit: bool = True) -> bool:
        question = self.db.get(Question, question_id)
        if not question:
            doc = self.db.get(QuestionSearchDocument, question_id)
            if doc:
                self.db.delete(doc)
                if commit:
                    self.db.commit()
            return False
        self.db.add(self.build_document_from_question(question))
        if commit:
            self.db.commit()
        return True

    def refresh_for_bank_version(self, bank_version_id: str, *, commit: bool = True) -> dict[str, int]:
        query = self.db.query(Question).filter(Question.bank_version_id == bank_version_id)
        count = 0
        for question in query.yield_per(500):
            self.db.add(self.build_document_from_question(question))
            count += 1
            if count % 1000 == 0:
                self.db.flush()
        if commit:
            self.db.commit()
        return {'updated': count}

    def refresh_for_chapter(self, chapter_id: str, *, commit: bool = True) -> dict[str, int]:
        query = self.db.query(Question).filter(Question.subject_chapter_id == chapter_id, Question.bank_version_id.isnot(None))
        count = 0
        for question in query.yield_per(500):
            self.db.add(self.build_document_from_question(question))
            count += 1
            if count % 1000 == 0:
                self.db.flush()
        if commit:
            self.db.commit()
        return {'updated': count}

    def rebuild(self, *, bank_version_id: str | None = None, chapter_id: str | None = None, commit: bool = True) -> dict[str, int | str | None]:
        query = self.db.query(Question).filter(Question.bank_version_id.isnot(None))
        if bank_version_id:
            query = query.filter(Question.bank_version_id == bank_version_id)
        if chapter_id:
            query = query.filter(Question.subject_chapter_id == chapter_id)
        seen: set[str] = set()
        count = 0
        for question in query.order_by(Question.created_at.asc(), Question.id.asc()).yield_per(500):
            self.db.add(self.build_document_from_question(question))
            seen.add(question.id)
            count += 1
            if count % 1000 == 0:
                self.db.flush()
        # Remove stale docs only for scoped rebuilds. Full rebuild can also purge
        # stale docs safely, but this keeps the SQL simple and explicit.
        stale_deleted = 0
        if bank_version_id or chapter_id:
            doc_query = self.db.query(QuestionSearchDocument)
            if bank_version_id:
                doc_query = doc_query.filter(QuestionSearchDocument.bank_version_id == bank_version_id)
            if chapter_id:
                doc_query = doc_query.filter(QuestionSearchDocument.chapter_id == chapter_id)
            for doc in doc_query.all():
                if doc.question_id not in seen:
                    self.db.delete(doc)
                    stale_deleted += 1
        if commit:
            self.db.commit()
        return {
            'updated': count,
            'stale_deleted': stale_deleted,
            'bank_version_id': bank_version_id,
            'chapter_id': chapter_id,
        }

    def health(self) -> dict[str, Any]:
        question_count = int(self.db.query(func.count(Question.id)).filter(Question.bank_version_id.isnot(None)).scalar() or 0)
        doc_count = int(self.db.query(func.count(QuestionSearchDocument.question_id)).scalar() or 0)
        missing_count = int(
            self.db.query(func.count(Question.id))
            .outerjoin(QuestionSearchDocument, QuestionSearchDocument.question_id == Question.id)
            .filter(Question.bank_version_id.isnot(None), QuestionSearchDocument.question_id.is_(None))
            .scalar() or 0
        )
        stale_count = int(
            self.db.query(func.count(QuestionSearchDocument.question_id))
            .outerjoin(Question, Question.id == QuestionSearchDocument.question_id)
            .filter(Question.id.is_(None))
            .scalar() or 0
        )
        latest_doc = self.db.query(func.max(QuestionSearchDocument.updated_at)).scalar()
        ok = missing_count == 0 and stale_count == 0
        return {
            'ok': ok,
            'question_count': question_count,
            'document_count': doc_count,
            'missing_or_unindexed_count': missing_count,
            'stale_document_count': stale_count,
            'latest_document_updated_at': latest_doc.isoformat() if latest_doc else None,
            'message': 'Search index sẵn sàng' if ok else 'Search index cần rebuild',
        }

    def _serialize_department(self, item: Department) -> dict[str, Any]:
        return {'type': 'department', 'id': item.id, 'title': f'{item.code} · {item.name}', 'subtitle': 'Bộ môn', 'href': f'/bank/departments/{item.id}/subjects'}

    def _serialize_subject(self, item: Subject, department: Department | None = None) -> dict[str, Any]:
        dep = f'{department.code} · ' if department else ''
        return {'type': 'subject', 'id': item.id, 'title': f'{item.code} · {item.name}', 'subtitle': f'{dep}Môn', 'href': f'/bank/subjects/{item.id}/versions'}

    def _serialize_offering(self, item: SubjectOffering, subject: Subject | None = None) -> dict[str, Any]:
        subj = f'{subject.code} · ' if subject else ''
        return {'type': 'subject_version', 'id': item.id, 'title': item.code, 'subtitle': f'{subj}{item.name or item.version_code or item.term or "Phiên bản môn"}', 'href': f'/bank/subject-versions/{item.id}/chapters'}

    def _serialize_chapter(self, item: SubjectChapter, subject: Subject | None = None, offering: SubjectOffering | None = None) -> dict[str, Any]:
        bits = [part for part in [subject.code if subject else None, offering.code if offering else None] if part]
        return {'type': 'chapter', 'id': item.id, 'title': item.title, 'subtitle': ' · '.join(bits) or 'Bài/Chapter', 'href': f'/bank/chapters/{item.id}'}

    def _serialize_question_doc(self, item: QuestionSearchDocument, question: Question | None = None, review_log: QuestionReviewLog | None = None) -> dict[str, Any]:
        reviewer = question.reviewed_by if question else None
        reviewed_at = question.reviewed_at.isoformat() if question and question.reviewed_at else None
        note = (review_log.note or '').strip() if review_log else ''
        reject_reason = note if (item.status == 'rejected' and note and not note.lower().startswith('bank review:')) else None
        subtitle_bits = [
            (item.difficulty or '').upper(),
            item.status or 'draft',
            item.concept_title or item.question_family_id or 'Câu hỏi',
        ]
        if reviewer:
            subtitle_bits.append(f'Người duyệt: {reviewer}')
        return {
            'type': 'question',
            'id': item.question_id,
            'title': item.question_text_preview or item.question_id,
            'subtitle': ' · '.join([str(x) for x in subtitle_bits if x]),
            'href': f'/bank/chapters/{item.chapter_id}?question_id={item.question_id}' if item.chapter_id else f'/bank/questions/{item.question_id}',
            'question_id': item.question_id,
            'bank_version_id': item.bank_version_id,
            'chapter_id': item.chapter_id,
            'status': item.status,
            'difficulty': item.difficulty,
            'reviewed_by': reviewer,
            'reviewer_name': reviewer,
            'reviewed_at': reviewed_at,
            'review_note': note or None,
            'reject_reason': reject_reason,
        }

    def drilldown_questions(
        self,
        *,
        user: Any,
        q: str = '',
        status: str | None = None,
        difficulty: str | None = None,
        question_type: str | None = None,
        created_from: str | None = None,
        created_to: str | None = None,
        question_id: str | None = None,
        chapter_id: str | None = None,
        subject_id: str | None = None,
        limit: int = 100,
    ) -> dict[str, Any]:
        """Scope-safe question drilldown used by actionable dashboard cards/charts.

        The dashboard sends users to /bank/search with filters such as status,
        difficulty, created date, or exact question id. This method reads the
        compact search-document table, joins ai_questions only for filters not
        stored in the search document, and always applies RBAC scope server-side.
        """
        safe_limit = max(1, min(int(limit or 100), 100))
        query_text = (q or '').strip()
        self._current_tokens = self._tokens(query_text)
        query = self.db.query(QuestionSearchDocument).outerjoin(Question, Question.id == QuestionSearchDocument.question_id)
        query = self._apply_document_scope(query, user)
        if query_text:
            query = query.filter(*self._search_text_filters(QuestionSearchDocument.search_text))
        if question_id:
            query = query.filter(QuestionSearchDocument.question_id == question_id)
        if chapter_id:
            query = query.filter(QuestionSearchDocument.chapter_id == chapter_id)
        if subject_id:
            query = query.filter(QuestionSearchDocument.subject_id == subject_id)
        if status and status not in {'all', '*'}:
            normalized_status = 'pending_review' if status == 'needs_review' else status
            if normalized_status == 'needs_action':
                query = query.filter(QuestionSearchDocument.status.in_(['pending_review', 'needs_review', 'draft_error']))
            else:
                query = query.filter(QuestionSearchDocument.status == normalized_status)
        if difficulty and difficulty not in {'all', '*'}:
            query = query.filter(func.lower(QuestionSearchDocument.difficulty) == str(difficulty).lower())
        if question_type and question_type not in {'all', '*'}:
            query = query.filter(func.coalesce(Question.question_type, 'unknown') == question_type)
        if created_from:
            try:
                query = query.filter(Question.created_at >= datetime.fromisoformat(created_from))
            except Exception:
                pass
        if created_to:
            try:
                end = datetime.fromisoformat(created_to)
                if len(created_to) <= 10:
                    end = end.replace(hour=23, minute=59, second=59)
                query = query.filter(Question.created_at <= end)
            except Exception:
                pass
        rows = query.order_by(QuestionSearchDocument.updated_at.desc(), QuestionSearchDocument.question_id.asc()).limit(safe_limit).all()
        question_ids = [item.question_id for item in rows]
        questions_by_id = {q.id: q for q in self.db.query(Question).filter(Question.id.in_(question_ids)).all()} if question_ids else {}
        review_logs: dict[str, QuestionReviewLog] = {}
        if question_ids:
            for log in self.db.query(QuestionReviewLog).filter(QuestionReviewLog.question_id.in_(question_ids)).order_by(QuestionReviewLog.created_at.desc()).all():
                review_logs.setdefault(log.question_id, log)
        items = [self._serialize_question_doc(item, questions_by_id.get(item.question_id), review_logs.get(item.question_id)) for item in rows]
        filters = {
            'q': query_text,
            'status': status,
            'difficulty': difficulty,
            'question_type': question_type,
            'created_from': created_from,
            'created_to': created_to,
            'question_id': question_id,
            'chapter_id': chapter_id,
            'subject_id': subject_id,
        }
        return {
            'entity': 'questions',
            'filters': {k: v for k, v in filters.items() if v not in (None, '')},
            'limit': safe_limit,
            'total': len(items),
            'items': items,
            'generated_at': datetime.utcnow().isoformat(),
        }

    def search_grouped(self, *, q: str, user: Any, limit: int = 20, include_questions: bool = True) -> dict[str, Any]:
        query_text = (q or '').strip()
        self._current_tokens = self._tokens(query_text)
        safe_limit = self._limit(limit)
        if not self._current_tokens:
            return {'q': query_text, 'limit': safe_limit, 'total': 0, 'items': [], 'groups': {'departments': [], 'subjects': [], 'subject_versions': [], 'chapters': [], 'questions': []}}

        departments_query = self.db.query(Department).filter(*self._like_all_tokens(Department.code, Department.name))
        departments_query = self._apply_department_scope(departments_query, user)
        departments = departments_query.order_by(Department.code.asc()).limit(safe_limit).all()

        subjects_query = self.db.query(Subject).filter(*self._like_all_tokens(Subject.code, Subject.name, Subject.description))
        subjects_query = self._apply_subject_scope(subjects_query, user)
        subjects = subjects_query.order_by(Subject.code.asc()).limit(safe_limit).all()
        dep_by_id = {d.id: d for d in self.db.query(Department).filter(Department.id.in_([s.department_id for s in subjects])).all()} if subjects else {}

        offerings_query = self.db.query(SubjectOffering).filter(*self._like_all_tokens(SubjectOffering.code, SubjectOffering.name, SubjectOffering.term))
        offerings_query = self._apply_offering_scope(offerings_query, user)
        offerings = offerings_query.order_by(SubjectOffering.code.asc()).limit(safe_limit).all()
        subj_by_id = {s.id: s for s in self.db.query(Subject).filter(Subject.id.in_([o.subject_id for o in offerings])).all()} if offerings else {}

        chapters_query = self.db.query(SubjectChapter).filter(*self._like_all_tokens(SubjectChapter.title, SubjectChapter.description))
        chapters_query = self._apply_chapter_scope(chapters_query, user)
        chapters = chapters_query.order_by(SubjectChapter.sort_order.asc(), SubjectChapter.title.asc()).limit(safe_limit).all()
        chapter_subjects = {s.id: s for s in self.db.query(Subject).filter(Subject.id.in_([c.subject_id for c in chapters])).all()} if chapters else {}
        chapter_offerings = {o.id: o for o in self.db.query(SubjectOffering).filter(SubjectOffering.id.in_([c.subject_offering_id for c in chapters if c.subject_offering_id])).all()} if chapters else {}

        questions: list[QuestionSearchDocument] = []
        if include_questions:
            question_query = self.db.query(QuestionSearchDocument).filter(*self._search_text_filters(QuestionSearchDocument.search_text))
            question_query = self._apply_document_scope(question_query, user)
            questions = question_query.order_by(QuestionSearchDocument.updated_at.desc(), QuestionSearchDocument.question_id.asc()).limit(safe_limit).all()

        groups = {
            'departments': [self._serialize_department(item) for item in departments],
            'subjects': [self._serialize_subject(item, dep_by_id.get(item.department_id)) for item in subjects],
            'subject_versions': [self._serialize_offering(item, subj_by_id.get(item.subject_id)) for item in offerings],
            'chapters': [self._serialize_chapter(item, chapter_subjects.get(item.subject_id), chapter_offerings.get(item.subject_offering_id or '')) for item in chapters],
            'questions': [self._serialize_question_doc(item) for item in questions],
        }
        items: list[dict[str, Any]] = []
        for key in ('departments', 'subjects', 'subject_versions', 'chapters', 'questions'):
            for item in groups[key]:
                if len(items) < safe_limit:
                    items.append(item)
        return {
            'q': query_text,
            'limit': safe_limit,
            'total': sum(len(v) for v in groups.values()),
            'items': items,
            'groups': groups,
        }
