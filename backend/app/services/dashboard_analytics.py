from __future__ import annotations

import hashlib
import json
from collections import defaultdict
from datetime import date, datetime, time, timedelta
from typing import Any

from sqlalchemy import and_, func, or_
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.audit import AuditLog
from app.models.question import Question
from app.models.question_bank import (
    BankChapterStats,
    BankOperationJob,
    Department,
    QuestionBankRelease,
    QuestionBankVersion,
    Subject,
    SubjectChapter,
    SubjectOffering,
)
from app.models.rbac import UserRoleAssignment
from app.services.bank_dashboard_stats import BankDashboardStatsService
from app.services.business_rbac import BusinessRBACService


def _safe_int(value: Any) -> int:
    try:
        return int(value or 0)
    except Exception:
        return 0


def _iso(dt: datetime | None) -> str | None:
    return dt.isoformat() if dt else None


class DashboardAnalyticsService:
    """Actionable, scope-aware dashboard analytics for AI Question Bank.

    This service intentionally reads precomputed ai_bank_chapter_stats for heavy
    totals. Querying ai_questions is restricted to bounded, date-filtered trend
    and alert calculations inside the current RBAC scope.
    """

    STATUS_LABELS = {
        'draft': 'Draft',
        'pending_review': 'Chờ duyệt',
        'approved': 'Đã duyệt',
        'rejected': 'Bị từ chối',
        'draft_error': 'Câu lỗi',
    }
    DIFFICULTY_LABELS = {'easy': 'Dễ', 'medium': 'Trung bình', 'hard': 'Khó'}
    QUESTION_TYPE_LABELS = {
        'single_choice': 'MCQ một đáp án',
        'multiple_choice': 'MCQ nhiều đáp án',
        'essay': 'Tự luận',
        'short_answer': 'Trả lời ngắn',
        'unknown': 'Khác',
    }

    def __init__(self, db: Session):
        self.db = db
        self.biz = BusinessRBACService(db)
        self.stats_service = BankDashboardStatsService(db)

    def _redis_client(self):
        try:
            import redis
            return redis.Redis.from_url(settings.redis_url, decode_responses=True)
        except Exception:
            return None

    def _cache_get(self, key: str) -> Any | None:
        client = self._redis_client()
        if not client:
            return None
        try:
            raw = client.get(key)
            return json.loads(raw) if raw else None
        except Exception:
            return None

    def _cache_set(self, key: str, value: Any, ttl_seconds: int) -> None:
        client = self._redis_client()
        if not client:
            return
        try:
            client.setex(key, max(5, min(int(ttl_seconds or 60), 300)), json.dumps(value, ensure_ascii=False, default=str))
        except Exception:
            return

    def _filters(self, date_range: str = '30d', from_date: str | None = None, to_date: str | None = None) -> dict[str, Any]:
        today = date.today()
        normalized = (date_range or '30d').strip().lower()
        if normalized == 'today':
            start = today
            end = today
        elif normalized == '7d':
            start = today - timedelta(days=6)
            end = today
        elif normalized == 'custom' and from_date and to_date:
            start = date.fromisoformat(from_date)
            end = date.fromisoformat(to_date)
            if end < start:
                start, end = end, start
        else:
            normalized = '30d'
            start = today - timedelta(days=29)
            end = today
        start_dt = datetime.combine(start, time.min)
        end_dt = datetime.combine(end, time.max)
        return {
            'date_range': normalized,
            'from_date': start.isoformat(),
            'to_date': end.isoformat(),
            'start_dt': start_dt,
            'end_dt': end_dt,
            'days': max(1, (end - start).days + 1),
        }

    def _scope_hash(self, user: Any) -> str:
        if self.biz.is_system_admin(user):
            return 'system-admin'
        parts = []
        for row in self.biz.active_assignments_for_actor(user):
            parts.append('|'.join([
                row.role_code or '',
                row.scope_type or '',
                row.scope_id or '',
                _iso(row.updated_at) or _iso(row.created_at) or '',
            ]))
        raw = ';;'.join(sorted(parts)) or str(getattr(user, 'user_id', '') or 'anonymous')
        return hashlib.sha1(raw.encode('utf-8')).hexdigest()[:16]

    def _scope_label(self, user: Any) -> dict[str, Any]:
        if self.biz.is_system_admin(user):
            return {'role': 'SYSTEM_ADMIN', 'label': 'Toàn hệ thống', 'scope_type': 'SYSTEM', 'scope_id': '*'}
        assignments = self.biz.active_assignments_for_actor(user)
        if not assignments:
            return {'role': getattr(user, 'role', 'viewer'), 'label': 'Chưa được phân quyền Bank', 'scope_type': 'NONE', 'scope_id': ''}
        role_rank = {'DEPARTMENT_HEAD': 3, 'SUBJECT_OWNER': 2, 'QUESTION_REVIEWER': 1}
        best = sorted(assignments, key=lambda a: (role_rank.get(a.role_code, 0), a.created_at or datetime.min), reverse=True)[0]
        label = f"{best.role_code} · {best.scope_type}:{best.scope_id}"
        try:
            scope = self.biz.entity_scope(best.scope_type, best.scope_id)
            if scope.scope_type == 'DEPARTMENT' and scope.department_id:
                item = self.db.get(Department, scope.department_id)
                if item:
                    label = f"Trưởng bộ môn {item.name}"
            elif scope.scope_type == 'SUBJECT' and scope.subject_id:
                item = self.db.get(Subject, scope.subject_id)
                if item:
                    label = f"Chủ môn {item.code} - {item.name}"
            elif scope.scope_type == 'SUBJECT_VERSION' and scope.subject_offering_id:
                item = self.db.get(SubjectOffering, scope.subject_offering_id)
                if item:
                    label = f"Chủ môn version {item.code}"
            elif scope.scope_type == 'CHAPTER' and scope.chapter_id:
                item = self.db.get(SubjectChapter, scope.chapter_id)
                if item:
                    label = f"Người duyệt {item.title}"
        except Exception:
            pass
        return {'role': best.role_code, 'label': label, 'scope_type': best.scope_type, 'scope_id': best.scope_id}

    def _visible_stats(self, user: Any) -> tuple[dict[str, dict[str, Any]], dict[str, dict[str, Any]], dict[str, dict[str, Any]], dict[str, dict[str, Any]]]:
        if self.biz.is_system_admin(user):
            chapters = self.stats_service.chapter_stats_map()
            offerings = self.stats_service.offering_summary_map(chapters)
            subjects = self.stats_service.subject_summary_map(offerings)
            departments = self.stats_service.department_summary_map(subjects)
            return chapters, offerings, subjects, departments
        chapter_ids = self.biz.accessible_chapter_ids(user) or set()
        offering_ids = self.biz.accessible_subject_offering_ids(user) or set()
        subject_ids = self.biz.accessible_subject_ids(user) or set()
        department_ids = self.biz.accessible_department_ids(user) or set()
        all_chapters = self.stats_service.chapter_stats_map()
        chapters = {cid: row for cid, row in all_chapters.items() if cid in chapter_ids}
        offerings_all = self.stats_service.offering_summary_map(chapters)
        subjects_all = self.stats_service.subject_summary_map(offerings_all)
        departments_all = self.stats_service.department_summary_map(subjects_all)
        return (
            chapters,
            {oid: row for oid, row in offerings_all.items() if oid in offering_ids},
            {sid: row for sid, row in subjects_all.items() if sid in subject_ids},
            {did: row for did, row in departments_all.items() if did in department_ids},
        )

    def _question_query(self, user: Any, filters: dict[str, Any], *, apply_date: bool = True):
        query = self.biz.apply_hierarchy_filter(self.db.query(Question), Question, user).filter(Question.bank_version_id.isnot(None))
        if apply_date:
            query = query.filter(Question.created_at >= filters['start_dt'], Question.created_at <= filters['end_dt'])
        return query

    def _drilldown(self, route: str, query: dict[str, Any] | None = None) -> dict[str, Any]:
        return {'route': route, 'query': query or {}}

    def _kpi(self, key: str, label: str, value: int, *, delta: int = 0, percent: float | None = None, overdue: int | None = None, drilldown: dict[str, Any] | None = None) -> dict[str, Any]:
        payload = {'key': key, 'label': label, 'value': int(value or 0), 'delta': int(delta or 0), 'delta_label': f"{delta:+d} trong kỳ" if delta else 'Không đổi trong kỳ', 'drilldown': drilldown or self._drilldown('/bank')}
        if percent is not None:
            payload['percent'] = round(float(percent), 1)
        if overdue is not None:
            payload['overdue'] = int(overdue or 0)
        return payload

    def _status_chart(self, totals: dict[str, int]) -> dict[str, Any]:
        total = max(1, sum(totals.values()))
        items = []
        for key in ['draft', 'pending_review', 'approved', 'rejected', 'draft_error']:
            value = int(totals.get(key, 0) or 0)
            if value <= 0 and key == 'draft_error':
                continue
            items.append({
                'key': key,
                'label': self.STATUS_LABELS.get(key, key),
                'value': value,
                'percent': round(value * 100 / total, 1) if total else 0,
                'drilldown': self._drilldown('/bank/search', {'entity': 'questions', 'status': key}),
            })
        return {'key': 'question_status', 'title': 'Tình trạng câu hỏi', 'type': 'donut', 'items': items}

    def _difficulty_chart(self, chapters: dict[str, dict[str, Any]]) -> dict[str, Any]:
        totals = {
            'easy': sum(_safe_int(row.get('easy_count')) for row in chapters.values()),
            'medium': sum(_safe_int(row.get('medium_count')) for row in chapters.values()),
            'hard': sum(_safe_int(row.get('hard_count')) for row in chapters.values()),
        }
        total = max(1, sum(totals.values()))
        return {
            'key': 'difficulty_distribution',
            'title': 'Phân bố độ khó',
            'type': 'donut',
            'items': [
                {'key': key, 'label': self.DIFFICULTY_LABELS[key], 'value': value, 'percent': round(value * 100 / total, 1), 'drilldown': self._drilldown('/bank/search', {'entity': 'questions', 'difficulty': key})}
                for key, value in totals.items()
            ],
        }

    def _type_chart(self, user: Any, filters: dict[str, Any]) -> dict[str, Any]:
        rows = self._question_query(user, filters, apply_date=False).with_entities(Question.question_type, func.count(Question.id)).group_by(Question.question_type).limit(20).all()
        items = []
        total = sum(int(count or 0) for _, count in rows) or 1
        for raw_type, count in rows:
            key = raw_type or 'unknown'
            value = int(count or 0)
            items.append({'key': key, 'label': self.QUESTION_TYPE_LABELS.get(key, key), 'value': value, 'percent': round(value * 100 / total, 1), 'drilldown': self._drilldown('/bank/search', {'entity': 'questions', 'question_type': key})})
        return {'key': 'question_type_distribution', 'title': 'Loại câu hỏi', 'type': 'donut', 'items': items}

    def _new_questions_line(self, user: Any, filters: dict[str, Any]) -> dict[str, Any]:
        rows = self._question_query(user, filters, apply_date=True).with_entities(func.date(Question.created_at), func.count(Question.id)).group_by(func.date(Question.created_at)).all()
        by_date = {str(day): int(count or 0) for day, count in rows}
        start = date.fromisoformat(filters['from_date'])
        days = int(filters['days'])
        items = []
        for i in range(days):
            current = start + timedelta(days=i)
            day = current.isoformat()
            label = current.strftime('%d/%m')
            items.append({'date': day, 'label': label, 'value': by_date.get(day, 0), 'drilldown': self._drilldown('/bank/search', {'entity': 'questions', 'created_from': day, 'created_to': day})})
        return {'key': 'new_questions_by_day', 'title': 'Câu hỏi mới theo ngày', 'type': 'line', 'items': items}

    def _questions_by_subject(self, subjects: dict[str, dict[str, Any]]) -> dict[str, Any]:
        items = []
        for sid, row in sorted(subjects.items(), key=lambda item: _safe_int(item[1].get('total_questions')), reverse=True)[:12]:
            label = ' - '.join([x for x in [row.get('code'), row.get('name')] if x]) or sid
            items.append({
                'subject_id': sid,
                'label': label,
                'value': _safe_int(row.get('total_questions')),
                'approved': _safe_int(row.get('approved_count')),
                'pending': _safe_int(row.get('pending_review_count')),
                'rejected': _safe_int(row.get('rejected_count')),
                'drilldown': self._drilldown(f'/bank/subjects/{sid}/versions'),
            })
        return {'key': 'questions_by_subject', 'title': 'Số câu hỏi theo môn', 'type': 'horizontal_bar', 'items': items}

    def _term_comparison(self, user: Any, offerings: dict[str, dict[str, Any]]) -> dict[str, Any]:
        visible_ids = set(offerings.keys())
        query = self.biz.apply_subject_offering_filter(self.db.query(SubjectOffering), user)
        offering_rows = query.filter(SubjectOffering.id.in_(visible_ids)).all() if visible_ids else []
        terms = []
        for item in offering_rows:
            term = item.term or (item.code.split('_')[-1] if '_' in item.code else item.version_code or item.code)
            if term not in terms:
                terms.append(term)
        # Prefer latest created terms by actual offering created_at order.
        term_order = []
        for item in sorted(offering_rows, key=lambda x: x.created_at or datetime.min, reverse=True):
            term = item.term or (item.code.split('_')[-1] if '_' in item.code else item.version_code or item.code)
            if term not in term_order:
                term_order.append(term)
        current_term = term_order[0] if term_order else 'Kỳ hiện tại'
        previous_term = term_order[1] if len(term_order) > 1 else 'Kỳ trước'
        subjects = {s.id: s for s in self.db.query(Subject).all()}
        by_subject: dict[str, dict[str, Any]] = defaultdict(lambda: {'current': 0, 'previous': 0, 'label': ''})
        for item in offering_rows:
            term = item.term or (item.code.split('_')[-1] if '_' in item.code else item.version_code or item.code)
            stat = offerings.get(item.id, {})
            bucket = by_subject[item.subject_id]
            subject = subjects.get(item.subject_id)
            bucket['label'] = subject.code if subject else item.subject_id
            if term == current_term:
                bucket['current'] += _safe_int(stat.get('total_questions'))
            elif term == previous_term:
                bucket['previous'] += _safe_int(stat.get('total_questions'))
        items = []
        for subject_id, data in sorted(by_subject.items(), key=lambda kv: (kv[1]['current'] + kv[1]['previous']), reverse=True)[:10]:
            items.append({
                'subject_id': subject_id,
                'label': data['label'] or subject_id,
                'current': int(data['current']),
                'previous': int(data['previous']),
                'delta': int(data['current']) - int(data['previous']),
                'drilldown': self._drilldown(f'/bank/subjects/{subject_id}/versions'),
            })
        return {'key': 'term_comparison', 'title': 'So sánh kỳ này và kỳ trước', 'type': 'grouped_bar', 'current_term': current_term, 'previous_term': previous_term, 'items': items}

    def _overdue_pending_count(self, user: Any, *, days: int = 3) -> int:
        cutoff = datetime.utcnow() - timedelta(days=days)
        return int(self._question_query(user, {'start_dt': datetime.min, 'end_dt': datetime.max}, apply_date=False)
                   .filter(Question.status.in_(['pending_review', 'needs_review']), Question.updated_at <= cutoff).count() or 0)

    def get_alerts(self, user: Any, filters: dict[str, Any] | None = None, *, limit: int = 12) -> list[dict[str, Any]]:
        filters = filters or self._filters('30d')
        cache_key = f"dashboard:alerts:{self._scope_hash(user)}:{filters['date_range']}:{filters['from_date']}:{filters['to_date']}:{limit}"
        cached = self._cache_get(cache_key)
        if cached is not None:
            return cached
        chapters, offerings, subjects, _departments = self._visible_stats(user)
        alerts: list[dict[str, Any]] = []
        cutoff = datetime.utcnow() - timedelta(days=3)
        pending_rows = (
            self._question_query(user, filters, apply_date=False)
            .filter(Question.status.in_(['pending_review', 'needs_review']), Question.updated_at <= cutoff)
            .with_entities(Question.subject_chapter_id, func.count(Question.id), func.min(Question.updated_at))
            .group_by(Question.subject_chapter_id)
            .limit(limit)
            .all()
        )
        chapter_entities = {c.id: c for c in self.db.query(SubjectChapter).filter(SubjectChapter.id.in_([cid for cid, *_ in pending_rows if cid])).all()}
        for chapter_id, count, oldest in pending_rows:
            chapter = chapter_entities.get(chapter_id)
            title = chapter.title if chapter else chapter_id or 'Chapter'
            alerts.append({
                'id': f'pending-overdue-{chapter_id}',
                'severity': 'critical',
                'type': 'pending_overdue',
                'title': f'{int(count or 0)} câu hỏi chờ duyệt quá 3 ngày',
                'description': f'{title} cần xử lý duyệt câu hỏi lâu ngày.',
                'age_days': max(3, (datetime.utcnow() - oldest).days) if oldest else 3,
                'drilldown': self._drilldown(f'/bank/chapters/{chapter_id}', {'status': 'pending_review', 'overdue': 'true'}),
            })
        for chapter_id, stat in sorted(chapters.items(), key=lambda kv: _safe_int(kv[1].get('remaining_quota')), reverse=True):
            if _safe_int(stat.get('total_questions')) < _safe_int(stat.get('question_limit')) and not stat.get('is_published'):
                missing = _safe_int(stat.get('question_limit')) - _safe_int(stat.get('total_questions'))
                if missing <= 0:
                    continue
                alerts.append({
                    'id': f'chapter-under-minimum-{chapter_id}',
                    'severity': 'warning',
                    'type': 'subject_under_minimum_questions',
                    'title': f'{stat.get("title") or "Bài"} còn thiếu {missing} câu',
                    'description': f"Hiện có {_safe_int(stat.get('total_questions'))}/{_safe_int(stat.get('question_limit'))} câu trong quota bài.",
                    'drilldown': self._drilldown(f'/bank/chapters/{chapter_id}'),
                })
                if len(alerts) >= limit:
                    break
        failed_jobs = self.biz.apply_hierarchy_filter(self.db.query(BankOperationJob), BankOperationJob, user).filter(BankOperationJob.status == 'failed').order_by(BankOperationJob.created_at.desc()).limit(5).all()
        for job in failed_jobs:
            alerts.append({
                'id': f'operation-job-failed-{job.id}',
                'severity': 'critical',
                'type': 'operation_job_failed',
                'title': f'Job {job.operation_type} thất bại',
                'description': job.error_message or job.progress_label or 'Cần kiểm tra Tiến trình job.',
                'drilldown': self._drilldown('/jobs', {'status': 'failed'}),
            })
        if self.biz.is_system_admin(user) or any(a.role_code in ['SYSTEM_ADMIN', 'DEPARTMENT_HEAD', 'SUBJECT_OWNER'] for a in self.biz.active_assignments_for_actor(user)):
            active_assignments = self.biz.active_assignments_for_actor(user) if not self.biz.is_system_admin(user) else self.biz.active_assignments_query().limit(200).all()
            cutoff_inactive = datetime.utcnow() - timedelta(days=14)
            for assignment in active_assignments[:20]:
                recent = self.db.query(AuditLog.id).filter(AuditLog.actor_id == assignment.user_id, AuditLog.created_at >= cutoff_inactive).first()
                if not recent:
                    alerts.append({
                        'id': f'inactive-assigned-user-{assignment.id}',
                        'severity': 'info',
                        'type': 'inactive_assigned_user',
                        'title': 'User được gán quyền nhưng chưa hoạt động',
                        'description': f'{assignment.user_id} chưa có audit activity trong 14 ngày gần đây.',
                        'drilldown': self._drilldown('/users'),
                    })
                    break
        alerts = alerts[:limit]
        self._cache_set(cache_key, alerts, 15)
        return alerts

    def _audit_visible(self, user: Any, audit: AuditLog) -> bool:
        if self.biz.is_system_admin(user):
            return True
        if audit.actor_id == getattr(user, 'user_id', None):
            return True
        target_type = (audit.target_type or '').upper()
        scope_map = {
            'DEPARTMENT': 'DEPARTMENT',
            'SUBJECT': 'SUBJECT',
            'SUBJECT_OFFERING': 'SUBJECT_VERSION',
            'SUBJECT_VERSION': 'SUBJECT_VERSION',
            'CHAPTER': 'CHAPTER',
            'QUESTION': 'QUESTION',
            'BANK_VERSION': 'BANK_VERSION',
            'BANK_RELEASE': 'RELEASE',
            'RELEASE': 'RELEASE',
        }
        if not audit.target_id or target_type not in scope_map:
            return False
        try:
            return self.biz.is_visible_scope(user, scope_map[target_type], audit.target_id)
        except Exception:
            return False

    def _activity_message(self, audit: AuditLog) -> str:
        action = audit.action or 'activity'
        actor = audit.actor_id or 'system'
        msg = audit.message or ''
        if msg:
            return msg
        if 'generate' in action:
            return f'{actor} vừa tạo câu hỏi.'
        if 'review' in action or 'approve' in action:
            return f'{actor} vừa duyệt câu hỏi.'
        if 'publish' in action:
            return f'{actor} vừa publish release.'
        if 'quiz' in action:
            return f'{actor} vừa tạo quiz Open edX.'
        return f'{actor} vừa thực hiện {action}.'

    def _relative_time(self, dt: datetime | None) -> str:
        if not dt:
            return ''
        seconds = max(0, int((datetime.utcnow() - dt).total_seconds()))
        if seconds < 60:
            return 'vừa xong'
        minutes = seconds // 60
        if minutes < 60:
            return f'{minutes} phút trước'
        hours = minutes // 60
        if hours < 24:
            return f'{hours} giờ trước'
        days = hours // 24
        return f'{days} ngày trước'

    def get_activity_feed(self, user: Any, *, limit: int = 10) -> dict[str, Any]:
        safe_limit = max(1, min(int(limit or 10), 30))
        cache_key = f"dashboard:activity:{self._scope_hash(user)}:{safe_limit}"
        cached = self._cache_get(cache_key)
        if cached is not None:
            return cached
        rows = self.db.query(AuditLog).order_by(AuditLog.created_at.desc(), AuditLog.id.desc()).limit(200).all()
        items = []
        for row in rows:
            if not self._audit_visible(user, row):
                continue
            drilldown = self._target_drilldown(row.target_type, row.target_id)
            items.append({
                'id': row.id,
                'actor': {'id': row.actor_id, 'name': row.actor_id},
                'action': row.action,
                'message': self._activity_message(row),
                'status': row.status,
                'created_at': _iso(row.created_at),
                'relative_time': self._relative_time(row.created_at),
                'target': {'type': row.target_type, 'id': row.target_id, 'label': row.target_id},
                'drilldown': drilldown,
            })
            if len(items) >= safe_limit:
                break
        payload = {'items': items, 'limit': safe_limit, 'generated_at': datetime.utcnow().isoformat()}
        self._cache_set(cache_key, payload, 30)
        return payload

    def _target_drilldown(self, target_type: str | None, target_id: str | None) -> dict[str, Any] | None:
        if not target_id:
            return None
        t = (target_type or '').lower()
        if t == 'department':
            return self._drilldown(f'/bank/departments/{target_id}/subjects')
        if t == 'subject':
            return self._drilldown(f'/bank/subjects/{target_id}/versions')
        if t in ['subject_version', 'subject_offering']:
            return self._drilldown(f'/bank/subject-versions/{target_id}/chapters')
        if t in ['chapter', 'subject_chapter']:
            return self._drilldown(f'/bank/chapters/{target_id}')
        if t in ['question']:
            return self._drilldown('/bank/search', {'entity': 'questions', 'question_id': target_id})
        if t in ['bank_operation_job', 'job']:
            return self._drilldown('/jobs')
        return None

    def get_analytics(self, user: Any, *, date_range: str = '30d', from_date: str | None = None, to_date: str | None = None) -> dict[str, Any]:
        filters = self._filters(date_range, from_date, to_date)
        scope_hash = self._scope_hash(user)
        cache_key = f"dashboard:analytics:{scope_hash}:{filters['date_range']}:{filters['from_date']}:{filters['to_date']}"
        cached = self._cache_get(cache_key)
        if cached is not None:
            cached['cache'] = {'hit': True, 'ttl_seconds': 60}
            return cached
        chapters, offerings, subjects, departments = self._visible_stats(user)
        total = sum(_safe_int(row.get('total_questions')) for row in chapters.values())
        approved = sum(_safe_int(row.get('approved_count')) for row in chapters.values())
        pending = sum(_safe_int(row.get('pending_review_count')) for row in chapters.values())
        rejected = sum(_safe_int(row.get('rejected_count')) for row in chapters.values())
        draft_error = sum(_safe_int(row.get('draft_error_count')) for row in chapters.values())
        draft = max(0, total - approved - pending - rejected - draft_error)
        in_range_total = int(self._question_query(user, filters, apply_date=True).count() or 0)
        overdue_pending = self._overdue_pending_count(user)
        totals = {'draft': draft, 'pending_review': pending, 'approved': approved, 'rejected': rejected, 'draft_error': draft_error}
        alerts = self.get_alerts(user, filters, limit=12)
        activity = self.get_activity_feed(user, limit=10).get('items', [])
        payload = {
            'scope': self._scope_label(user),
            'filters': {'date_range': filters['date_range'], 'from_date': filters['from_date'], 'to_date': filters['to_date']},
            'kpis': {
                'total_questions': self._kpi('total_questions', 'Tổng câu hỏi', total, delta=in_range_total, drilldown=self._drilldown('/bank/search', {'entity': 'questions'})),
                'pending_review': self._kpi('pending_review', 'Đang chờ duyệt', pending, delta=0, overdue=overdue_pending, drilldown=self._drilldown('/bank/search', {'entity': 'questions', 'status': 'pending_review'})),
                'approved': self._kpi('approved', 'Đã duyệt', approved, percent=(approved * 100 / total) if total else 0, drilldown=self._drilldown('/bank/search', {'entity': 'questions', 'status': 'approved'})),
                'rejected': self._kpi('rejected', 'Bị từ chối', rejected, percent=(rejected * 100 / total) if total else 0, drilldown=self._drilldown('/bank/search', {'entity': 'questions', 'status': 'rejected'})),
            },
            'charts': {
                'question_status': self._status_chart(totals),
                'new_questions_by_day': self._new_questions_line(user, filters),
                'questions_by_subject': self._questions_by_subject(subjects),
                'difficulty_distribution': self._difficulty_chart(chapters),
                'question_type_distribution': self._type_chart(user, filters),
                'term_comparison': self._term_comparison(user, offerings),
            },
            'alerts': alerts,
            'activity_feed': activity,
            'meta': {
                'departments_total': len(departments),
                'subjects_total': len(subjects),
                'subject_versions_total': len(offerings),
                'chapters_total': len(chapters),
            },
            'generated_at': datetime.utcnow().isoformat(),
            'cache': {'hit': False, 'ttl_seconds': 60},
        }
        self._cache_set(cache_key, payload, 60)
        return payload
