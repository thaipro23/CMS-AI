from collections import defaultdict
from datetime import datetime
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from app.core.rbac import UserContext, ensure_course_access, require_permission
from app.db.session import get_db
from app.models.cost import UsageLog
from app.models.job import GenerationJob
from app.models.question import Question, QuestionReviewLog
from app.services.cost_control import USD_TO_VND

router = APIRouter()


def _empty_user(user_id: str):
    return {
        'user_id': user_id or 'unknown',
        'generate_jobs': 0,
        'questions_requested': 0,
        'approved': 0,
        'rejected': 0,
        'published': 0,
        'edits': 0,
        'input_tokens': 0,
        'cached_input_tokens': 0,
        'uncached_input_tokens': 0,
        'output_tokens': 0,
        'estimated_cost_usd': 0.0,
        'actual_cost_usd': 0.0,
        'estimate_accuracy_percent': 0.0,
        'cost_usd': 0.0,
        'cost_vnd': 0.0,
        'last_activity': None,
    }


def _touch(row: dict, dt):
    if not dt:
        return
    iso = dt.isoformat() if isinstance(dt, datetime) else str(dt)
    if not row['last_activity'] or iso > row['last_activity']:
        row['last_activity'] = iso


@router.get('/analytics')
def user_analytics(course_id: str | None = None, search: str | None = None, sort_by: str = 'cost_usd', sort_dir: str = 'desc', db: Session = Depends(get_db), user: UserContext = Depends(require_permission('view_user_analytics'))):
    ensure_course_access(user, course_id)
    users: dict[str, dict] = {}

    job_query = db.query(GenerationJob)
    usage_query = db.query(UsageLog)
    question_query = db.query(Question)
    review_query = db.query(QuestionReviewLog).join(Question, QuestionReviewLog.question_id == Question.id)
    if course_id:
        job_query = job_query.filter(GenerationJob.course_id == course_id)
        usage_query = usage_query.filter(UsageLog.course_id == course_id)
        question_query = question_query.filter(Question.course_id == course_id)
        review_query = review_query.filter(Question.course_id == course_id)

    for job in job_query.all():
        uid = job.requested_by or 'unknown'
        row = users.setdefault(uid, _empty_user(uid))
        row['generate_jobs'] += 1
        row['questions_requested'] += job.question_count or 0
        row['estimated_cost_usd'] += job.estimated_raw_cost_usd or 0
        row['actual_cost_usd'] += job.actual_cost_usd or 0
        _touch(row, job.updated_at or job.created_at)

    for usage in usage_query.all():
        uid = usage.user_id or 'unknown'
        row = users.setdefault(uid, _empty_user(uid))
        row['input_tokens'] += usage.input_tokens or 0
        row['cached_input_tokens'] += usage.cached_input_tokens or 0
        row['uncached_input_tokens'] += usage.uncached_input_tokens or max((usage.input_tokens or 0) - (usage.cached_input_tokens or 0), 0)
        row['output_tokens'] += usage.output_tokens or 0
        row['cost_usd'] += usage.cost_usd or 0
        _touch(row, usage.created_at)

    for q in question_query.all():
        uid = q.reviewed_by or 'unknown'
        if q.status in {'approved', 'rejected', 'published'}:
            row = users.setdefault(uid, _empty_user(uid))
            if q.status == 'approved':
                row['approved'] += 1
            elif q.status == 'rejected':
                row['rejected'] += 1
            elif q.status == 'published':
                row['published'] += 1
            _touch(row, q.reviewed_at or q.updated_at)

    for log in review_query.all():
        uid = log.actor or 'unknown'
        row = users.setdefault(uid, _empty_user(uid))
        # QuestionReviewLog stores status transitions, not an `action` column.
        # Older dashboard code expected log.action and crashed on /users.
        # Derive the activity type from old_status/new_status instead so old DB rows
        # and future transition logs are both safe.
        old_status = (getattr(log, 'old_status', '') or '').lower()
        new_status = (getattr(log, 'new_status', '') or '').lower()
        if old_status == 'edited' or new_status == 'edited':
            row['edits'] += 1
        elif new_status == 'approved':
            row['approved'] += 1
        elif new_status == 'rejected':
            row['rejected'] += 1
        elif new_status == 'published':
            row['published'] += 1
        _touch(row, log.created_at)

    rows = list(users.values())
    for row in rows:
        row['estimated_cost_usd'] = round(row['estimated_cost_usd'], 6)
        row['actual_cost_usd'] = round(row['actual_cost_usd'], 6)
        if row['actual_cost_usd'] > 0 and row['estimated_cost_usd'] > 0:
            row['estimate_accuracy_percent'] = round(max(0, 100 - abs(row['actual_cost_usd'] - row['estimated_cost_usd']) / row['actual_cost_usd'] * 100), 2)
        elif row['actual_cost_usd'] == 0 and row['estimated_cost_usd'] == 0:
            row['estimate_accuracy_percent'] = 100.0
        row['cost_usd'] = round(row['cost_usd'], 6)
        row['cost_vnd'] = round(row['cost_usd'] * USD_TO_VND, 0)

    if search:
        needle = search.lower().strip()
        rows = [row for row in rows if needle in row['user_id'].lower()]

    allowed = {'user_id', 'generate_jobs', 'questions_requested', 'approved', 'rejected', 'published', 'edits', 'input_tokens', 'cached_input_tokens', 'uncached_input_tokens', 'output_tokens', 'estimated_cost_usd', 'actual_cost_usd', 'estimate_accuracy_percent', 'cost_usd', 'cost_vnd', 'last_activity'}
    key = sort_by if sort_by in allowed else 'cost_usd'
    reverse = sort_dir != 'asc'
    rows.sort(key=lambda row: (row.get(key) is None, row.get(key)), reverse=reverse)
    return {'course_id': course_id, 'total_users': len(rows), 'users': rows}
