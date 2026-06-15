from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from sqlalchemy import and_, case, distinct, func
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.cost import BudgetPolicy
from app.models.question import Question
from app.models.question_bank import (
    BankChapterStats,
    Department,
    LearningMaterialVersion,
    QuestionBankRelease,
    QuestionBankVersion,
    Subject,
    SubjectChapter,
    SubjectOffering,
)


BANK_PENDING_STATUSES = {'pending_review', 'needs_review'}
BANK_ERROR_STATUSES = {'draft_error'}
BANK_APPROVED_STATUSES = {'approved', 'published'}
DIFFICULTY_EASY = {'easy', 'EASY'}
DIFFICULTY_MEDIUM = {'medium', 'MEDIUM'}
DIFFICULTY_HARD = {'hard', 'HARD'}


class BankDashboardStatsService:
    """Summary engine for Bank Dashboard.

    v25.9.15.6.34 rule: request-time dashboard code must not aggregate the
    1.5M-row ai_questions table. Only rebuild/refresh paths in this service may
    scan ai_questions; UI reads ai_bank_chapter_stats plus small hierarchy tables.
    """

    def __init__(self, db: Session):
        self.db = db

    def _redis_client(self):
        try:
            import redis

            return redis.Redis.from_url(settings.redis_url, decode_responses=True)
        except Exception:
            return None

    def invalidate_cache(self) -> None:
        client = self._redis_client()
        if not client:
            return
        try:
            for pattern in (
                'bank_dashboard_overview:v1',
                'bank_department_summary:v1',
                'bank_subject_summary:*',
                'bank_offering_summary:*',
                'bank_chapter_summary:*',
            ):
                keys = list(client.scan_iter(match=pattern, count=100))
                if keys:
                    client.delete(*keys)
        except Exception:
            # Cache must never break the dashboard.
            return

    def _cache_get(self, key: str) -> Any | None:
        client = self._redis_client()
        if not client:
            return None
        try:
            raw = client.get(key)
            return json.loads(raw) if raw else None
        except Exception:
            return None

    def _cache_set(self, key: str, value: Any, ttl_seconds: int | None = None) -> None:
        client = self._redis_client()
        if not client:
            return
        ttl = ttl_seconds if ttl_seconds is not None else int(getattr(settings, 'bank_dashboard_cache_ttl_seconds', 45) or 45)
        try:
            client.setex(key, max(5, min(ttl, 300)), json.dumps(value, ensure_ascii=False, default=str))
        except Exception:
            return

    def chapter_question_limit_default(self) -> int:
        policy = self.db.query(BudgetPolicy).filter(
            BudgetPolicy.scope == 'chapter',
            BudgetPolicy.scope_id == 'default',
            BudgetPolicy.is_active == True,  # noqa: E712
        ).first()
        if not policy:
            policy = self.db.query(BudgetPolicy).filter(
                BudgetPolicy.scope == 'course',
                BudgetPolicy.scope_id.in_(['__bank_chapter_default__', 'default']),
                BudgetPolicy.is_active == True,  # noqa: E712
            ).first()
        if policy:
            return max(1, int(policy.max_questions_per_course or 100))
        return 100

    def ensure_chapter_stats(self, chapter_ids: list[str] | tuple[str, ...], *, max_rebuild: int = 500) -> dict[str, Any]:
        """Auto-heal missing summary rows for the currently viewed Bank scope.

        This keeps UI cards accurate after upgrading from pre-summary versions or
        after old data imports. It is bounded so a production system with a large
        missing stats set will not accidentally rebuild 15k chapters from a page
        load; admins can still run /admin/stats/rebuild for full repair.
        """
        unique_ids = sorted({str(cid) for cid in chapter_ids if cid})
        if not unique_ids:
            return {'ok': True, 'checked_count': 0, 'rebuilt_count': 0, 'skipped': False}
        existing = {
            row.chapter_id: row
            for row in self.db.query(BankChapterStats).filter(BankChapterStats.chapter_id.in_(unique_ids)).all()
        }
        missing_or_stale = [cid for cid in unique_ids if cid not in existing or existing[cid].updated_at is None]
        if not missing_or_stale:
            return {'ok': True, 'checked_count': len(unique_ids), 'rebuilt_count': 0, 'skipped': False}
        if len(missing_or_stale) > max_rebuild:
            return {
                'ok': False,
                'checked_count': len(unique_ids),
                'rebuilt_count': 0,
                'missing_or_stale_count': len(missing_or_stale),
                'skipped': True,
                'message': 'Scope có quá nhiều stats thiếu/stale; hãy chạy admin stats rebuild.',
            }
        rebuilt = 0
        for cid in missing_or_stale:
            self.rebuild_chapter_stats(chapter_id=cid, commit=False)
            rebuilt += 1
        self.db.commit()
        self.invalidate_cache()
        return {'ok': True, 'checked_count': len(unique_ids), 'rebuilt_count': rebuilt, 'skipped': False}

    def _zero_stat(self, chapter: SubjectChapter, *, question_limit: int) -> dict[str, Any]:
        return {
            'chapter_id': chapter.id,
            'subject_id': chapter.subject_id,
            'subject_offering_id': chapter.subject_offering_id,
            'latest_bank_version_id': None,
            'title': chapter.title,
            'total_questions': 0,
            'approved_count': 0,
            'pending_review_count': 0,
            'draft_error_count': 0,
            'rejected_count': 0,
            'retired_count': 0,
            'duplicate_count': 0,
            'easy_count': 0,
            'medium_count': 0,
            'hard_count': 0,
            'family_count': 0,
            'material_count': 0,
            'bank_version_count': 0,
            'release_count': 0,
            'published_release_count': 0,
            'release_status': 'none',
            'is_published': False,
            'published_chapter_count': 0,
            'ready_to_release': False,
            'unresolved_count': 0,
            'is_review_done': False,
            'has_questions': False,
            'status': 'empty',
            'question_limit': question_limit,
            'remaining_quota': question_limit,
            'updated_at': None,
        }

    def _serialize_chapter_stat(self, chapter: SubjectChapter, stat: BankChapterStats | None, *, question_limit: int, bank_version_count: int = 0) -> dict[str, Any]:
        if not stat:
            return self._zero_stat(chapter, question_limit=question_limit)
        total = int(stat.total_questions or 0)
        unresolved = int(stat.unresolved_count or 0)
        draft_error = int(stat.draft_error_count or 0)
        pending = int(stat.pending_review_count or 0)
        approved = int(stat.approved_count or 0)
        published = int(stat.published_release_count or 0)
        release_status = 'published' if published else ('ready_to_release' if bool(stat.ready_to_release) else ('has_release' if int(stat.release_count or 0) else 'none'))
        is_published = published > 0
        is_done = bool((approved and not unresolved and total > 0) or is_published)
        status = 'published' if is_published else ('ready' if is_done else ('needs_fix' if draft_error else ('needs_review' if pending else ('empty' if not total else 'not_ready'))))
        return {
            'chapter_id': chapter.id,
            'subject_id': chapter.subject_id,
            'subject_offering_id': chapter.subject_offering_id,
            'latest_bank_version_id': stat.latest_bank_version_id,
            'title': chapter.title,
            'total_questions': total,
            'approved_count': approved,
            'pending_review_count': pending,
            'draft_error_count': draft_error,
            'rejected_count': int(stat.rejected_count or 0),
            'retired_count': int(stat.retired_count or 0),
            'duplicate_count': int(stat.duplicate_count or 0),
            'easy_count': int(stat.easy_count or 0),
            'medium_count': int(stat.medium_count or 0),
            'hard_count': int(stat.hard_count or 0),
            'family_count': int(stat.family_count or 0),
            'material_count': int(stat.material_count or 0),
            'bank_version_count': int(bank_version_count or 0),
            'release_count': int(stat.release_count or 0),
            'published_release_count': published,
            'release_status': release_status,
            'is_published': is_published,
            'published_chapter_count': 1 if is_published else 0,
            'ready_to_release': bool(stat.ready_to_release) and not is_published,
            'unresolved_count': unresolved,
            'is_review_done': is_done,
            'has_questions': bool(total),
            'status': status,
            'question_limit': question_limit,
            'remaining_quota': max(0, question_limit - total),
            'updated_at': stat.updated_at.isoformat() if stat.updated_at else None,
        }

    def chapter_stats_map(self) -> dict[str, dict[str, Any]]:
        question_limit = self.chapter_question_limit_default()
        chapters = self.db.query(SubjectChapter).all()
        stats = {row.chapter_id: row for row in self.db.query(BankChapterStats).all()}
        version_counts = {
            chapter_id: int(count or 0)
            for chapter_id, count in self.db.query(QuestionBankVersion.chapter_id, func.count(QuestionBankVersion.id)).group_by(QuestionBankVersion.chapter_id).all()
        }
        return {
            chapter.id: self._serialize_chapter_stat(chapter, stats.get(chapter.id), question_limit=question_limit, bank_version_count=version_counts.get(chapter.id, 0))
            for chapter in chapters
        }

    def offering_summary_map(self, chapter_stats: dict[str, dict[str, Any]] | None = None) -> dict[str, dict[str, Any]]:
        chapter_stats = chapter_stats or self.chapter_stats_map()
        offerings = self.db.query(SubjectOffering).all()
        chapters = self.db.query(SubjectChapter).all()
        chapter_limit = self.chapter_question_limit_default()
        out: dict[str, dict[str, Any]] = {}
        for offering in offerings:
            own = [c for c in chapters if c.subject_offering_id == offering.id]
            stats = [chapter_stats.get(c.id, {}) for c in own]
            chapter_count = len(own)
            done = len([s for s in stats if s.get('is_review_done')])
            unresolved = sum(int(s.get('unresolved_count') or 0) for s in stats)
            draft_error = sum(int(s.get('draft_error_count') or 0) for s in stats)
            pending = sum(int(s.get('pending_review_count') or 0) for s in stats)
            total = sum(int(s.get('total_questions') or 0) for s in stats)
            approved = sum(int(s.get('approved_count') or 0) for s in stats)
            published_releases = sum(int(s.get('published_release_count') or 0) for s in stats)
            published_chapters = sum(1 for s in stats if s.get('release_status') == 'published' or s.get('is_published'))
            ready_to_release = sum(1 for s in stats if s.get('ready_to_release'))
            capacity = sum(int(s.get('question_limit') or chapter_limit) for s in stats)
            is_published = chapter_count > 0 and published_chapters == chapter_count
            is_done = is_published or (chapter_count > 0 and done == chapter_count)
            out[offering.id] = {
                'subject_offering_id': offering.id,
                'subject_id': offering.subject_id,
                'code': offering.code,
                'name': offering.name,
                'chapter_count': chapter_count,
                'review_done_chapter_count': done,
                'review_not_done_chapter_count': max(0, chapter_count - done),
                'total_questions': total,
                'approved_count': approved,
                'pending_review_count': pending,
                'draft_error_count': draft_error,
                'unresolved_count': unresolved,
                'published_release_count': published_releases,
                'published_chapter_count': published_chapters,
                'is_published': is_published,
                'ready_to_release_chapter_count': 0 if is_published else ready_to_release,
                'chapter_question_limit': chapter_limit,
                'question_capacity': capacity,
                'is_review_done': is_done,
                'status': 'published' if is_published else ('ready' if is_done else ('needs_fix' if draft_error else ('needs_review' if unresolved else ('empty' if chapter_count == 0 else 'not_ready')))),
            }
        return out

    def subject_summary_map(self, offering_stats: dict[str, dict[str, Any]] | None = None) -> dict[str, dict[str, Any]]:
        offering_stats = offering_stats or self.offering_summary_map()
        subjects = self.db.query(Subject).all()
        offerings = self.db.query(SubjectOffering).all()
        out: dict[str, dict[str, Any]] = {}
        for subject in subjects:
            own = [o for o in offerings if o.subject_id == subject.id]
            stats = [offering_stats.get(o.id, {}) for o in own]
            version_count = len(own)
            done = len([s for s in stats if s.get('is_review_done')])
            unresolved = sum(int(s.get('unresolved_count') or 0) for s in stats)
            draft_error = sum(int(s.get('draft_error_count') or 0) for s in stats)
            total = sum(int(s.get('total_questions') or 0) for s in stats)
            approved = sum(int(s.get('approved_count') or 0) for s in stats)
            pending = sum(int(s.get('pending_review_count') or 0) for s in stats)
            published_releases = sum(int(s.get('published_release_count') or 0) for s in stats)
            published_versions = sum(1 for s in stats if s.get('is_published') or s.get('status') == 'published')
            ready_to_release = sum(int(s.get('ready_to_release_chapter_count') or 0) for s in stats)
            capacity = sum(int(s.get('question_capacity') or 0) for s in stats)
            is_published = version_count > 0 and published_versions == version_count
            is_done = is_published or (version_count > 0 and done == version_count)
            out[subject.id] = {
                'subject_id': subject.id,
                'department_id': subject.department_id,
                'code': subject.code,
                'name': subject.name,
                'subject_version_count': version_count,
                'review_done_version_count': done,
                'review_not_done_version_count': max(0, version_count - done),
                'total_questions': total,
                'approved_count': approved,
                'pending_review_count': pending,
                'draft_error_count': draft_error,
                'unresolved_count': unresolved,
                'published_release_count': published_releases,
                'published_version_count': published_subjects,
                'is_published': is_published,
                'ready_to_release_chapter_count': 0 if is_published else ready_to_release,
                'question_capacity': capacity,
                'is_review_done': is_done,
                'status': 'published' if is_published else ('ready' if is_done else ('needs_fix' if draft_error else ('needs_review' if unresolved else ('empty' if version_count == 0 else 'not_ready')))),
            }
        return out

    def department_summary_map(self, subject_stats: dict[str, dict[str, Any]] | None = None) -> dict[str, dict[str, Any]]:
        subject_stats = subject_stats or self.subject_summary_map()
        departments = self.db.query(Department).all()
        subjects = self.db.query(Subject).all()
        out: dict[str, dict[str, Any]] = {}
        for department in departments:
            own = [s for s in subjects if s.department_id == department.id]
            stats = [subject_stats.get(s.id, {}) for s in own]
            subject_count = len(own)
            done = len([s for s in stats if s.get('is_review_done')])
            unresolved = sum(int(s.get('unresolved_count') or 0) for s in stats)
            draft_error = sum(int(s.get('draft_error_count') or 0) for s in stats)
            total = sum(int(s.get('total_questions') or 0) for s in stats)
            approved = sum(int(s.get('approved_count') or 0) for s in stats)
            pending = sum(int(s.get('pending_review_count') or 0) for s in stats)
            published_releases = sum(int(s.get('published_release_count') or 0) for s in stats)
            published_subjects = sum(1 for s in stats if s.get('is_published') or s.get('status') == 'published')
            ready_to_release = sum(int(s.get('ready_to_release_chapter_count') or 0) for s in stats)
            capacity = sum(int(s.get('question_capacity') or 0) for s in stats)
            is_published = subject_count > 0 and published_subjects == subject_count
            is_done = is_published or (subject_count > 0 and done == subject_count)
            out[department.id] = {
                'department_id': department.id,
                'code': department.code,
                'name': department.name,
                'subject_count': subject_count,
                'review_done_subject_count': done,
                'review_not_done_subject_count': max(0, subject_count - done),
                'total_questions': total,
                'approved_count': approved,
                'pending_review_count': pending,
                'draft_error_count': draft_error,
                'unresolved_count': unresolved,
                'published_release_count': published_releases,
                'published_version_count': published_subjects,
                'is_published': is_published,
                'ready_to_release_chapter_count': 0 if is_published else ready_to_release,
                'question_capacity': capacity,
                'is_review_done': is_done,
                'status': 'published' if is_published else ('ready' if is_done else ('needs_fix' if draft_error else ('needs_review' if unresolved else ('empty' if subject_count == 0 else 'not_ready')))),
            }
        return out

    def dashboard_overview(self, *, use_cache: bool = True) -> dict[str, Any]:
        cache_key = 'bank_dashboard_overview:v1'
        if use_cache:
            cached = self._cache_get(cache_key)
            if cached:
                return cached
        chapter_stats = self.chapter_stats_map()
        offering_stats = self.offering_summary_map(chapter_stats)
        subject_stats = self.subject_summary_map(offering_stats)
        department_stats = self.department_summary_map(subject_stats)
        chapters_needing_work = [s for s in chapter_stats.values() if int(s.get('unresolved_count') or 0) > 0]
        chapters_ready = [s for s in chapter_stats.values() if s.get('ready_to_release')]
        departments_with_work = len([s for s in department_stats.values() if int(s.get('unresolved_count') or 0) > 0])
        subjects_with_work = len([s for s in subject_stats.values() if int(s.get('unresolved_count') or 0) > 0])
        versions_with_work = len([s for s in offering_stats.values() if int(s.get('unresolved_count') or 0) > 0])
        payload = {
            'ok': True,
            'summary_source': 'ai_bank_chapter_stats',
            'cache_ttl_seconds': int(getattr(settings, 'bank_dashboard_cache_ttl_seconds', 45) or 45),
            'departments_total': len(department_stats),
            'departments_done': max(0, len(department_stats) - departments_with_work),
            'departments_not_done': departments_with_work,
            'subjects_total': len(subject_stats),
            'subjects_done': max(0, len(subject_stats) - subjects_with_work),
            'subjects_not_done': subjects_with_work,
            'subject_versions_total': len(offering_stats),
            'subject_versions_done': max(0, len(offering_stats) - versions_with_work),
            'subject_versions_not_done': versions_with_work,
            'chapters_total': len(chapter_stats),
            'chapters_needing_review': len(chapters_needing_work),
            'chapters_ready_to_release': len(chapters_ready),
            'total_questions': sum(int(s.get('total_questions') or 0) for s in chapter_stats.values()),
            'approved_count': sum(int(s.get('approved_count') or 0) for s in chapter_stats.values()),
            'pending_review_count': sum(int(s.get('pending_review_count') or 0) for s in chapter_stats.values()),
            'draft_error_count': sum(int(s.get('draft_error_count') or 0) for s in chapter_stats.values()),
            'next_actions': self.build_dashboard_next_actions(chapter_stats),
        }
        self._cache_set(cache_key, payload)
        return payload

    def build_dashboard_next_actions(self, chapter_stats: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
        chapters = {c.id: c for c in self.db.query(SubjectChapter).all()}
        offerings = {o.id: o for o in self.db.query(SubjectOffering).all()}
        subjects = {s.id: s for s in self.db.query(Subject).all()}
        actions: list[dict[str, Any]] = []
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

    def rebuild_chapter_stats(self, *, chapter_id: str | None = None, commit: bool = True) -> dict[str, Any]:
        chapters_query = self.db.query(SubjectChapter)
        if chapter_id:
            chapters_query = chapters_query.filter(SubjectChapter.id == chapter_id)
        chapters = chapters_query.all()
        if chapter_id and not chapters:
            raise ValueError('Không tìm thấy chapter cần rebuild stats')
        chapter_ids = [c.id for c in chapters]
        if not chapter_ids:
            return {'ok': True, 'rebuilt_count': 0, 'chapter_id': chapter_id}

        version_query = self.db.query(QuestionBankVersion).filter(QuestionBankVersion.chapter_id.in_(chapter_ids))
        versions = version_query.order_by(QuestionBankVersion.chapter_id.asc(), QuestionBankVersion.created_at.desc(), QuestionBankVersion.id.desc()).all()
        latest_by_chapter: dict[str, str] = {}
        version_count_by_chapter: dict[str, int] = {}
        for version in versions:
            version_count_by_chapter[version.chapter_id] = version_count_by_chapter.get(version.chapter_id, 0) + 1
            latest_by_chapter.setdefault(version.chapter_id, version.id)

        chapter_expr = func.coalesce(Question.subject_chapter_id, QuestionBankVersion.chapter_id)
        active = Question.is_retired.is_(False)
        query = self.db.query(
            chapter_expr.label('chapter_id'),
            func.sum(case((active, 1), else_=0)).label('total_questions'),
            func.sum(case((and_(active, Question.status.in_(BANK_APPROVED_STATUSES)), 1), else_=0)).label('approved_count'),
            func.sum(case((and_(active, Question.status.in_(BANK_PENDING_STATUSES)), 1), else_=0)).label('pending_review_count'),
            func.sum(case((and_(active, Question.status.in_(BANK_ERROR_STATUSES)), 1), else_=0)).label('draft_error_count'),
            func.sum(case((and_(active, Question.status == 'rejected'), 1), else_=0)).label('rejected_count'),
            func.sum(case((Question.is_retired.is_(True), 1), else_=0)).label('retired_count'),
            func.sum(case((and_(active, Question.is_duplicate.is_(True)), 1), else_=0)).label('duplicate_count'),
            func.sum(case((and_(active, Question.difficulty.in_(DIFFICULTY_EASY)), 1), else_=0)).label('easy_count'),
            func.sum(case((and_(active, Question.difficulty.in_(DIFFICULTY_MEDIUM)), 1), else_=0)).label('medium_count'),
            func.sum(case((and_(active, Question.difficulty.in_(DIFFICULTY_HARD)), 1), else_=0)).label('hard_count'),
            func.count(distinct(case((and_(active, Question.question_family_id.isnot(None)), Question.question_family_id), else_=None))).label('family_count'),
        ).outerjoin(QuestionBankVersion, Question.bank_version_id == QuestionBankVersion.id)
        query = query.filter(Question.bank_version_id.isnot(None), chapter_expr.in_(chapter_ids)).group_by(chapter_expr)
        question_rows = {row.chapter_id: row for row in query.all() if row.chapter_id}

        material_rows = {
            cid: int(count or 0)
            for cid, count in self.db.query(LearningMaterialVersion.chapter_id, func.count(LearningMaterialVersion.id))
            .filter(LearningMaterialVersion.chapter_id.in_(chapter_ids), LearningMaterialVersion.status != 'deleted')
            .group_by(LearningMaterialVersion.chapter_id)
            .all()
        }
        release_rows = {
            cid: {'release_count': int(release_count or 0), 'published_release_count': int(published_count or 0)}
            for cid, release_count, published_count in self.db.query(
                QuestionBankRelease.chapter_id,
                func.count(QuestionBankRelease.id),
                func.sum(case((QuestionBankRelease.status == 'published', 1), else_=0)),
            )
            .filter(QuestionBankRelease.chapter_id.in_(chapter_ids))
            .group_by(QuestionBankRelease.chapter_id)
            .all()
        }

        now = datetime.utcnow()
        rebuilt = 0
        for chapter in chapters:
            q = question_rows.get(chapter.id)
            total = int(getattr(q, 'total_questions', 0) or 0)
            approved = int(getattr(q, 'approved_count', 0) or 0)
            pending = int(getattr(q, 'pending_review_count', 0) or 0)
            draft_error = int(getattr(q, 'draft_error_count', 0) or 0)
            unresolved = pending + draft_error
            rel = release_rows.get(chapter.id, {'release_count': 0, 'published_release_count': 0})
            published = int(rel.get('published_release_count') or 0)
            row = self.db.get(BankChapterStats, chapter.id)
            if not row:
                row = BankChapterStats(chapter_id=chapter.id, subject_id=chapter.subject_id, subject_offering_id=chapter.subject_offering_id)
                self.db.add(row)
            row.subject_id = chapter.subject_id
            row.subject_offering_id = chapter.subject_offering_id
            row.latest_bank_version_id = latest_by_chapter.get(chapter.id)
            row.total_questions = total
            row.approved_count = approved
            row.pending_review_count = pending
            row.draft_error_count = draft_error
            row.rejected_count = int(getattr(q, 'rejected_count', 0) or 0)
            row.retired_count = int(getattr(q, 'retired_count', 0) or 0)
            row.duplicate_count = int(getattr(q, 'duplicate_count', 0) or 0)
            row.easy_count = int(getattr(q, 'easy_count', 0) or 0)
            row.medium_count = int(getattr(q, 'medium_count', 0) or 0)
            row.hard_count = int(getattr(q, 'hard_count', 0) or 0)
            row.family_count = int(getattr(q, 'family_count', 0) or 0)
            row.material_count = int(material_rows.get(chapter.id, 0) or 0)
            row.release_count = int(rel.get('release_count') or 0)
            row.published_release_count = published
            row.unresolved_count = unresolved
            row.ready_to_release = bool(total > 0 and approved > 0 and unresolved == 0 and published == 0)
            row.updated_at = now
            rebuilt += 1
        if commit:
            self.db.commit()
        else:
            self.db.flush()
        self.invalidate_cache()
        return {'ok': True, 'rebuilt_count': rebuilt, 'chapter_id': chapter_id, 'summary_table': 'ai_bank_chapter_stats'}

    def refresh_for_bank_version(self, bank_version_id: str | None, *, commit: bool = True) -> dict[str, Any] | None:
        if not bank_version_id:
            return None
        version = self.db.get(QuestionBankVersion, bank_version_id)
        if not version:
            return None
        return self.rebuild_chapter_stats(chapter_id=version.chapter_id, commit=commit)

    def stats_health(self) -> dict[str, Any]:
        chapter_count = int(self.db.query(func.count(SubjectChapter.id)).scalar() or 0)
        stats_count = int(self.db.query(func.count(BankChapterStats.chapter_id)).scalar() or 0)
        stale_rows = self.db.query(BankChapterStats).filter(BankChapterStats.updated_at.is_(None)).count()
        oldest = self.db.query(func.min(BankChapterStats.updated_at)).scalar()
        newest = self.db.query(func.max(BankChapterStats.updated_at)).scalar()
        return {
            'ok': stats_count >= chapter_count and stale_rows == 0,
            'summary_table': 'ai_bank_chapter_stats',
            'chapter_count': chapter_count,
            'stats_count': stats_count,
            'missing_stats_count': max(0, chapter_count - stats_count),
            'stale_stats_count': int(stale_rows or 0),
            'oldest_stats_updated_at': oldest.isoformat() if oldest else None,
            'newest_stats_updated_at': newest.isoformat() if newest else None,
            'dashboard_reads_questions_directly': False,
            'message': 'Stats đầy đủ.' if stats_count >= chapter_count else 'Cần chạy rebuild stats sau migration hoặc sau import dữ liệu cũ.',
        }
