from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo
from typing import Any

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.cost import UsageLog
from app.models.question import Question
from app.models.question_bank import Department, QuestionBankVersion, Subject, SubjectChapter, SubjectOffering
from app.services.business_rbac import BusinessRBACService


def _safe_int(value: Any) -> int:
    try:
        return int(value or 0)
    except Exception:
        return 0


def _safe_float(value: Any) -> float:
    try:
        return float(value or 0)
    except Exception:
        return 0.0


class BankCostAnalyticsService:
    """Scope-aware actual token and cost analytics for Bank generation.

    Only persisted model usage is reported. No KPI is inferred from question
    counts when an actual UsageLog does not exist.
    """

    def __init__(self, db: Session):
        self.db = db
        self.biz = BusinessRBACService(db)

    def _filters(self, date_range: str = '30d', from_date: str | None = None, to_date: str | None = None) -> dict[str, Any]:
        vn_tz = ZoneInfo('Asia/Ho_Chi_Minh')
        utc_tz = ZoneInfo('UTC')
        today = datetime.now(vn_tz).date()
        normalized = (date_range or '30d').strip().lower()
        if normalized == 'today':
            start = today
            end = today
        elif normalized == '7d':
            start = today - timedelta(days=6)
            end = today
        elif normalized == 'custom':
            if not from_date or not to_date:
                raise ValueError('Khoảng thời gian tùy chỉnh cần đầy đủ từ ngày và đến ngày.')
            try:
                start = date.fromisoformat(from_date)
                end = date.fromisoformat(to_date)
            except ValueError as exc:
                raise ValueError('Ngày lọc phải có định dạng YYYY-MM-DD.') from exc
            if end < start:
                raise ValueError('Từ ngày không được lớn hơn đến ngày.')
        else:
            normalized = '30d'
            start = today - timedelta(days=29)
            end = today
        days = max(1, (end - start).days + 1)
        start_local = datetime.combine(start, time.min, tzinfo=vn_tz)
        end_local = datetime.combine(end, time.max, tzinfo=vn_tz)
        return {
            'date_range': normalized,
            'from_date': start.isoformat(),
            'to_date': end.isoformat(),
            # UsageLog.created_at is stored as naive UTC; translate the
            # Vietnam-facing calendar range to UTC before querying PostgreSQL.
            'start_dt': start_local.astimezone(utc_tz).replace(tzinfo=None),
            'end_dt': end_local.astimezone(utc_tz).replace(tzinfo=None),
            'days': days,
        }

    def _scope_label(self, user: Any) -> dict[str, str]:
        if self.biz.is_system_admin(user):
            return {'role': 'SYSTEM_ADMIN', 'label': 'Toàn hệ thống', 'scope_type': 'SYSTEM', 'scope_id': '*'}
        assignments = self.biz.active_assignments_for_actor(user)
        if not assignments:
            return {'role': str(getattr(user, 'role', 'viewer')), 'label': 'Chưa được phân quyền Bank', 'scope_type': 'NONE', 'scope_id': ''}
        best = assignments[0]
        return {
            'role': str(best.role_code or ''),
            'label': f'{best.role_code} · {best.scope_type}:{best.scope_id}',
            'scope_type': str(best.scope_type or ''),
            'scope_id': str(best.scope_id or ''),
        }

    def _visible_versions(self, user: Any) -> dict[str, dict[str, Any]]:
        query = (
            self.db.query(QuestionBankVersion, SubjectChapter, SubjectOffering, Subject, Department)
            .join(SubjectChapter, SubjectChapter.id == QuestionBankVersion.chapter_id)
            .outerjoin(SubjectOffering, SubjectOffering.id == QuestionBankVersion.subject_offering_id)
            .join(Subject, Subject.id == QuestionBankVersion.subject_id)
            .outerjoin(Department, Department.id == Subject.department_id)
        )
        if not self.biz.is_system_admin(user):
            chapter_ids = self.biz.accessible_chapter_ids(user) or set()
            if not chapter_ids:
                return {}
            query = query.filter(QuestionBankVersion.chapter_id.in_(chapter_ids))
        result: dict[str, dict[str, Any]] = {}
        for version, chapter, offering, subject, department in query.all():
            result[version.id] = {
                'bank_version_id': version.id,
                'version_code': version.version_code or version.title or 'v1.0',
                'version_status': version.status,
                'chapter_id': chapter.id,
                'chapter_title': chapter.title,
                'chapter_no': chapter.chapter_no,
                'subject_id': subject.id,
                'subject_code': subject.code,
                'subject_name': subject.name,
                'subject_offering_id': offering.id if offering else version.subject_offering_id,
                'subject_offering_code': offering.code if offering else '',
                'term': offering.term if offering else '',
                'department_id': department.id if department else subject.department_id,
                'department_code': department.code if department else '',
                'department_name': department.name if department else '',
            }
        return result

    @staticmethod
    def _course_key(version_id: str) -> str:
        return f'bank:{version_id}'

    def _usage_query(self, version_ids: list[str], start_dt: datetime, end_dt: datetime):
        if not version_ids:
            return self.db.query(UsageLog).filter(False)
        return self.db.query(UsageLog).filter(
            UsageLog.course_id.in_([self._course_key(item) for item in version_ids]),
            UsageLog.created_at >= start_dt,
            UsageLog.created_at <= end_dt,
        )

    def _period_totals(self, version_ids: list[str], start_dt: datetime, end_dt: datetime) -> dict[str, Any]:
        row = self._usage_query(version_ids, start_dt, end_dt).with_entities(
            func.coalesce(func.sum(UsageLog.cost_usd), 0),
            func.coalesce(func.sum(UsageLog.cost_vnd), 0),
            func.coalesce(func.sum(UsageLog.input_tokens), 0),
            func.coalesce(func.sum(UsageLog.cached_input_tokens), 0),
            func.coalesce(func.sum(UsageLog.uncached_input_tokens), 0),
            func.coalesce(func.sum(UsageLog.output_tokens), 0),
            func.count(UsageLog.id),
        ).one()
        return {
            'cost_usd': round(_safe_float(row[0]), 6),
            'cost_vnd': round(_safe_float(row[1]), 0),
            'input_tokens': _safe_int(row[2]),
            'cached_input_tokens': _safe_int(row[3]),
            'uncached_input_tokens': _safe_int(row[4]),
            'output_tokens': _safe_int(row[5]),
            'calls': _safe_int(row[6]),
        }

    def get_analytics(
        self,
        user: Any,
        *,
        date_range: str = '30d',
        from_date: str | None = None,
        to_date: str | None = None,
        q: str = '',
        page: int = 1,
        page_size: int = 20,
        sort_by: str = 'cost_vnd',
        sort_dir: str = 'desc',
    ) -> dict[str, Any]:
        filters = self._filters(date_range, from_date, to_date)
        version_meta = self._visible_versions(user)
        version_ids = list(version_meta.keys())
        totals = self._period_totals(version_ids, filters['start_dt'], filters['end_dt'])

        previous_end = filters['start_dt'] - timedelta(microseconds=1)
        previous_start = previous_end - timedelta(days=filters['days']) + timedelta(microseconds=1)
        previous = self._period_totals(version_ids, previous_start, previous_end)

        grouped_usage = self._usage_query(version_ids, filters['start_dt'], filters['end_dt']).with_entities(
            UsageLog.course_id,
            func.coalesce(func.sum(UsageLog.cost_usd), 0),
            func.coalesce(func.sum(UsageLog.cost_vnd), 0),
            func.coalesce(func.sum(UsageLog.input_tokens), 0),
            func.coalesce(func.sum(UsageLog.cached_input_tokens), 0),
            func.coalesce(func.sum(UsageLog.uncached_input_tokens), 0),
            func.coalesce(func.sum(UsageLog.output_tokens), 0),
            func.count(UsageLog.id),
            func.max(UsageLog.created_at),
        ).group_by(UsageLog.course_id).all()

        # Count AI-created Bank questions by generation provenance, not by
        # material source type. Bank generation preserves the underlying chunk
        # source_type (pdf/docx/html/...), so filtering source_type='bank_material'
        # incorrectly reported 0 even when model calls successfully created rows.
        question_counts = dict(
            self.db.query(Question.bank_version_id, func.count(Question.id))
            .filter(
                Question.bank_version_id.in_(version_ids) if version_ids else False,
                Question.created_at >= filters['start_dt'],
                Question.created_at <= filters['end_dt'],
                Question.model_provider.isnot(None),
                func.lower(func.coalesce(Question.model_provider, '')).notin_(['', 'manual']),
            )
            .group_by(Question.bank_version_id)
            .all()
        ) if version_ids else {}

        rows: list[dict[str, Any]] = []
        for usage_row in grouped_usage:
            course_id = str(usage_row[0] or '')
            version_id = course_id[5:] if course_id.startswith('bank:') else course_id
            meta = version_meta.get(version_id)
            if not meta:
                continue
            generated = _safe_int(question_counts.get(version_id))
            cost_vnd = _safe_float(usage_row[2])
            input_tokens = _safe_int(usage_row[3])
            cached_tokens = _safe_int(usage_row[4])
            output_tokens = _safe_int(usage_row[6])
            row = {
                **meta,
                'cost_usd': round(_safe_float(usage_row[1]), 6),
                'cost_vnd': round(cost_vnd, 0),
                'input_tokens': input_tokens,
                'cached_input_tokens': cached_tokens,
                'uncached_input_tokens': _safe_int(usage_row[5]),
                'output_tokens': output_tokens,
                'total_tokens': input_tokens + output_tokens,
                'calls': _safe_int(usage_row[7]),
                'questions_generated': generated,
                'avg_cost_per_question_vnd': round(cost_vnd / generated, 0) if generated else 0,
                'cache_ratio_percent': round(cached_tokens * 100 / input_tokens, 1) if input_tokens else 0,
                'latest_at': usage_row[8].isoformat() if usage_row[8] else None,
                'href': f"/bank/chapters/{meta['chapter_id']}",
            }
            rows.append(row)

        keyword = (q or '').strip().lower()
        if keyword:
            rows = [row for row in rows if keyword in ' '.join([
                str(row.get('department_code') or ''),
                str(row.get('department_name') or ''),
                str(row.get('subject_code') or ''),
                str(row.get('subject_name') or ''),
                str(row.get('subject_offering_code') or ''),
                str(row.get('chapter_title') or ''),
                str(row.get('version_code') or ''),
            ]).lower()]

        allowed_sort = {
            'cost_vnd', 'cost_usd', 'total_tokens', 'input_tokens', 'cached_input_tokens',
            'output_tokens', 'calls', 'questions_generated', 'avg_cost_per_question_vnd',
            'latest_at', 'subject_code', 'chapter_title',
        }
        sort_key = sort_by if sort_by in allowed_sort else 'cost_vnd'
        reverse = str(sort_dir).lower() != 'asc'
        rows.sort(key=lambda item: (item.get(sort_key) is not None, item.get(sort_key) or 0), reverse=reverse)

        total_rows = len(rows)
        safe_page_size = max(10, min(int(page_size or 20), 100))
        total_pages = (total_rows + safe_page_size - 1) // safe_page_size if total_rows else 0
        safe_page = max(1, min(int(page or 1), total_pages or 1))
        page_items = rows[(safe_page - 1) * safe_page_size:safe_page * safe_page_size]

        daily_rows = self._usage_query(version_ids, filters['start_dt'], filters['end_dt']).with_entities(
            func.date(UsageLog.created_at),
            func.coalesce(func.sum(UsageLog.cost_usd), 0),
            func.coalesce(func.sum(UsageLog.cost_vnd), 0),
            func.coalesce(func.sum(UsageLog.input_tokens), 0),
            func.coalesce(func.sum(UsageLog.cached_input_tokens), 0),
            func.coalesce(func.sum(UsageLog.output_tokens), 0),
            func.count(UsageLog.id),
        ).group_by(func.date(UsageLog.created_at)).all()
        daily_map = {str(row[0]): row for row in daily_rows}
        start_day = date.fromisoformat(filters['from_date'])
        daily = []
        for offset in range(filters['days']):
            current = start_day + timedelta(days=offset)
            row = daily_map.get(current.isoformat())
            input_tokens = _safe_int(row[3]) if row else 0
            output_tokens = _safe_int(row[5]) if row else 0
            daily.append({
                'date': current.isoformat(),
                'label': current.strftime('%d/%m'),
                'cost_usd': round(_safe_float(row[1]), 6) if row else 0,
                'cost_vnd': round(_safe_float(row[2]), 0) if row else 0,
                'input_tokens': input_tokens,
                'cached_input_tokens': _safe_int(row[4]) if row else 0,
                'output_tokens': output_tokens,
                'total_tokens': input_tokens + output_tokens,
                'calls': _safe_int(row[6]) if row else 0,
            })

        model_rows = self._usage_query(version_ids, filters['start_dt'], filters['end_dt']).with_entities(
            UsageLog.model_provider,
            UsageLog.model_name,
            func.coalesce(func.sum(UsageLog.cost_usd), 0),
            func.coalesce(func.sum(UsageLog.cost_vnd), 0),
            func.coalesce(func.sum(UsageLog.input_tokens), 0),
            func.coalesce(func.sum(UsageLog.output_tokens), 0),
            func.count(UsageLog.id),
        ).group_by(UsageLog.model_provider, UsageLog.model_name).order_by(func.sum(UsageLog.cost_usd).desc()).all()
        models = [{
            'provider': row[0] or 'openai',
            'model': row[1] or settings.openai_model,
            'cost_usd': round(_safe_float(row[2]), 6),
            'cost_vnd': round(_safe_float(row[3]), 0),
            'input_tokens': _safe_int(row[4]),
            'output_tokens': _safe_int(row[5]),
            'calls': _safe_int(row[6]),
        } for row in model_rows]

        subject_buckets: dict[str, dict[str, Any]] = {}
        for row in rows:
            key = str(row['subject_id'])
            bucket = subject_buckets.setdefault(key, {
                'subject_id': row['subject_id'],
                'subject_code': row['subject_code'],
                'subject_name': row['subject_name'],
                'cost_usd': 0.0,
                'cost_vnd': 0.0,
                'total_tokens': 0,
                'calls': 0,
                'questions_generated': 0,
            })
            bucket['cost_usd'] += _safe_float(row['cost_usd'])
            bucket['cost_vnd'] += _safe_float(row['cost_vnd'])
            bucket['total_tokens'] += _safe_int(row['total_tokens'])
            bucket['calls'] += _safe_int(row['calls'])
            bucket['questions_generated'] += _safe_int(row['questions_generated'])
        subjects = sorted(subject_buckets.values(), key=lambda item: item['cost_vnd'], reverse=True)[:8]
        for item in subjects:
            item['cost_usd'] = round(item['cost_usd'], 6)
            item['cost_vnd'] = round(item['cost_vnd'], 0)

        total_tokens = totals['input_tokens'] + totals['output_tokens']
        total_questions = sum(_safe_int(value) for value in question_counts.values())
        totals.update({
            'total_tokens': total_tokens,
            'questions_generated': total_questions,
            'avg_cost_per_question_vnd': round(totals['cost_vnd'] / total_questions, 0) if total_questions else 0,
            'cache_ratio_percent': round(totals['cached_input_tokens'] * 100 / totals['input_tokens'], 1) if totals['input_tokens'] else 0,
        })
        previous_total_tokens = previous['input_tokens'] + previous['output_tokens']
        previous.update({'total_tokens': previous_total_tokens})

        def delta_percent(current: float, old: float) -> float | None:
            if old == 0:
                return None if current == 0 else 100.0
            return round((current - old) * 100 / old, 1)

        return {
            'scope': self._scope_label(user),
            'filters': {key: filters[key] for key in ('date_range', 'from_date', 'to_date')},
            'totals': totals,
            'previous': previous,
            'deltas': {
                'cost_percent': delta_percent(totals['cost_vnd'], previous['cost_vnd']),
                'tokens_percent': delta_percent(total_tokens, previous_total_tokens),
                'calls_percent': delta_percent(totals['calls'], previous['calls']),
            },
            'daily': daily,
            'models': models,
            'subjects': subjects,
            'rows': {
                'items': page_items,
                'total': total_rows,
                'page': safe_page,
                'page_size': safe_page_size,
                'total_pages': total_pages,
            },
            'meta': {
                'visible_bank_versions': len(version_ids),
                'usd_to_vnd': settings.usd_to_vnd,
                'data_source': 'ai_usage_log',
                'actual_usage_only': True,
            },
            'generated_at': datetime.now(timezone.utc).isoformat(),
        }
