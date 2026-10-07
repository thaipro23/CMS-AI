"""Short lived overview cache; PostgreSQL and current RBAC remain authoritative."""
from dataclasses import asdict
from functools import wraps
import hashlib
import inspect
import json
from uuid import uuid4

from sqlalchemy import event
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.json_safe import json_safe_value
from app.core.redis_client import get_redis_client

GENERATION_KEY = 'ai:teacher-overview:v1:generation'
_CHANGED = 'teacher_overview_changed'
_MAX_BYTES = 512 * 1024

# Jobs themselves do not change report data. Including snapshots and summaries
# makes worker commits invalidate pages just as API writes do.
_TABLES = frozenset({
    'academic_campuses', 'academic_terms', 'academic_blocks',
    'academic_subjects', 'academic_subject_deliveries',
    'academic_teachers', 'academic_teacher_assignments',
    'academic_classes', 'academic_class_students', 'academic_students',
    'academic_course_mappings', 'academic_class_course_mappings',
    'openedx_user_mappings', 'academic_student_learning_snapshots',
    'academic_teacher_report_summaries', 'academic_quiz_deadline_overrides',
    'academic_assignment_defense_scores', 'udemy_student_progress',
    'udemy_subject_plans', 'udemy_subject_plan_milestones', 'ai_course_sync_state',
    'academic_teacher_report_snapshots',
})


def _canonical(value):
    if isinstance(value, dict):
        return {str(k): _canonical(v) for k, v in value.items()}
    if isinstance(value, (set, frozenset)):
        return sorted((_canonical(v) for v in value), key=lambda v: json.dumps(v, sort_keys=True))
    if isinstance(value, (tuple, list)):
        return [_canonical(v) for v in value]
    return value


def _generation(client):
    token = client.get(GENERATION_KEY)
    if token:
        return token
    # Never use a fixed default generation: eviction of this key must not make
    # old cached pages reachable again.
    client.set(GENERATION_KEY, uuid4().hex, nx=True)
    return client.get(GENERATION_KEY)


def invalidate_teacher_overview_cache():
    try:
        get_redis_client(cache=True).set(GENERATION_KEY, uuid4().hex)
    except Exception:
        # A cache outage must not fail an already committed business operation.
        # TTL still bounds staleness if invalidation could not reach Redis.
        pass


def cached_teacher_overview(func):
    signature = inspect.signature(func)

    @wraps(func)
    def wrapped(self, user, *args, **kwargs):
        bound = signature.bind(self, user, *args, **kwargs)
        bound.apply_defaults()
        params = {k: v for k, v in bound.arguments.items() if k not in {'self', 'user'}}
        extras = params.pop('kwargs', {})
        params.update(extras)
        supplied_decision = params.pop('_report_access_decision', None)
        ttl = int(settings.teacher_report_cache_ttl_seconds)
        db = getattr(self, 'db', None)
        eligible = (supplied_decision is None and ttl > 0 and params.get('term_id') and params.get('use_cache', True)
                    and not any(params.get(k) for k in (
                        'include_all', 'include_students', 'include_classes', 'teacher_id',
                        'class_id', 'enforce_branch_integrity'))
                    and params.get('allowed_class_ids') is None
                    and not (db is not None and (db.new or db.dirty or db.deleted or db.info.get(_CHANGED))))
        if not eligible:
            return func(self, user, *args, **kwargs)
        # Resolve live database grants before touching the cache. A changed
        # decision yields another key even when the same user keeps their JWT.
        decision = self.access_decision(user)
        client = key = None
        try:
            client = get_redis_client(cache=True)
            generation = _generation(client)
            if generation:
                identity = {'user_id': user.user_id, 'role': user.role,
                            'permissions': user.permissions, 'course_ids': user.course_ids,
                            'decision': asdict(decision), 'params': params}
                digest = hashlib.sha256(json.dumps(_canonical(identity), sort_keys=True,
                                                  ensure_ascii=False).encode()).hexdigest()
                key = f'ai:teacher-overview:v1:{generation}:{digest}'
                raw = client.get(key)
                if raw and len(raw.encode()) <= _MAX_BYTES:
                    report = json.loads(raw)
                    if isinstance(report, dict) and isinstance(report.get('items'), list):
                        report.setdefault('cache', {})['redis_status'] = 'hit'
                        return report
        except Exception:
            client = key = None
        report_kwargs = dict(kwargs)
        if '_report_access_decision' in signature.parameters:
            report_kwargs['_report_access_decision'] = decision
        report = func(self, user, *args, **report_kwargs)
        if client is not None and key is not None:
            try:
                payload = json_safe_value(report)
                payload.setdefault('cache', {})['redis_status'] = 'miss'
                raw = json.dumps(payload, ensure_ascii=False, allow_nan=False)
                if len(raw.encode()) <= _MAX_BYTES:
                    client.set(key, raw, ex=ttl)
                    return payload
            except Exception:
                pass
        return report

    return wrapped


@event.listens_for(Session, 'before_flush')
def _mark_report_changes(session, _flush_context, _instances):
    for obj in session.new | session.dirty | session.deleted:
        if getattr(getattr(obj, '__table__', None), 'name', None) in _TABLES:
            session.info[_CHANGED] = True
            break


@event.listens_for(Session, 'do_orm_execute')
def _mark_statement_changes(state):
    if state.is_update or state.is_delete or state.is_insert:
        table = getattr(state.statement, 'table', None)
        if getattr(table, 'name', None) in _TABLES:
            state.session.info[_CHANGED] = True


@event.listens_for(Session, 'after_commit')
def _invalidate_committed_changes(session):
    if not session.in_nested_transaction() and session.info.pop(_CHANGED, False):
        invalidate_teacher_overview_cache()


@event.listens_for(Session, 'after_soft_rollback')
def _discard_rolled_back_changes(session, previous_transaction):
    if previous_transaction.parent is None:
        session.info.pop(_CHANGED, None)
