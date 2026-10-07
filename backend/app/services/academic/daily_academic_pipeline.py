from __future__ import annotations

import hashlib
import json
import logging
import threading
from contextlib import contextmanager
from datetime import datetime, timezone, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from celery.schedules import crontab
import redis
from redis.exceptions import RedisError, LockError
from sqlalchemy import and_, func, or_, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.json_safe import json_safe_value
from app.core.rbac import UserContext
from app.db.session import SessionLocal
from app.models.academic import (
    AcademicBulkOperationJob,
    AcademicCampus,
    AcademicClass,
    AcademicClassSyncJob,
    AcademicSubjectDelivery,
    AcademicSyncRun,
    AcademicTeacherReportJob,
    AcademicTerm,
)
from app.services.academic.platform import cms_delivery_predicate
from app.schemas.academic import AcademicAPSyncIn
from app.services.academic.ap_sync import AcademicAPSyncWorkflowService
from app.services.academic.daily_pipeline_state import (
    ACTIVE,
    MAX_STAGE_RETRY_ROUNDS,
    plan_stage_barrier,
    select_global_dispatch_targets,
)
from app.services.academic.job_runtime import (
    class_sync_queued_timeout_seconds,
    reconcile_stale_rows,
)
from app.services.academic.job_identity import (
    CLASS_SYNC_POLICY_VERSION,
    ClassSyncJobBlocked,
    choose_active_class_sync_job,
    class_sync_contract,
    class_sync_idempotency_key,
)
from app.services.academic.scheduled_parent import (
    ContinuationPublishError,
    confirm_parent_continuation,
    create_or_load_scheduled_parent,
    publish_parent_continuation,
    recover_due_parent_continuations,
)


VN_TZ = ZoneInfo('Asia/Ho_Chi_Minh')
DAILY_ROOT_JOB_TYPE = 'academic_daily_pipeline_v2'
DAILY_START_TASK = 'academic_daily_pipeline_start_task'
DAILY_ROOT_TASK = 'academic_daily_pipeline_task'
DAILY_COORDINATOR_QUEUE = 'sync-fast'
DAILY_COORDINATOR_LOCK_SECONDS = 240
DAILY_MAX_RUNTIME_SECONDS = 24 * 60 * 60
log = logging.getLogger(__name__)
DAILY_SNAPSHOT_TASK = 'academic_daily_snapshot_attempt_task'
DAILY_POLICY_VERSION = 'academic-daily/v2'
DAILY_STATE_VERSION = 'academic-daily-state.v2'
DAILY_SCHEDULER_ACTOR = 'academic-daily-scheduler'
REQUIRED_BRANCHES = ('poly', 'ptcd')
DAILY_CONFIRMED_CONTINUATION_STALE_SECONDS = 5 * 60
DAILY_AP_RUNNING_STALE_SECONDS = 65 * 60
DAILY_MAPPING_RUNNING_STALE_SECONDS = 65 * 60
DAILY_SNAPSHOT_RUNNING_STALE_SECONDS = 40 * 60

_DAILY_ROOT_LOCKS_GUARD = threading.Lock()
_DAILY_ROOT_LOCKS: dict[str, list[Any]] = {}


class DailyScopeError(ValueError):
    def __init__(self, code: str, message: str):
        self.code = code
        super().__init__(message)


@contextmanager
def _daily_root_process_lock(root_id: str):
    key = str(root_id)
    with _DAILY_ROOT_LOCKS_GUARD:
        entry = _DAILY_ROOT_LOCKS.get(key)
        if entry is None:
            entry = [threading.Lock(), 0]
            _DAILY_ROOT_LOCKS[key] = entry
        entry[1] += 1
        lock = entry[0]
    lock.acquire()
    try:
        yield
    finally:
        lock.release()
        with _DAILY_ROOT_LOCKS_GUARD:
            entry[1] -= 1
            if entry[1] == 0:
                _DAILY_ROOT_LOCKS.pop(key, None)


def _canonical_hash(payload: dict[str, Any]) -> str:
    encoded = json.dumps(
        payload,
        ensure_ascii=True,
        separators=(',', ':'),
        sort_keys=True,
    ).encode('utf-8')
    return hashlib.sha256(encoded).hexdigest()


def _local_now(value: datetime | None) -> datetime:
    current = value or datetime.now(timezone.utc)
    if current.tzinfo is None:
        current = current.replace(tzinfo=timezone.utc)
    return current.astimezone(VN_TZ)


def _utc_naive(value: datetime) -> datetime:
    return value.astimezone(timezone.utc).replace(tzinfo=None)


def daily_root_key(run_date_vn: str) -> str:
    return f'academic-daily:v2:{str(run_date_vn or "").strip()}'


def _parse_state_time(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        parsed = value
    else:
        try:
            parsed = datetime.fromisoformat(str(value))
        except (TypeError, ValueError):
            return None
    if parsed.tzinfo is not None:
        return parsed.astimezone(timezone.utc).replace(tzinfo=None)
    return parsed


def _try_daily_root_db_lock(db: Session, root_id: str) -> bool:
    bind = db.get_bind()
    if not bind or bind.dialect.name != 'postgresql':
        return True
    return bool(
        db.execute(
            text('SELECT pg_try_advisory_lock(hashtextextended(:key, 0))'),
            {'key': f'academic-daily-root:{root_id}'},
        ).scalar()
    )


def _release_daily_root_db_lock(db: Session, root_id: str) -> bool:
    bind = db.get_bind()
    if not bind or bind.dialect.name != 'postgresql':
        return True
    try:
        # An aborted transaction rejects every query, including advisory unlock.
        # Discard pending work before releasing this session-owned lock.
        db.rollback()
        released = bool(db.execute(
            text('SELECT pg_advisory_unlock(hashtextextended(:key, 0))'),
            {'key': f'academic-daily-root:{root_id}'},
        ).scalar())
        db.commit()
        return released
    except Exception:
        try:
            db.rollback()
        except Exception:
            pass
        return False


def _daily_redis_client():
    return redis.Redis.from_url(settings.redis_url, socket_connect_timeout=1, socket_timeout=1)


@contextmanager
def _daily_coordinator_session():
    """Serialize scheduler, worker, watchdog and operator across all commits.

    The PostgreSQL connection remains pinned until its session advisory lock is
    released. Redis provides a bounded lease shared by all worker processes.
    PostgreSQL remains authoritative if Redis is temporarily unavailable.
    """
    with _daily_root_process_lock('coordinator'):
        db = SessionLocal()
        connection = None
        client = None
        lease = None
        locked = False
        try:
            bind = db.get_bind()
            if bind is not None and bind.dialect.name == 'postgresql':
                connection = bind.connect()
                db.bind = connection
            try:
                client = _daily_redis_client()
                if client is not None:
                    lease = client.lock('ai-server:academic-daily:coordinator',
                                        timeout=DAILY_COORDINATOR_LOCK_SECONDS, blocking=False)
                    if not lease.acquire(blocking=False):
                        lease = None
                        yield db, False
                        return
            except RedisError:
                lease = None
                log.warning('Daily coordinator Redis lease unavailable; using PostgreSQL lock.')
            locked = _try_daily_root_db_lock(db, 'coordinator')
            yield db, locked
        finally:
            if locked:
                released = _release_daily_root_db_lock(db, 'coordinator')
                if not released and connection is not None:
                    # Do not pool a physical connection still owning a session lock.
                    connection.invalidate()
            db.close()
            if connection is not None:
                connection.close()
            if lease is not None:
                try:
                    lease.release()
                except (RedisError, LockError):
                    log.warning('Daily coordinator Redis lease expired or could not be released.')
            if client is not None:
                client.close()


def _cms_classes_for_term(db: Session, *, term_id: str, branch: str):
    normalized_branch = str(branch or '').strip().lower()
    return (
        db.query(AcademicClass)
        .outerjoin(
            AcademicSubjectDelivery,
            and_(
                AcademicSubjectDelivery.subject_id == AcademicClass.subject_id,
                AcademicSubjectDelivery.term_id == AcademicClass.term_id,
                AcademicSubjectDelivery.block_id == AcademicClass.block_id,
                func.lower(AcademicSubjectDelivery.branch) == normalized_branch,
            ),
        )
        .filter(
            AcademicClass.active.is_(True),
            AcademicClass.term_id == str(term_id),
            func.lower(func.coalesce(AcademicClass.branch, normalized_branch))
            == normalized_branch,
            or_(
                AcademicSubjectDelivery.id.is_(None),
                and_(
                    AcademicSubjectDelivery.active.is_(True),
                    cms_delivery_predicate(),
                ),
            ),
        )
    )


def discover_daily_scopes(db: Session) -> list[dict[str, object]]:
    terms = (
        db.query(AcademicTerm)
        .filter(AcademicTerm.active.is_(True))
        .order_by(func.lower(AcademicTerm.branch).asc(), AcademicTerm.id.asc())
        .all()
    )
    scopes: list[dict[str, object]] = []
    for term in terms:
        branch = str(term.branch or '').strip().lower()
        if branch not in REQUIRED_BRANCHES:
            raise DailyScopeError(
                'invalid_branch_scope',
                f'Active term {term.id} has unsupported branch {branch or "empty"}.',
            )
        campuses = (
            db.query(AcademicCampus)
            .filter(
                AcademicCampus.active.is_(True),
                func.lower(AcademicCampus.branch) == branch,
            )
            .order_by(AcademicCampus.campus_code.asc(), AcademicCampus.id.asc())
            .all()
        )
        campus_codes = sorted({
            str(item.campus_code or '').strip().lower()
            for item in campuses
            if str(item.campus_code or '').strip()
        })
        if not campus_codes:
            raise DailyScopeError(
                'active_campus_scope_missing',
                f'Active term {term.id} has no active campus for branch {branch}.',
            )

        classes = (
            _cms_classes_for_term(db, term_id=str(term.id), branch=branch)
            .order_by(AcademicClass.id.asc())
            .all()
        )
        class_to_campus: dict[str, str] = {}
        for item in classes:
            campus = str(item.campus or '').strip().lower()
            if not campus or campus not in campus_codes:
                raise DailyScopeError(
                    'class_campus_outside_scope',
                    f'Active class {item.id} has no active campus in branch {branch}.',
                )
            class_to_campus[str(item.id)] = campus

        scope_payload: dict[str, Any] = {
            'policy_version': DAILY_POLICY_VERSION,
            'scope_key': f'{branch}:{term.id}',
            'term_id': str(term.id),
            'term_name': str(term.term_name or ''),
            'branch': branch,
            'campuses': campus_codes,
            'class_ids': sorted(class_to_campus),
            'subject_ids': sorted({str(item.subject_id) for item in classes}),
            'class_to_campus': {
                key: class_to_campus[key]
                for key in sorted(class_to_campus)
            },
        }
        scopes.append({**scope_payload, 'scope_hash': _canonical_hash(scope_payload)})
    return sorted(scopes, key=lambda item: (str(item['branch']), str(item['term_id'])))


def _scope_parent_values(
    root: AcademicBulkOperationJob,
    scope: dict[str, object],
    *,
    stage_group: str,
) -> dict[str, Any]:
    return {
        'parent_job_id': str(root.id),
        'job_type': f'academic_daily_{stage_group}_scope',
        'status': 'queued',
        'term_id': str(scope['term_id']),
        'branch': str(scope['branch']),
        'campus': None,
        'requested_by': DAILY_SCHEDULER_ACTOR,
        'progress_current': 0,
        'progress_total': 100,
        'progress_label': f'01:00 +07 · chờ giai đoạn {stage_group}',
        'request_json': json_safe_value({
            'scheduled': True,
            'daily_root_job_id': str(root.id),
            'stage_group': stage_group,
            'scope_hash': scope.get('scope_hash'),
            'frozen_scope': scope,
            'scope': scope,
        }),
        'result_json': {},
    }


def ensure_scope_parents(
    db: Session,
    root: AcademicBulkOperationJob,
    scopes: list[dict[str, object]],
) -> dict[str, AcademicBulkOperationJob]:
    request = root.request_json if isinstance(root.request_json, dict) else {}
    run_date_vn = str(request.get('run_date_vn') or '').strip()
    parents: dict[str, AcademicBulkOperationJob] = {}
    for scope in scopes:
        term_id = str(scope['term_id'])
        branch = str(scope['branch'])
        for stage_group in ('provision', 'score-report'):
            key = ':'.join((
                daily_root_key(run_date_vn),
                term_id,
                branch,
                stage_group,
            ))
            parent, _created = create_or_load_scheduled_parent(
                db,
                idempotency_key=key,
                values=_scope_parent_values(
                    root,
                    scope,
                    stage_group=stage_group,
                ),
            )
            parents[f'{scope["scope_key"]}:{stage_group}'] = parent
    return parents


_ROOT_PHASE_PROGRESS: dict[str, tuple[int, str]] = {
    'ap_sync': (5, '01:00 +07 · đang đồng bộ AP'),
    'course_mapping': (15, '01:00 +07 · đang ghép Course CMS'),
    'account_enrollment': (35, '01:00 +07 · đang tạo tài khoản và ghi danh'),
    'score_update': (60, '01:00 +07 · đang cập nhật điểm toàn bộ'),
    'campus_snapshots': (75, '01:00 +07 · đang chốt snapshot từng cơ sở'),
    'campus_reports': (82, '01:00 +07 · đang tạo Excel từng cơ sở'),
    'ho_snapshots': (90, '01:00 +07 · đang chốt snapshot HO'),
    'ho_reports': (95, '01:00 +07 · đang tổng hợp báo cáo HO'),
    'completed': (100, '01:00 +07 · hoàn tất đồng bộ và báo cáo'),
}


def _sync_scope_parent_states(
    db: Session,
    root: AcademicBulkOperationJob,
    state: dict[str, Any],
    *,
    now: datetime | None = None,
) -> None:
    current_time = now or datetime.utcnow()
    phase = str(state.get('phase') or 'ap_sync')
    rows = db.query(AcademicBulkOperationJob).filter(
        AcademicBulkOperationJob.parent_job_id == str(root.id),
        AcademicBulkOperationJob.job_type.in_([
            'academic_daily_provision_scope',
            'academic_daily_score-report_scope',
        ]),
    ).all()

    provision_running = {
        'course_mapping': (15, '01:00 +07 · đang ghép Course CMS'),
        'account_enrollment': (55, '01:00 +07 · đang tạo tài khoản và ghi danh'),
    }
    score_running = {
        'score_update': (45, '01:00 +07 · đang cập nhật điểm toàn bộ'),
        'campus_snapshots': (70, '01:00 +07 · đang chốt snapshot cơ sở'),
        'campus_reports': (82, '01:00 +07 · đang tạo Excel cơ sở'),
        'ho_snapshots': (90, '01:00 +07 · đang chốt snapshot HO'),
        'ho_reports': (95, '01:00 +07 · đang tổng hợp Excel HO'),
    }

    for parent in rows:
        if parent.status in {'completed', 'failed', 'cancelled', 'canceled'}:
            continue

        if root.status == 'failed' or phase == 'failed':
            parent.result_json = json_safe_value({**dict(parent.result_json or {}),
                'root_failure_code': state.get('code'), 'daily_root_job_id': str(root.id)})
            parent.status = 'failed'
            parent.progress_current = 100
            parent.progress_total = 100
            parent.progress_label = (
                f'01:00 +07 · dừng theo pipeline ({state.get("failed_stage") or phase})'
            )[:255]
            parent.error_message = str(root.error_message or 'Daily pipeline stopped.')[:4000]
            parent.finished_at = parent.finished_at or current_time
        elif root.status == 'completed' or phase == 'completed':
            parent.status = 'completed'
            parent.progress_current = 100
            parent.progress_total = 100
            parent.progress_label = '01:00 +07 · hoàn tất'
            parent.error_message = None
            parent.started_at = parent.started_at or root.started_at or current_time
            parent.finished_at = parent.finished_at or current_time
        elif parent.job_type == 'academic_daily_provision_scope':
            if phase in provision_running:
                progress, label = provision_running[phase]
                parent.status = 'running'
                parent.progress_current = progress
                parent.progress_total = 100
                parent.progress_label = label
                parent.error_message = None
                parent.started_at = parent.started_at or current_time
            elif phase in {
                'score_update',
                'campus_snapshots',
                'campus_reports',
                'ho_snapshots',
                'ho_reports',
            }:
                parent.status = 'completed'
                parent.progress_current = 100
                parent.progress_total = 100
                parent.progress_label = '01:00 +07 · hoàn tất tạo tài khoản và ghi danh'
                parent.error_message = None
                parent.started_at = parent.started_at or root.started_at or current_time
                parent.finished_at = parent.finished_at or current_time
        elif phase in score_running:
            progress, label = score_running[phase]
            parent.status = 'running'
            parent.progress_current = progress
            parent.progress_total = 100
            parent.progress_label = label
            parent.error_message = None
            parent.started_at = parent.started_at or current_time

        parent.updated_at = current_time
        db.add(parent)


def _cancel_queued_root_attempts(
    db: Session,
    root: AcademicBulkOperationJob,
    state: dict[str, Any],
    *,
    now: datetime,
) -> int:
    model_by_stage = {
        'ap_sync': AcademicSyncRun,
        'course_mapping': AcademicBulkOperationJob,
        'account_enrollment': AcademicClassSyncJob,
        'score_update': AcademicClassSyncJob,
        'campus_snapshots': AcademicBulkOperationJob,
        'campus_reports': AcademicTeacherReportJob,
        'ho_snapshots': AcademicBulkOperationJob,
        'ho_reports': AcademicTeacherReportJob,
    }
    cancelled = 0
    seen_ids: set[tuple[type, str]] = set()
    attempts_by_stage = (
        state.get('attempts_by_stage')
        if isinstance(state.get('attempts_by_stage'), dict)
        else {}
    )
    for stage, rounds in attempts_by_stage.items():
        model = model_by_stage.get(str(stage))
        if model is None or not isinstance(rounds, dict):
            continue
        for attempts in rounds.values():
            if not isinstance(attempts, dict):
                continue
            for attempt_id in attempts.values():
                key = (model, str(attempt_id or ''))
                if not key[1] or key in seen_ids:
                    continue
                seen_ids.add(key)
                row = db.get(model, key[1])
                if row is None or str(getattr(row, 'status', '') or '').lower() != 'queued':
                    continue
                row.status = 'cancelled'
                if hasattr(row, 'error_message'):
                    row.error_message = (
                        f'Daily pipeline root {root.id} was superseded before this task started.'
                    )[:4000]
                if hasattr(row, 'progress_current'):
                    row.progress_current = 100
                if hasattr(row, 'progress_total'):
                    row.progress_total = 100
                if hasattr(row, 'progress_label'):
                    row.progress_label = 'Đã hủy vì pipeline ngày mới đã thay thế'
                if hasattr(row, 'finished_at'):
                    row.finished_at = now
                if hasattr(row, 'updated_at'):
                    row.updated_at = now
                if hasattr(row, 'result_json'):
                    payload = dict(getattr(row, 'result_json', None) or {})
                    payload.update({
                        'ok': False,
                        'code': 'superseded_by_newer_daily_run',
                        'superseded_root_id': str(root.id),
                    })
                    row.result_json = json_safe_value(payload)
                elif hasattr(row, 'counters_json'):
                    payload = dict(getattr(row, 'counters_json', None) or {})
                    payload['error'] = {
                        'code': 'superseded_by_newer_daily_run',
                        'message': 'Daily AP attempt cancelled before worker start.',
                        'retryable': False,
                    }
                    row.counters_json = json_safe_value(payload)
                db.add(row)
                cancelled += 1
    return cancelled


def _mark_older_active_roots_superseded(
    db: Session,
    *,
    keep_root_id: str | None = None,
    now: datetime | None = None,
) -> int:
    current_time = now or datetime.utcnow()
    active = db.query(AcademicBulkOperationJob).filter(
        AcademicBulkOperationJob.job_type == DAILY_ROOT_JOB_TYPE,
        AcademicBulkOperationJob.status.in_(['queued', 'running']),
    ).all()
    if len(active) <= 1:
        return 0

    if keep_root_id:
        keep = next((item for item in active if str(item.id) == str(keep_root_id)), None)
    else:
        keep = None
    if keep is None:
        keep = max(
            active,
            key=lambda item: (
                str((item.request_json or {}).get('run_date_vn') or ''),
                item.created_at or datetime.min,
            ),
        )

    changed = 0
    for root in active:
        if str(root.id) == str(keep.id):
            continue
        state = dict(root.result_json or {})
        continuation = (
            dict(state.get('continuation') or {})
            if isinstance(state.get('continuation'), dict)
            else {}
        )
        continuation.update({
            'status': 'failed',
            'failed_at': current_time.isoformat(),
            'last_error': 'Superseded by a newer daily pipeline root.',
        })
        cancelled_attempts = _cancel_queued_root_attempts(
            db,
            root,
            state,
            now=current_time,
        )
        state.update({
            'continuation': continuation,
            'code': 'superseded_by_newer_daily_run',
            'superseded_by_root_id': str(keep.id),
            'superseded_at': current_time.isoformat(),
            'cancelled_queued_attempt_count': cancelled_attempts,
        })
        root.status = 'failed'
        root.progress_current = 100
        root.progress_total = 100
        root.progress_label = '01:00 +07 · dừng vì đã có pipeline ngày mới hơn'
        root.error_message = (
            f'Daily pipeline superseded by newer root {keep.id}.'
        )[:4000]
        root.finished_at = root.finished_at or current_time
        root.updated_at = current_time
        _sync_scope_parent_states(db, root, state, now=current_time)
        root.result_json = json_safe_value(state)
        db.add(root)
        changed += 1
    if changed:
        db.commit()
    return changed


def _root_request(run_date_vn: str, scopes: list[dict[str, object]]) -> dict[str, Any]:
    return {
        'scheduled': True,
        'schedule_time': '01:00',
        'timezone': 'Asia/Ho_Chi_Minh',
        'run_date_vn': run_date_vn,
        'policy_version': DAILY_POLICY_VERSION,
        'required_branches': list(REQUIRED_BRANCHES),
        'scopes': scopes,
    }


def _root_state(scopes: list[dict[str, object]]) -> dict[str, Any]:
    return {
        'schema_version': DAILY_STATE_VERSION,
        'phase': 'ap_sync',
        'stage_round': 0,
        'stage_target_keys': [str(scope['scope_key']) for scope in scopes],
        'attempts_by_stage': {},
        'artifacts': {},
    }


def _continuation_publisher(celery_app):
    def publish(*, task_name: str, args: list[Any], queue: str, countdown: int):
        return celery_app.send_task(
            task_name,
            args=args,
            queue=queue,
            countdown=countdown,
        )

    return publish


def recover_daily_academic_pipeline(
    celery_app,
    *,
    now: datetime | None = None,
) -> dict[str, object]:
    """Recover durable root continuation intent and stale confirmed deliveries."""
    current_time = now or datetime.utcnow()
    with _daily_coordinator_session() as (db, acquired):
        if not acquired:
            return {'ok': True, 'status': 'coordinator_busy', 'scanned': 0,
                    'republished': 0, 'failed': 0, 'errors': []}
        unfinished_scope_root_ids = db.query(AcademicBulkOperationJob.parent_job_id).filter(
            AcademicBulkOperationJob.job_type.in_(
                ['academic_daily_provision_scope', 'academic_daily_score-report_scope']),
            AcademicBulkOperationJob.status.in_(['queued', 'running']),
        )
        failed_roots = db.query(AcademicBulkOperationJob).filter(
            AcademicBulkOperationJob.job_type == DAILY_ROOT_JOB_TYPE,
            AcademicBulkOperationJob.status == 'failed',
            AcademicBulkOperationJob.id.in_(unfinished_scope_root_ids),
        ).all()
        for failed_root in failed_roots:
            _sync_scope_parent_states(db, failed_root, dict(failed_root.result_json or {}), now=current_time)
        db.commit()
        superseded = _mark_older_active_roots_superseded(
            db,
            now=current_time,
        )
        roots = db.query(AcademicBulkOperationJob).filter(
            AcademicBulkOperationJob.job_type == DAILY_ROOT_JOB_TYPE,
            AcademicBulkOperationJob.status.in_(['queued', 'running']),
        ).all()
        stale_confirmed = 0
        for root in roots:
            state = dict(root.result_json or {})
            continuation = (
                dict(state.get('continuation') or {})
                if isinstance(state.get('continuation'), dict)
                else {}
            )
            status = str(continuation.get('status') or '')
            if status == 'confirmed':
                confirmed_at = (
                    _parse_state_time(continuation.get('confirmed_at'))
                    or _parse_state_time(root.updated_at)
                    or _parse_state_time(root.created_at)
                )
                age_seconds = (
                    (current_time - confirmed_at).total_seconds()
                    if confirmed_at is not None
                    else DAILY_CONFIRMED_CONTINUATION_STALE_SECONDS + 1
                )
                if age_seconds <= DAILY_CONFIRMED_CONTINUATION_STALE_SECONDS:
                    continue
                continuation.update({
                    'status': 'dispatch_pending',
                    'due_at': current_time.isoformat(),
                    'last_error': (
                        'Confirmed coordinator delivery became stale before '
                        'publishing the next continuation.'
                    ),
                    'last_error_class': 'StaleConfirmedContinuation',
                    'last_error_at': current_time.isoformat(),
                })
                stale_confirmed += 1
            elif status not in {'dispatch_pending', 'dispatched'}:
                continuation = {
                    'status': 'dispatch_pending',
                    'attempt_count': 0,
                    'due_at': current_time.isoformat(),
                    'task_name': DAILY_ROOT_TASK,
                    'args': [str(root.id)],
                    'queue': 'sync-bulk',
                    'countdown': 15,
                    'intent_created_at': current_time.isoformat(),
                }
            elif not continuation.get('due_at'):
                continuation['due_at'] = current_time.isoformat()

            continuation['queue'] = DAILY_COORDINATOR_QUEUE
            continuation['confirmation_timeout_seconds'] = class_sync_queued_timeout_seconds()
            if status == 'dispatched':
                dispatched_at = _parse_state_time(continuation.get('dispatched_at'))
                if dispatched_at is not None:
                    continuation['due_at'] = (dispatched_at + timedelta(
                        seconds=int(continuation.get('countdown') or 0)
                        + class_sync_queued_timeout_seconds())).isoformat()
            state['continuation'] = continuation
            root.result_json = json_safe_value(state)
            root.updated_at = current_time
            db.add(root)
        db.commit()

        result = recover_due_parent_continuations(
            db,
            publisher=_continuation_publisher(celery_app),
            job_types={DAILY_ROOT_JOB_TYPE},
            now=current_time,
            max_attempts=5,
            max_runtime_seconds=DAILY_MAX_RUNTIME_SECONDS,
            runtime_failure_code='pipeline_runtime_exceeded',
        )
        for root in roots:
            if root.status == 'failed':
                _sync_scope_parent_states(db, root, dict(root.result_json or {}), now=current_time)
        db.commit()
        return {
            'scanned': int(result.get('scanned') or 0),
            'republished': int(result.get('republished') or 0),
            'failed': int(result.get('failed') or 0),
            'superseded': superseded,
            'stale_confirmed': stale_confirmed,
            'errors': list(result.get('errors') or []),
        }

def _scheduler_user() -> UserContext:
    return UserContext(
        user_id=DAILY_SCHEDULER_ACTOR,
        username=DAILY_SCHEDULER_ACTOR,
        email=None,
        role='admin',
        permissions=set(),
        course_ids=None,
        raw_claims={
            'ai_system_admin': True,
            'source': DAILY_POLICY_VERSION,
        },
    )


def _scheduler_requester_context() -> dict[str, Any]:
    return {
        'user_id': DAILY_SCHEDULER_ACTOR,
        'username': DAILY_SCHEDULER_ACTOR,
        'email': None,
        'role': 'admin',
        'permissions': [],
        'course_ids': None,
        'authenticated_admin_claims': {'ai_system_admin': True},
    }


def _scope_by_key(root: AcademicBulkOperationJob) -> dict[str, dict[str, Any]]:
    request = root.request_json if isinstance(root.request_json, dict) else {}
    return {
        str(scope.get('scope_key')): dict(scope)
        for scope in (request.get('scopes') or [])
        if isinstance(scope, dict) and scope.get('scope_key')
    }


def _attempt_key(
    root: AcademicBulkOperationJob,
    scope: dict[str, Any],
    *,
    stage: str,
    round_no: int,
) -> str:
    request = root.request_json if isinstance(root.request_json, dict) else {}
    return ':'.join((
        daily_root_key(str(request.get('run_date_vn') or '')),
        str(scope['term_id']),
        str(scope['branch']),
        stage,
        'attempt',
        str(max(0, int(round_no))),
    ))


def enqueue_ap_stage_attempt(
    db: Session,
    root: AcademicBulkOperationJob,
    scope: dict[str, object],
    round_no: int,
) -> AcademicSyncRun:
    scope_data = dict(scope)
    attempt_key = _attempt_key(
        root,
        scope_data,
        stage='ap',
        round_no=round_no,
    )
    metadata = {
        'root_job_id': str(root.id),
        'scope_key': str(scope_data['scope_key']),
        'logical_target_key': f'ap_sync:{scope_data["scope_key"]}',
        'stage': 'ap_sync',
        'round': max(0, int(round_no)),
    }
    result = AcademicAPSyncWorkflowService(db).enqueue_sync_from_ap_job(
        AcademicAPSyncIn(
            term_name=str(scope_data['term_name']),
            sync_scope='all',
            campuses=[str(value) for value in scope_data.get('campuses') or []],
            branch=str(scope_data['branch']),
            subject_codes=[],
            max_subjects=0,
            dry_run=False,
        ),
        user=_scheduler_user(),
        idempotency_key=attempt_key,
        run_metadata=metadata,
    )
    run = result['sync_run']
    if str(run.idempotency_key or '') == attempt_key:
        counters = dict(run.counters_json or {})
        counters['daily_pipeline'] = {
            **metadata,
            'source_run_id': str(run.id),
        }
        run.counters_json = json_safe_value(counters)
        db.add(run)
        db.commit()
        db.refresh(run)
    return run


def _reconcile_ap_runs(db: Session, runs: list[AcademicSyncRun]) -> None:
    now = datetime.utcnow()
    queued_timeout = class_sync_queued_timeout_seconds()
    changed = False
    for run in runs:
        if run is None or str(run.status or '').lower() not in ACTIVE:
            continue
        counters = dict(run.counters_json or {})
        progress = (
            dict(counters.get('progress') or {})
            if isinstance(counters.get('progress'), dict)
            else {}
        )
        reference = (
            _parse_state_time(progress.get('updated_at'))
            or _parse_state_time(run.started_at)
            or _parse_state_time(run.created_at)
        )
        if reference is None:
            continue
        timeout = (
            queued_timeout
            if str(run.status or '').lower() == 'queued' and run.started_at is None
            else DAILY_AP_RUNNING_STALE_SECONDS
        )
        if (now - reference).total_seconds() <= timeout:
            continue

        run.status = 'failed'
        run.error_message = (
            'AP sync worker không còn cập nhật tiến độ trong thời gian cho phép; '
            'pipeline sẽ retry bằng attempt mới.'
        )[:4000]
        run.finished_at = now
        counters['error'] = {
            'code': 'CELERY_JOB_ORPHANED',
            'message': run.error_message,
            'retryable': True,
        }
        counters['progress'] = {
            **progress,
            'label': 'Đồng bộ AP bị gián đoạn do worker',
            'updated_at': now.isoformat(),
        }
        run.counters_json = json_safe_value(counters)
        db.add(run)
        changed = True
    if changed:
        db.commit()


def _refresh_scope_after_ap(
    db: Session,
    scope: dict[str, Any],
) -> dict[str, Any]:
    branch = str(scope['branch'])
    campus_codes = sorted({
        str(value).strip().lower()
        for value in scope.get('campuses') or []
        if str(value).strip()
    })
    classes = (
        _cms_classes_for_term(
            db,
            term_id=str(scope['term_id']),
            branch=branch,
        )
        .order_by(AcademicClass.id.asc())
        .all()
    )
    class_to_campus: dict[str, str] = {}
    for item in classes:
        campus = str(item.campus or '').strip().lower()
        if not campus or campus not in campus_codes:
            raise DailyScopeError(
                'class_campus_outside_scope',
                f'Active class {item.id} has no frozen campus in branch {branch}.',
            )
        class_to_campus[str(item.id)] = campus
    refreshed = {
        key: value
        for key, value in scope.items()
        if key not in {'scope_hash', 'class_ids', 'subject_ids', 'class_to_campus'}
    }
    refreshed.update({
        'class_ids': sorted(class_to_campus),
        'subject_ids': sorted({str(item.subject_id) for item in classes}),
        'class_to_campus': {
            key: class_to_campus[key]
            for key in sorted(class_to_campus)
        },
    })
    return {**refreshed, 'scope_hash': _canonical_hash(refreshed)}


def ensure_mapping_attempt(
    db: Session,
    root: AcademicBulkOperationJob,
    scope: dict[str, object],
    round_no: int,
) -> AcademicBulkOperationJob:
    scope_data = dict(scope)
    parents = ensure_scope_parents(db, root, [scope_data])
    scope_parent = parents[f'{scope_data["scope_key"]}:provision']
    parent_request = dict(scope_parent.request_json or {})
    parent_request.update({
        'scope_hash': scope_data['scope_hash'],
        'frozen_scope': scope_data,
        'scope': scope_data,
    })
    scope_parent.request_json = json_safe_value(parent_request)
    db.add(scope_parent)
    db.commit()

    class_ids = [str(value) for value in scope_data.get('class_ids') or []]
    subject_ids = [
        str(value)
        for value in scope_data.get('subject_ids') or []
        if value
    ]
    if not subject_ids and class_ids:
        subject_ids = [
            str(value)
            for (value,) in db.query(AcademicClass.subject_id).filter(
                AcademicClass.id.in_(class_ids),
            ).distinct().all()
            if value
        ]
    key = _attempt_key(
        root,
        scope_data,
        stage='mapping',
        round_no=round_no,
    )
    job, _created = create_or_load_scheduled_parent(
        db,
        idempotency_key=key,
        values={
            'parent_job_id': str(scope_parent.id),
            'job_type': 'subject_auto_map_all_sync',
            'status': 'queued',
            'term_id': str(scope_data['term_id']),
            'branch': str(scope_data['branch']),
            'campus': None,
            'requested_by': DAILY_SCHEDULER_ACTOR,
            'progress_current': 0,
            'progress_total': 100,
            'progress_label': '01:00 +07 · chờ ghép Course CMS còn thiếu',
            'request_json': json_safe_value({
                'operation': 'map_only',
                'scheduled': True,
                'daily_root_job_id': str(root.id),
                'scheduled_parent_job_id': str(scope_parent.id),
                'scheduled_scope_hash': scope_data['scope_hash'],
                'scheduled_scope_contract': {
                    'scope_hash': scope_data['scope_hash'],
                    'scope_key': scope_data['scope_key'],
                    'round': max(0, int(round_no)),
                },
                'frozen_scope': scope_data,
                'approved_class_ids': class_ids,
                'approved_subject_ids': subject_ids,
                'term_id': str(scope_data['term_id']),
                'branch': str(scope_data['branch']),
                'requester_context': _scheduler_requester_context(),
                'logical_target_key': f'course_mapping:{scope_data["scope_key"]}',
                'attempt_no': max(0, int(round_no)),
            }),
            'result_json': {},
        },
    )
    return job


def _lock_class_attempt(db: Session, class_id: str) -> None:
    bind = db.get_bind()
    if bind and bind.dialect.name == 'postgresql':
        db.execute(
            text('SELECT pg_advisory_xact_lock(hashtext(:key))'),
            {'key': f'academic-daily-class:{class_id}'},
        )


def ensure_class_attempt_job(
    db: Session,
    *,
    scope_parent: AcademicBulkOperationJob,
    class_id: str,
    stage: str,
    round_no: int,
    request: dict[str, Any],
) -> AcademicClassSyncJob:
    if stage not in {'account_enrollment', 'score_update'}:
        raise ValueError(f'Unsupported daily class stage: {stage}')
    _lock_class_attempt(db, class_id)
    job_type = 'full_cms_sync' if stage == 'account_enrollment' else 'learning_sync'
    logical_target_key = str(request.get('logical_target_key') or '').strip()
    contract = class_sync_contract(
        class_id=class_id,
        job_type=job_type,
        force=bool(request.get('force', False)),
        limit=int(request.get('limit') or 5000),
        mode=request.get('mode'),
        auto_map_course=request.get('auto_map_course'),
        sync_learning=request.get('sync_learning'),
        parent_job_id=str(scope_parent.id),
        origin='scheduled',
        policy_version=CLASS_SYNC_POLICY_VERSION,
        attempt_no=round_no,
        logical_target_key=logical_target_key,
    )
    idempotency_key = class_sync_idempotency_key(**contract)
    existing = db.query(AcademicClassSyncJob).filter(
        AcademicClassSyncJob.idempotency_key == idempotency_key,
    ).one_or_none()
    if existing is not None:
        return existing

    active_jobs = (
        db.query(AcademicClassSyncJob)
        .filter(
            AcademicClassSyncJob.class_id == str(class_id),
            AcademicClassSyncJob.status.in_(['queued', 'running']),
        )
        .order_by(AcademicClassSyncJob.created_at.desc())
        .all()
    )
    stale_blockers = reconcile_stale_rows(
        active_jobs,
        now=datetime.utcnow(),
        queued_timeout_seconds=class_sync_queued_timeout_seconds(),
        running_timeout_seconds=int(settings.academic_class_sync_stale_seconds),
    )
    if stale_blockers:
        db.add_all(stale_blockers)
        db.commit()
        active_jobs = (
            db.query(AcademicClassSyncJob)
            .filter(
                AcademicClassSyncJob.class_id == str(class_id),
                AcademicClassSyncJob.status.in_(['queued', 'running']),
            )
            .order_by(AcademicClassSyncJob.created_at.desc())
            .all()
        )
    decision = choose_active_class_sync_job(
        active_jobs,
        requested_key=idempotency_key,
    )
    if decision.blocker is not None:
        raise ClassSyncJobBlocked(decision.blocker)
    if decision.reusable is not None:
        return decision.reusable

    job = AcademicClassSyncJob(
        job_type=job_type,
        status='queued',
        class_id=str(class_id),
        parent_job_id=str(scope_parent.id),
        idempotency_key=idempotency_key,
        requested_by=DAILY_SCHEDULER_ACTOR,
        force=bool(request.get('force', False)),
        limit=max(1, int(request.get('limit') or 5000)),
        mode=request.get('mode'),
        progress_current=0,
        progress_total=100,
        progress_label=(
            '01:00 +07 · chờ tạo tài khoản và ghi danh'
            if stage == 'account_enrollment'
            else '01:00 +07 · chờ cập nhật điểm'
        ),
        request_json=json_safe_value({
            **request,
            'request_key': idempotency_key,
            'request_contract': contract,
            'policy_version': CLASS_SYNC_POLICY_VERSION,
            'parent_job_id': str(scope_parent.id),
            'parent_job_type': scope_parent.job_type,
            'approved_class_id': str(class_id),
        }),
        result_json={},
    )
    db.add(job)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        existing = db.query(AcademicClassSyncJob).filter(
            AcademicClassSyncJob.idempotency_key == idempotency_key,
        ).one_or_none()
        if existing is None:
            raise
        return existing
    db.refresh(job)
    return job


def _stage_attempts(
    state: dict[str, Any],
    stage: str,
    round_no: int,
) -> dict[str, str]:
    attempts_by_stage = dict(state.get('attempts_by_stage') or {})
    stage_attempts = dict(attempts_by_stage.get(stage) or {})
    return {
        str(key): str(value)
        for key, value in dict(stage_attempts.get(str(round_no)) or {}).items()
        if key and value
    }


def _set_stage_attempts(
    state: dict[str, Any],
    stage: str,
    round_no: int,
    attempts: dict[str, str],
) -> None:
    attempts_by_stage = dict(state.get('attempts_by_stage') or {})
    stage_attempts = dict(attempts_by_stage.get(stage) or {})
    stage_attempts[str(round_no)] = dict(attempts)
    attempts_by_stage[stage] = stage_attempts
    state['attempts_by_stage'] = attempts_by_stage


def _run_date(root: AcademicBulkOperationJob) -> str:
    request = root.request_json if isinstance(root.request_json, dict) else {}
    return str(request.get('run_date_vn') or '').strip()


def _scope_parent(
    db: Session,
    root: AcademicBulkOperationJob,
    scope: dict[str, Any],
) -> AcademicBulkOperationJob:
    parents = ensure_scope_parents(db, root, [scope])
    return parents[f'{scope["scope_key"]}:score-report']


def ensure_snapshot_attempt(
    db: Session,
    *,
    root: AcademicBulkOperationJob,
    scope: dict[str, Any],
    snapshot_type: str,
    round_no: int,
) -> AcademicBulkOperationJob:
    if snapshot_type not in {'campus_set', 'ho'}:
        raise ValueError(f'Unsupported snapshot type: {snapshot_type}')
    stage = 'campus_snapshots' if snapshot_type == 'campus_set' else 'ho_snapshots'
    snapshot_key = 'campus-snapshot' if snapshot_type == 'campus_set' else 'ho-snapshot'
    key = (
        f'academic-daily:v2:{_run_date(root)}:{scope["term_id"]}:'
        f'{scope["branch"]}:{snapshot_key}:attempt:{max(0, int(round_no))}'
    )
    existing = db.query(AcademicBulkOperationJob).filter(
        AcademicBulkOperationJob.idempotency_key == key,
    ).one_or_none()
    if existing is not None:
        return existing
    scope_parent = _scope_parent(db, root, scope)
    job = AcademicBulkOperationJob(
        parent_job_id=str(root.id),
        idempotency_key=key,
        job_type='daily_report_snapshot_attempt',
        status='queued',
        term_id=str(scope['term_id']),
        branch=str(scope['branch']),
        campus=None,
        requested_by=DAILY_SCHEDULER_ACTOR,
        progress_current=0,
        progress_total=100,
        progress_label='01:00 +07 · chờ chốt snapshot báo cáo',
        request_json=json_safe_value({
            'scheduled': True,
            'daily_root_job_id': str(root.id),
            'scope_parent_id': str(scope_parent.id),
            'daily_stage': stage,
            'logical_target_key': str(scope['scope_key']),
            'attempt_no': max(0, int(round_no)),
            'snapshot_type': snapshot_type,
            'scope': scope,
        }),
        result_json=json_safe_value({'dispatch': {'state': 'pending'}}),
    )
    db.add(job)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        existing = db.query(AcademicBulkOperationJob).filter(
            AcademicBulkOperationJob.idempotency_key == key,
        ).one_or_none()
        if existing is None:
            raise
        return existing
    db.refresh(job)
    return job


def ensure_report_attempt(
    db: Session,
    *,
    root: AcademicBulkOperationJob,
    scope: dict[str, Any],
    campus: str | None,
    stage: str,
    round_no: int,
    snapshot_id: str,
) -> AcademicTeacherReportJob:
    if stage not in {'campus_reports', 'ho_reports'}:
        raise ValueError(f'Unsupported report stage: {stage}')
    target_name = f'campus:{campus}' if campus else 'ho'
    key = (
        f'academic-daily:v2:{_run_date(root)}:{scope["term_id"]}:'
        f'{scope["branch"]}:{target_name}:attempt:{max(0, int(round_no))}'
    )
    existing = db.query(AcademicTeacherReportJob).filter(
        AcademicTeacherReportJob.idempotency_key == key,
    ).one_or_none()
    if existing is not None:
        return existing
    scope_parent = _scope_parent(db, root, scope)
    logical_target_key = (
        f'{scope["scope_key"]}:{campus}' if campus else str(scope['scope_key'])
    )
    job = AcademicTeacherReportJob(
        parent_job_id=str(root.id),
        idempotency_key=key,
        job_type='scheduled_export_excel',
        status='queued',
        term_id=str(scope['term_id']),
        branch=str(scope['branch']),
        campus=campus,
        requested_by=DAILY_SCHEDULER_ACTOR,
        progress_current=0,
        progress_total=100,
        progress_label='01:00 +07 · chờ tạo file báo cáo',
        request_json=json_safe_value({
            'scheduled': True,
            'management_scope': True,
            'learning_platform': 'cms',
            'daily_root_job_id': str(root.id),
            'source_sync_parent_id': str(scope_parent.id),
            'source_synced_at': str((root.result_json or {}).get('source_synced_at') or ''),
            'daily_stage': stage,
            'logical_target_key': logical_target_key,
            'attempt_no': max(0, int(round_no)),
            'report_snapshot_id': str(snapshot_id),
            'report_snapshot_scope_hash': str(scope.get('scope_hash') or ''),
            'scope': 'campus' if campus else 'ho',
            'requester_context': _scheduler_requester_context(),
            'scope_enforced_by_backend': True,
        }),
        result_json=json_safe_value({'dispatch': {'state': 'pending'}}),
    )
    db.add(job)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        existing = db.query(AcademicTeacherReportJob).filter(
            AcademicTeacherReportJob.idempotency_key == key,
        ).one_or_none()
        if existing is None:
            raise
        return existing
    db.refresh(job)
    return job


def _dispatch_snapshot_job(celery_app, db: Session, job: AcademicBulkOperationJob) -> None:
    payload = dict(job.result_json or {})
    dispatch = dict(payload.get('dispatch') or {})
    if job.status != 'queued' or dispatch.get('celery_task_id'):
        return
    try:
        result = celery_app.send_task(
            DAILY_SNAPSHOT_TASK,
            args=[str(job.id)],
            queue='exports',
        )
        dispatch.update({
            'state': 'confirmed',
            'celery_task_id': str(getattr(result, 'id', '') or ''),
            'confirmed_at': datetime.utcnow().isoformat(),
        })
    except Exception as exc:
        job.status = 'failed'
        job.error_message = str(exc)[:4000]
        job.finished_at = datetime.utcnow()
        dispatch.update({'state': 'failed', 'error_type': exc.__class__.__name__})
    payload['dispatch'] = dispatch
    job.result_json = json_safe_value(payload)
    job.updated_at = datetime.utcnow()
    db.add(job)
    db.commit()


def _all_stage_jobs(
    db: Session,
    state: dict[str, Any],
    stage: str,
    model,
) -> dict[str, Any]:
    selected: dict[str, Any] = {}
    stage_rounds = dict((state.get('attempts_by_stage') or {}).get(stage) or {})
    for round_key in sorted(stage_rounds, key=lambda value: int(value)):
        for target, job_id in dict(stage_rounds[round_key] or {}).items():
            job = db.get(model, str(job_id))
            if job is not None and str(job.status or '').lower() == 'completed':
                selected[str(target)] = job
    return selected


def _campus_targets(scopes: list[dict[str, Any]]) -> list[str]:
    rows = [
        [f'{scope["scope_key"]}:{campus}' for campus in scope.get('campuses') or []]
        for scope in sorted(scopes, key=lambda item: (str(item.get('branch')), str(item.get('term_id'))))
    ]
    return [
        target
        for index in range(max((len(row) for row in rows), default=0))
        for row in rows
        for target in row[index:index + 1]
    ]


def _frozen_scopes(state: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        dict(value)
        for value in dict(state.get('frozen_scopes_after_ap') or {}).values()
        if isinstance(value, dict)
    ]


def _save_root_state(
    db: Session,
    root: AcademicBulkOperationJob,
    state: dict[str, Any],
) -> None:
    now = datetime.utcnow()
    phase = str(state.get('phase') or 'ap_sync')
    if root.status in {'queued', 'running'}:
        progress, label = _ROOT_PHASE_PROGRESS.get(
            phase,
            (max(1, int(root.progress_current or 1)), str(root.progress_label or 'Đang điều phối')),
        )
        root.status = 'running'
        root.progress_current = progress
        root.progress_total = 100
        root.progress_label = label[:255]
        root.error_message = None
    root.result_json = json_safe_value(state)
    root.updated_at = now
    _sync_scope_parent_states(db, root, state, now=now)
    db.add(root)
    db.commit()


def _publish_root_continuation(
    celery_app, db: Session, root: AcademicBulkOperationJob, *, countdown: int = 15,
) -> None:
    try:
        publish_parent_continuation(
            db, root, publisher=_continuation_publisher(celery_app),
            task_name=DAILY_ROOT_TASK, args=[str(root.id)], queue=DAILY_COORDINATOR_QUEUE,
            countdown=countdown, confirmation_timeout_seconds=class_sync_queued_timeout_seconds(),
        )
    except ContinuationPublishError:
        if root.status == 'failed':
            _sync_scope_parent_states(db, root, dict(root.result_json or {}))
            db.commit()
        raise


def _reconcile_attempt_rows(
    db: Session,
    rows: list[Any],
    *,
    running_timeout_seconds: int,
) -> None:
    changed = reconcile_stale_rows(
        [row for row in rows if row is not None],
        now=datetime.utcnow(),
        queued_timeout_seconds=class_sync_queued_timeout_seconds(),
        running_timeout_seconds=max(1, int(running_timeout_seconds)),
    )
    if changed:
        db.add_all(changed)
        db.commit()


def _attempt_model_for_stage(stage: str):
    if stage == 'ap_sync':
        return AcademicSyncRun
    if stage in {'account_enrollment', 'score_update'}:
        return AcademicClassSyncJob
    if stage in {'campus_reports', 'ho_reports'}:
        return AcademicTeacherReportJob
    return AcademicBulkOperationJob


def _fail_exhausted_stage(
    db: Session,
    root: AcademicBulkOperationJob,
    state: dict[str, Any],
    *,
    stage: str,
    failed_target_keys: tuple[str, ...],
    attempt_ids: dict[str, str],
) -> dict[str, object]:
    now = datetime.utcnow()
    failure_details: list[dict[str, str]] = []
    for target_key in failed_target_keys:
        attempt_id = attempt_ids.get(target_key)
        attempt = db.get(_attempt_model_for_stage(stage), str(attempt_id or ''))
        message = str(getattr(attempt, 'error_message', '') or '').strip()
        if message:
            failure_details.append({
                'target_key': str(target_key),
                'attempt_id': str(attempt_id or ''),
                'message': message[:1000],
            })
    state.update({
        'phase': 'failed',
        'failed_stage': stage,
        'failed_scope_keys': list(failed_target_keys),
        'failed_target_keys': list(failed_target_keys),
        'final_attempt_ids': {
            key: attempt_ids.get(key)
            for key in failed_target_keys
        },
        'code': 'stage_retry_exhausted',
        'failure_details': failure_details,
    })
    root.status = 'failed'
    root.progress_current = 100
    root.progress_label = f'01:00 +07 · {stage} thất bại sau retry'
    root_error = f'{stage} exhausted: {", ".join(failed_target_keys)}'
    if failure_details:
        root_error += '; causes: ' + ' | '.join(
            f'{item["target_key"]}: {item["message"]}'
            for item in failure_details[:3]
        )
    root.error_message = root_error[:4000]
    root.finished_at = now
    _save_root_state(db, root, state)
    return {
        'ok': False,
        'status': 'failed',
        'code': 'stage_retry_exhausted',
        'failed_stage': stage,
        'failed_target_keys': list(failed_target_keys),
        'root_job_id': str(root.id),
    }


def _dispatch_mapping_job(celery_app, db: Session, job: AcademicBulkOperationJob) -> None:
    result = dict(job.result_json or {})
    enqueue = result.get('enqueue') if isinstance(result.get('enqueue'), dict) else {}
    if job.status != 'queued' or enqueue.get('celery_task_id'):
        return
    try:
        async_result = celery_app.send_task(
            'academic_subject_auto_map_all_sync_task',
            args=[str(job.id)],
            queue='sync-bulk',
        )
        result['enqueue'] = {
            'task_name': 'academic_subject_auto_map_all_sync_task',
            'celery_task_id': str(getattr(async_result, 'id', '') or ''),
            'enqueued_at': datetime.utcnow().isoformat(),
        }
    except Exception as exc:
        job.status = 'failed'
        job.error_message = str(exc)[:4000]
        job.finished_at = datetime.utcnow()
        result['enqueue_error'] = str(exc)[:2000]
    job.result_json = json_safe_value(result)
    job.updated_at = datetime.utcnow()
    db.add(job)
    db.commit()


def _round_robin_class_targets(scopes: list[dict[str, Any]]) -> list[str]:
    ordered_rows = [
        [str(value) for value in scope.get('class_ids') or []]
        for scope in sorted(
            scopes,
            key=lambda item: (str(item.get('branch')), str(item.get('term_id'))),
        )
    ]
    return [
        class_id
        for index in range(max((len(row) for row in ordered_rows), default=0))
        for row in ordered_rows
        for class_id in row[index:index + 1]
    ]


def _class_scope_index(state: dict[str, Any]) -> dict[str, dict[str, Any]]:
    scopes = [
        dict(value)
        for value in dict(state.get('frozen_scopes_after_ap') or {}).values()
        if isinstance(value, dict)
    ]
    return {
        str(class_id): scope
        for scope in scopes
        for class_id in scope.get('class_ids') or []
    }


def _dispatch_class_job(celery_app, db: Session, job: AcademicClassSyncJob) -> None:
    result = dict(job.result_json or {})
    enqueue = result.get('enqueue') if isinstance(result.get('enqueue'), dict) else {}
    if job.status != 'queued' or enqueue.get('celery_task_id'):
        return
    try:
        async_result = celery_app.send_task(
            'academic_class_sync_task',
            args=[str(job.id)],
            queue='sync-bulk',
        )
        result['enqueue'] = {
            'task_name': 'academic_class_sync_task',
            'celery_task_id': str(getattr(async_result, 'id', '') or ''),
            'enqueued_at': datetime.utcnow().isoformat(),
        }
    except Exception as exc:
        job.status = 'failed'
        job.error_message = str(exc)[:4000]
        job.finished_at = datetime.utcnow()
        result['enqueue_error'] = str(exc)[:2000]
    job.result_json = json_safe_value(result)
    job.updated_at = datetime.utcnow()
    db.add(job)
    db.commit()


def _class_attempt_request(
    root: AcademicBulkOperationJob,
    scope_parent: AcademicBulkOperationJob,
    scope: dict[str, Any],
    class_id: str,
    *,
    stage: str,
    round_no: int,
) -> dict[str, Any]:
    root_request = root.request_json if isinstance(root.request_json, dict) else {}
    run_date = str(root_request.get('run_date_vn') or '')
    logical_target_key = f'{stage}:{scope["scope_key"]}:{class_id}'
    return {
        'scheduled': True,
        'stage_managed_retries': True,
        'daily_root_job_id': str(root.id),
        'scheduled_parent_job_id': str(scope_parent.id),
        'scheduled_scope_hash': str(scope['scope_hash']),
        'logical_target_key': logical_target_key,
        'mutation_intent_key': (
            f'academic-daily:v2:{run_date}:{stage}:{scope["scope_key"]}:{class_id}'
        ),
        'attempt_no': max(0, int(round_no)),
        'auto_map_course': False,
        'sync_learning': stage == 'score_update',
        # Every daily run rechecks accounts and enrollment for the full roster,
        # including locally cached matched/enrolled students. The score stage
        # also refreshes everyone rather than reusing yesterday's payload.
        'force': True,
        'limit': max(
            1000,
            min(
                int(settings.academic_class_sync_max_students or 5000),
                20000,
            ),
        ),
        'immediate_after_enrollment': stage == 'score_update',
        'mode': None,
        'requester_context': _scheduler_requester_context(),
    }


def _run_class_stage(
    celery_app,
    db: Session,
    root: AcademicBulkOperationJob,
    state: dict[str, Any],
    *,
    stage: str,
) -> dict[str, object]:
    class_scopes = _class_scope_index(state)
    round_no = max(0, int(state.get('stage_round') or 0))
    targets = [str(value) for value in state.get('stage_target_keys') or []]
    attempts = _stage_attempts(state, stage, round_no)
    jobs = {
        target: db.get(AcademicClassSyncJob, job_id)
        for target, job_id in attempts.items()
    }
    _reconcile_attempt_rows(
        db,
        list(jobs.values()),
        running_timeout_seconds=int(settings.academic_class_sync_stale_seconds),
    )
    jobs = {
        target: db.get(AcademicClassSyncJob, job_id)
        for target, job_id in attempts.items()
    }
    statuses = {
        target: str(job.status or '').lower()
        for target, job in jobs.items()
        if job is not None
    }
    active_count = sum(status in ACTIVE for status in statuses.values())
    for class_id in select_global_dispatch_targets(
        targets,
        statuses,
        active_count=active_count,
    ):
        scope = class_scopes[class_id]
        parents = ensure_scope_parents(db, root, [scope])
        group = 'provision' if stage == 'account_enrollment' else 'score-report'
        scope_parent = parents[f'{scope["scope_key"]}:{group}']
        parent_request = dict(scope_parent.request_json or {})
        parent_request.update({
            'scope_hash': scope['scope_hash'],
            'frozen_scope': scope,
            'scope': scope,
        })
        scope_parent.request_json = json_safe_value(parent_request)
        db.add(scope_parent)
        db.commit()
        try:
            job = ensure_class_attempt_job(
                db,
                scope_parent=scope_parent,
                class_id=class_id,
                stage=stage,
                round_no=round_no,
                request=_class_attempt_request(
                    root,
                    scope_parent,
                    scope,
                    class_id,
                    stage=stage,
                    round_no=round_no,
                ),
            )
        except ClassSyncJobBlocked:
            continue
        attempts[class_id] = str(job.id)
        statuses[class_id] = str(job.status or '').lower()
        _dispatch_class_job(celery_app, db, job)
    _set_stage_attempts(state, stage, round_no, attempts)
    state['stage_attempt_ids'] = dict(attempts)
    _save_root_state(db, root, state)

    decision = plan_stage_barrier(
        targets,
        statuses,
        current_round=round_no,
    )
    if not decision.ready:
        _publish_root_continuation(celery_app, db, root)
        return {
            'ok': True,
            'status': 'waiting_stage',
            'phase': stage,
            'root_job_id': str(root.id),
        }
    if decision.exhausted:
        state.setdefault('artifacts', {})
        state['report_job_count'] = 0
        return _fail_exhausted_stage(
            db,
            root,
            state,
            stage=stage,
            failed_target_keys=decision.retry_target_keys,
            attempt_ids=attempts,
        )
    if decision.retry_target_keys:
        retry_round = int(decision.next_round or round_no + 1)
        state['stage_round'] = retry_round
        state['stage_target_keys'] = list(decision.retry_target_keys)
        _set_stage_attempts(state, stage, retry_round, {})
        state['stage_attempt_ids'] = {}
        _save_root_state(db, root, state)
        return _run_class_stage(
            celery_app,
            db,
            root,
            state,
            stage=stage,
        )

    scopes = [
        dict(value)
        for value in dict(state.get('frozen_scopes_after_ap') or {}).values()
        if isinstance(value, dict)
    ]
    all_class_ids = _round_robin_class_targets(scopes)
    if stage == 'account_enrollment':
        state.update({
            'phase': 'score_update',
            'stage_round': 0,
            'stage_target_keys': all_class_ids,
        })
        _save_root_state(db, root, state)
        return _run_class_stage(
            celery_app,
            db,
            root,
            state,
            stage='score_update',
        )

    score_jobs = _all_stage_jobs(
        db,
        state,
        'score_update',
        AcademicClassSyncJob,
    )
    score_finished = [job.finished_at for job in score_jobs.values() if job.finished_at]
    source_synced_at = max(score_finished or [datetime.utcnow()]).isoformat()
    state.update({
        'phase': 'campus_snapshots',
        'stage_round': 0,
        'stage_target_keys': [str(scope['scope_key']) for scope in scopes],
        'source_synced_at': source_synced_at,
        'score_job_ids_by_class': {
            class_id: str(job.id)
            for class_id, job in score_jobs.items()
        },
    })
    _save_root_state(db, root, state)
    _publish_root_continuation(celery_app, db, root)
    return {
        'ok': True,
        'status': 'stage_complete',
        'phase': 'campus_snapshots',
        'root_job_id': str(root.id),
    }


def _run_snapshot_stage(
    celery_app,
    db: Session,
    root: AcademicBulkOperationJob,
    state: dict[str, Any],
    *,
    snapshot_type: str,
) -> dict[str, object]:
    stage = 'campus_snapshots' if snapshot_type == 'campus_set' else 'ho_snapshots'
    scopes = _frozen_scopes(state)
    scope_index = {str(scope['scope_key']): scope for scope in scopes}
    round_no = max(0, int(state.get('stage_round') or 0))
    targets = [str(value) for value in state.get('stage_target_keys') or []]
    attempts = _stage_attempts(state, stage, round_no)
    jobs = {
        target: db.get(AcademicBulkOperationJob, job_id)
        for target, job_id in attempts.items()
    }
    _reconcile_attempt_rows(
        db,
        list(jobs.values()),
        running_timeout_seconds=DAILY_SNAPSHOT_RUNNING_STALE_SECONDS,
    )
    jobs = {
        target: db.get(AcademicBulkOperationJob, job_id)
        for target, job_id in attempts.items()
    }
    statuses = {
        target: str(job.status or '').lower()
        for target, job in jobs.items()
        if job is not None
    }
    active_count = db.query(AcademicBulkOperationJob).filter(
        AcademicBulkOperationJob.parent_job_id == str(root.id),
        AcademicBulkOperationJob.job_type == 'daily_report_snapshot_attempt',
        AcademicBulkOperationJob.status.in_(list(ACTIVE)),
    ).count()
    for target in select_global_dispatch_targets(
        targets,
        statuses,
        active_count=active_count,
    ):
        scope = scope_index[target]
        job = ensure_snapshot_attempt(
            db,
            root=root,
            scope=scope,
            snapshot_type=snapshot_type,
            round_no=round_no,
        )
        request = dict(job.request_json or {})
        request['source_synced_at'] = str(state.get('source_synced_at') or '')
        request['score_job_ids_by_class'] = {
            class_id: job_id
            for class_id, job_id in dict(state.get('score_job_ids_by_class') or {}).items()
            if class_id in set(scope.get('class_ids') or [])
        }
        if snapshot_type == 'ho':
            request['campus_snapshot_ids_by_campus'] = {
                campus: state.get('campus_snapshot_ids_by_target', {}).get(
                    f'{scope["scope_key"]}:{campus}'
                )
                for campus in scope.get('campuses') or []
            }
        job.request_json = json_safe_value(request)
        db.add(job)
        db.commit()
        attempts[target] = str(job.id)
        statuses[target] = str(job.status or '').lower()
        _dispatch_snapshot_job(celery_app, db, job)
    _set_stage_attempts(state, stage, round_no, attempts)
    state['stage_attempt_ids'] = dict(attempts)
    _save_root_state(db, root, state)

    decision = plan_stage_barrier(targets, statuses, current_round=round_no)
    if not decision.ready:
        _publish_root_continuation(celery_app, db, root)
        return {'ok': True, 'status': 'waiting_stage', 'phase': stage, 'root_job_id': str(root.id)}
    if decision.exhausted:
        completed = _all_stage_jobs(db, state, stage, AcademicBulkOperationJob)
        artifacts = state.setdefault('artifacts', {})
        artifacts[stage] = {target: str(job.id) for target, job in completed.items()}
        return _fail_exhausted_stage(
            db,
            root,
            state,
            stage=stage,
            failed_target_keys=decision.retry_target_keys,
            attempt_ids=attempts,
        )
    if decision.retry_target_keys:
        retry_round = int(decision.next_round or round_no + 1)
        state['stage_round'] = retry_round
        state['stage_target_keys'] = list(decision.retry_target_keys)
        _set_stage_attempts(state, stage, retry_round, {})
        state['stage_attempt_ids'] = {}
        _save_root_state(db, root, state)
        return _run_snapshot_stage(
            celery_app,
            db,
            root,
            state,
            snapshot_type=snapshot_type,
        )

    completed = _all_stage_jobs(db, state, stage, AcademicBulkOperationJob)
    if snapshot_type == 'campus_set':
        snapshot_ids_by_target: dict[str, str] = {}
        snapshot_checksums: dict[str, str] = {}
        for scope_key, job in completed.items():
            result = dict(job.result_json or {})
            for campus, snapshot_id in dict(result.get('snapshot_ids_by_campus') or {}).items():
                target = f'{scope_key}:{campus}'
                snapshot_ids_by_target[target] = str(snapshot_id)
            snapshot_checksums.update({
                str(key): str(value)
                for key, value in dict(result.get('snapshot_checksums') or {}).items()
            })
        state.update({
            'phase': 'campus_reports',
            'stage_round': 0,
            'stage_target_keys': _campus_targets(scopes),
            'campus_snapshot_ids_by_target': snapshot_ids_by_target,
            'campus_snapshot_checksums': snapshot_checksums,
        })
        _save_root_state(db, root, state)
        return _run_report_stage(celery_app, db, root, state, stage='campus_reports')

    ho_snapshot_ids = {
        scope_key: str((job.result_json or {}).get('ho_snapshot_id') or '')
        for scope_key, job in completed.items()
    }
    state.update({
        'phase': 'ho_reports',
        'stage_round': 0,
        'stage_target_keys': [str(scope['scope_key']) for scope in scopes],
        'ho_snapshot_ids_by_scope': ho_snapshot_ids,
    })
    _save_root_state(db, root, state)
    return _run_report_stage(celery_app, db, root, state, stage='ho_reports')


def _run_report_stage(
    celery_app,
    db: Session,
    root: AcademicBulkOperationJob,
    state: dict[str, Any],
    *,
    stage: str,
) -> dict[str, object]:
    from app.services.academic.daily_teacher_report_runtime import (
        _publish_scheduled_export_job,
    )

    scopes = _frozen_scopes(state)
    scope_index = {str(scope['scope_key']): scope for scope in scopes}
    round_no = max(0, int(state.get('stage_round') or 0))
    targets = [str(value) for value in state.get('stage_target_keys') or []]
    attempts = _stage_attempts(state, stage, round_no)
    jobs = {
        target: db.get(AcademicTeacherReportJob, job_id)
        for target, job_id in attempts.items()
    }
    statuses = {
        target: str(job.status or '').lower()
        for target, job in jobs.items()
        if job is not None
    }
    active_count = db.query(AcademicTeacherReportJob).filter(
        AcademicTeacherReportJob.parent_job_id == str(root.id),
        AcademicTeacherReportJob.status.in_(list(ACTIVE)),
    ).count()
    for target in select_global_dispatch_targets(
        targets,
        statuses,
        active_count=active_count,
    ):
        if stage == 'campus_reports':
            scope_key, campus = target.rsplit(':', 1)
            scope = scope_index[scope_key]
            snapshot_id = str(
                (state.get('campus_snapshot_ids_by_target') or {}).get(target) or ''
            )
        else:
            scope_key, campus = target, None
            scope = scope_index[scope_key]
            snapshot_id = str(
                (state.get('ho_snapshot_ids_by_scope') or {}).get(scope_key) or ''
            )
        if not snapshot_id:
            raise RuntimeError(f'Missing immutable snapshot for report target {target}.')
        job = ensure_report_attempt(
            db,
            root=root,
            scope=scope,
            campus=campus,
            stage=stage,
            round_no=round_no,
            snapshot_id=snapshot_id,
        )
        if stage == 'ho_reports':
            request = dict(job.request_json or {})
            campus_targets = [
                f'{scope_key}:{value}' for value in scope.get('campuses') or []
            ]
            campus_jobs = _all_stage_jobs(
                db, state, 'campus_reports', AcademicTeacherReportJob,
            )
            request.update({
                'aggregate_after_campus_reports': True,
                'source_campus_report_job_ids': [
                    str(campus_jobs[key].id) for key in campus_targets
                ],
                'source_campus_snapshot_ids': [
                    str((state.get('campus_snapshot_ids_by_target') or {}).get(key) or '')
                    for key in campus_targets
                ],
                'source_campus_checksums': dict(state.get('campus_snapshot_checksums') or {}),
            })
            job.request_json = json_safe_value(request)
            db.add(job)
            db.commit()
        attempts[target] = str(job.id)
        statuses[target] = str(job.status or '').lower()
        _publish_scheduled_export_job(db, celery_app, job)
    _set_stage_attempts(state, stage, round_no, attempts)
    state['stage_attempt_ids'] = dict(attempts)
    _save_root_state(db, root, state)

    decision = plan_stage_barrier(targets, statuses, current_round=round_no)
    if not decision.ready:
        _publish_root_continuation(celery_app, db, root)
        return {'ok': True, 'status': 'waiting_stage', 'phase': stage, 'root_job_id': str(root.id)}
    completed = _all_stage_jobs(db, state, stage, AcademicTeacherReportJob)
    if decision.exhausted:
        artifacts = state.setdefault('artifacts', {})
        artifacts[stage] = {target: str(job.id) for target, job in completed.items()}
        return _fail_exhausted_stage(
            db,
            root,
            state,
            stage=stage,
            failed_target_keys=decision.retry_target_keys,
            attempt_ids=attempts,
        )
    if decision.retry_target_keys:
        retry_round = int(decision.next_round or round_no + 1)
        state['stage_round'] = retry_round
        state['stage_target_keys'] = list(decision.retry_target_keys)
        _set_stage_attempts(state, stage, retry_round, {})
        state['stage_attempt_ids'] = {}
        _save_root_state(db, root, state)
        return _run_report_stage(celery_app, db, root, state, stage=stage)

    artifacts = state.setdefault('artifacts', {})
    artifacts[stage] = {target: str(job.id) for target, job in completed.items()}
    if stage == 'campus_reports':
        state.update({
            'phase': 'ho_snapshots',
            'stage_round': 0,
            'stage_target_keys': [str(scope['scope_key']) for scope in scopes],
        })
        _save_root_state(db, root, state)
        return _run_snapshot_stage(
            celery_app, db, root, state, snapshot_type='ho',
        )

    now = datetime.utcnow()
    state.update({'phase': 'completed', 'finished_at': now.isoformat(), 'ok': True})
    root.status = 'completed'
    root.progress_current = 100
    root.progress_total = 100
    root.progress_label = '01:00 +07 · hoàn tất đồng bộ và báo cáo'
    root.error_message = None
    root.finished_at = now
    _save_root_state(db, root, state)
    return {
        'ok': True,
        'status': 'completed',
        'root_job_id': str(root.id),
        'artifacts': artifacts,
    }


def _run_ap_stage(
    celery_app,
    db: Session,
    root: AcademicBulkOperationJob,
    state: dict[str, Any],
) -> dict[str, object]:
    scopes = _scope_by_key(root)
    round_no = max(0, int(state.get('stage_round') or 0))
    targets = [str(value) for value in state.get('stage_target_keys') or []]
    attempts = _stage_attempts(state, 'ap_sync', round_no)
    runs = {
        target: db.get(AcademicSyncRun, run_id)
        for target, run_id in attempts.items()
    }
    _reconcile_ap_runs(db, list(runs.values()))
    runs = {
        target: db.get(AcademicSyncRun, run_id)
        for target, run_id in attempts.items()
    }
    statuses = {
        target: str(run.status or '').lower()
        for target, run in runs.items()
        if run is not None
    }
    active_count = sum(status in ACTIVE for status in statuses.values())
    for target in select_global_dispatch_targets(
        targets,
        statuses,
        active_count=active_count,
    ):
        run = enqueue_ap_stage_attempt(db, root, scopes[target], round_no)
        attempts[target] = str(run.id)
        statuses[target] = str(run.status or '').lower()
    _set_stage_attempts(state, 'ap_sync', round_no, attempts)
    state['stage_attempt_ids'] = dict(attempts)
    _save_root_state(db, root, state)

    decision = plan_stage_barrier(
        targets,
        statuses,
        current_round=round_no,
    )
    if not decision.ready:
        _publish_root_continuation(celery_app, db, root)
        return {
            'ok': True,
            'status': 'waiting_stage',
            'phase': 'ap_sync',
            'root_job_id': str(root.id),
        }
    if decision.exhausted:
        return _fail_exhausted_stage(
            db,
            root,
            state,
            stage='ap_sync',
            failed_target_keys=decision.retry_target_keys,
            attempt_ids=attempts,
        )
    if decision.retry_target_keys:
        state['stage_round'] = int(decision.next_round or round_no + 1)
        state['stage_target_keys'] = list(decision.retry_target_keys)
        retry_round = int(state['stage_round'])
        retry_attempts: dict[str, str] = {}
        for target in select_global_dispatch_targets(
            decision.retry_target_keys,
            {},
            active_count=0,
        ):
            run = enqueue_ap_stage_attempt(db, root, scopes[target], retry_round)
            retry_attempts[target] = str(run.id)
        _set_stage_attempts(state, 'ap_sync', retry_round, retry_attempts)
        state['stage_attempt_ids'] = dict(retry_attempts)
        _save_root_state(db, root, state)
        _publish_root_continuation(celery_app, db, root)
        return {
            'ok': True,
            'status': 'retrying_stage',
            'phase': 'ap_sync',
            'stage_round': retry_round,
            'retry_target_keys': list(decision.retry_target_keys),
            'root_job_id': str(root.id),
        }

    refreshed_scopes = {
        key: _refresh_scope_after_ap(db, scope)
        for key, scope in scopes.items()
    }
    state.update({
        'phase': 'course_mapping',
        'stage_round': 0,
        'stage_target_keys': list(scopes),
        'frozen_scopes_after_ap': refreshed_scopes,
    })
    _save_root_state(db, root, state)
    return _run_mapping_stage(celery_app, db, root, state)


def _run_mapping_stage(
    celery_app,
    db: Session,
    root: AcademicBulkOperationJob,
    state: dict[str, Any],
) -> dict[str, object]:
    root_scopes = _scope_by_key(root)
    frozen = {
        str(key): dict(value)
        for key, value in dict(state.get('frozen_scopes_after_ap') or {}).items()
        if isinstance(value, dict)
    }
    scopes = {key: frozen.get(key, value) for key, value in root_scopes.items()}
    round_no = max(0, int(state.get('stage_round') or 0))
    targets = [str(value) for value in state.get('stage_target_keys') or []]
    attempts = _stage_attempts(state, 'course_mapping', round_no)
    jobs = {
        target: db.get(AcademicBulkOperationJob, job_id)
        for target, job_id in attempts.items()
    }
    _reconcile_attempt_rows(
        db,
        list(jobs.values()),
        running_timeout_seconds=DAILY_MAPPING_RUNNING_STALE_SECONDS,
    )
    jobs = {
        target: db.get(AcademicBulkOperationJob, job_id)
        for target, job_id in attempts.items()
    }
    statuses = {
        target: str(job.status or '').lower()
        for target, job in jobs.items()
        if job is not None
    }
    active_count = sum(status in ACTIVE for status in statuses.values())
    for target in select_global_dispatch_targets(
        targets,
        statuses,
        active_count=active_count,
    ):
        job = ensure_mapping_attempt(db, root, scopes[target], round_no)
        attempts[target] = str(job.id)
        statuses[target] = str(job.status or '').lower()
        _dispatch_mapping_job(celery_app, db, job)
    _set_stage_attempts(state, 'course_mapping', round_no, attempts)
    state['stage_attempt_ids'] = dict(attempts)
    _save_root_state(db, root, state)

    decision = plan_stage_barrier(
        targets,
        statuses,
        current_round=round_no,
    )
    if not decision.ready:
        _publish_root_continuation(celery_app, db, root)
        return {
            'ok': True,
            'status': 'waiting_stage',
            'phase': 'course_mapping',
            'root_job_id': str(root.id),
        }
    if decision.exhausted:
        return _fail_exhausted_stage(
            db,
            root,
            state,
            stage='course_mapping',
            failed_target_keys=decision.retry_target_keys,
            attempt_ids=attempts,
        )
    if decision.retry_target_keys:
        retry_round = int(decision.next_round or round_no + 1)
        state['stage_round'] = retry_round
        state['stage_target_keys'] = list(decision.retry_target_keys)
        retry_attempts: dict[str, str] = {}
        for target in select_global_dispatch_targets(
            decision.retry_target_keys,
            {},
            active_count=0,
        ):
            job = ensure_mapping_attempt(db, root, scopes[target], retry_round)
            retry_attempts[target] = str(job.id)
            _dispatch_mapping_job(celery_app, db, job)
        _set_stage_attempts(state, 'course_mapping', retry_round, retry_attempts)
        state['stage_attempt_ids'] = dict(retry_attempts)
        _save_root_state(db, root, state)
        _publish_root_continuation(celery_app, db, root)
        return {
            'ok': True,
            'status': 'retrying_stage',
            'phase': 'course_mapping',
            'stage_round': retry_round,
            'retry_target_keys': list(decision.retry_target_keys),
            'root_job_id': str(root.id),
        }

    state.update({
        'phase': 'account_enrollment',
        'stage_round': 0,
        'stage_target_keys': _round_robin_class_targets(list(scopes.values())),
    })
    _save_root_state(db, root, state)
    _publish_root_continuation(celery_app, db, root)
    return {
        'ok': True,
        'status': 'stage_complete',
        'phase': 'account_enrollment',
        'root_job_id': str(root.id),
    }


def start_daily_academic_pipeline(
    celery_app,
    *,
    now: datetime | None = None,
) -> dict[str, object]:
    local_now = _local_now(now)
    stored_now = _utc_naive(local_now)
    run_date_vn = local_now.date().isoformat()
    with _daily_coordinator_session() as (db, acquired):
        if not acquired:
            celery_app.send_task(DAILY_START_TASK, args=[], queue=DAILY_COORDINATOR_QUEUE, countdown=30)
            return {'ok': True, 'status': 'coordinator_busy', 'retry_scheduled': True}
        existing_root = (
            db.query(AcademicBulkOperationJob)
            .filter(
                AcademicBulkOperationJob.idempotency_key
                == daily_root_key(run_date_vn),
            )
            .one_or_none()
        )
        if existing_root is not None:
            _mark_older_active_roots_superseded(
                db,
                keep_root_id=str(existing_root.id),
                now=stored_now,
            )
            frozen_request = (
                existing_root.request_json
                if isinstance(existing_root.request_json, dict)
                else {}
            )
            frozen_scopes = list(frozen_request.get('scopes') or [])
            if existing_root.status in {'queued', 'running'}:
                ensure_scope_parents(db, existing_root, frozen_scopes)
                continuation = (
                    dict((existing_root.result_json or {}).get('continuation') or {})
                    if isinstance(existing_root.result_json, dict)
                    else {}
                )
                if str(continuation.get('status') or '') in {'', 'dispatch_pending'}:
                    _publish_root_continuation(celery_app, db, existing_root, countdown=5)
            existing_state = (
                existing_root.result_json
                if isinstance(existing_root.result_json, dict)
                else {}
            )
            response: dict[str, object] = {
                'ok': existing_root.status != 'failed',
                'created': False,
                'root_job_id': str(existing_root.id),
                'scope_count': len(frozen_scopes),
            }
            if existing_root.status == 'failed':
                response['code'] = str(existing_state.get('code') or 'root_failed')
            return response

        try:
            scopes = discover_daily_scopes(db)
            discovered_branches = {str(scope['branch']) for scope in scopes}
            missing_branches = [
                branch for branch in REQUIRED_BRANCHES
                if branch not in discovered_branches
            ]
            if missing_branches:
                raise DailyScopeError(
                    'mandatory_branch_scope_missing',
                    f'Missing mandatory daily branches: {", ".join(missing_branches)}.',
                )
        except DailyScopeError as exc:
            scopes = locals().get('scopes', [])
            root, _created = create_or_load_scheduled_parent(
                db,
                idempotency_key=daily_root_key(run_date_vn),
                values={
                    'job_type': DAILY_ROOT_JOB_TYPE,
                    'status': 'failed',
                    'term_id': None,
                    'branch': None,
                    'campus': None,
                    'requested_by': DAILY_SCHEDULER_ACTOR,
                    'progress_current': 100,
                    'progress_total': 100,
                    'progress_label': '01:00 +07 · phạm vi bắt buộc không hợp lệ',
                    'request_json': json_safe_value(_root_request(run_date_vn, scopes)),
                    'result_json': json_safe_value({
                        **_root_state(scopes),
                        'phase': 'failed',
                        'ok': False,
                        'code': exc.code,
                        'message': str(exc),
                    }),
                    'error_message': str(exc),
                    'started_at': stored_now,
                    'finished_at': stored_now,
                    'updated_at': stored_now,
                },
            )
            return {
                'ok': False,
                'code': exc.code,
                'root_job_id': str(root.id),
            }

        root, created = create_or_load_scheduled_parent(
            db,
            idempotency_key=daily_root_key(run_date_vn),
            values={
                'job_type': DAILY_ROOT_JOB_TYPE,
                'status': 'running',
                'term_id': None,
                'branch': None,
                'campus': None,
                'requested_by': DAILY_SCHEDULER_ACTOR,
                'progress_current': 1,
                'progress_total': 100,
                'progress_label': '01:00 +07 · bắt đầu đồng bộ AP',
                'request_json': json_safe_value(_root_request(run_date_vn, scopes)),
                'result_json': json_safe_value(_root_state(scopes)),
                'started_at': stored_now,
                'updated_at': stored_now,
            },
        )
        _mark_older_active_roots_superseded(
            db,
            keep_root_id=str(root.id),
            now=stored_now,
        )
        frozen_request = root.request_json if isinstance(root.request_json, dict) else {}
        frozen_scopes = list(frozen_request.get('scopes') or [])
        ensure_scope_parents(db, root, frozen_scopes)
        continuation = (
            dict((root.result_json or {}).get('continuation') or {})
            if isinstance(root.result_json, dict)
            else {}
        )
        continuation_status = str(continuation.get('status') or '')
        if (
            root.status in {'queued', 'running'}
            and (created or continuation_status in {'', 'dispatch_pending'})
        ):
            _publish_root_continuation(celery_app, db, root, countdown=0 if created else 5)
        return {
            'ok': True,
            'created': created,
            'root_job_id': str(root.id),
            'scope_count': len(frozen_scopes),
        }


def _run_daily_academic_pipeline_locked(celery_app, root_job_id: str) -> dict[str, object]:
    with _daily_coordinator_session() as (db, acquired):
        if not acquired:
            return {'ok': True, 'status': 'coordinator_busy', 'root_job_id': str(root_job_id)}
        try:
            root = db.query(AcademicBulkOperationJob).filter(
                AcademicBulkOperationJob.id == str(root_job_id),
            ).with_for_update().one_or_none()
            if root is None or root.job_type != DAILY_ROOT_JOB_TYPE:
                return {'ok': False, 'code': 'root_job_not_found'}
            if root.status not in {'queued', 'running'}:
                return {
                    'ok': root.status == 'completed',
                    'status': root.status,
                    'root_job_id': str(root.id),
                }
            confirm_parent_continuation(
                db,
                root,
                expected_task_name=DAILY_ROOT_TASK,
            )
            request = root.request_json if isinstance(root.request_json, dict) else {}
            scopes = list(request.get('scopes') or [])
            ensure_scope_parents(db, root, scopes)
            state = dict(root.result_json or {}) if isinstance(root.result_json, dict) else {}
            phase = str(state.get('phase') or 'ap_sync')
            if phase == 'ap_sync':
                return _run_ap_stage(celery_app, db, root, state)
            if phase == 'course_mapping':
                return _run_mapping_stage(celery_app, db, root, state)
            if phase == 'account_enrollment':
                return _run_class_stage(
                    celery_app,
                    db,
                    root,
                    state,
                    stage='account_enrollment',
                )
            if phase == 'score_update':
                return _run_class_stage(
                    celery_app,
                    db,
                    root,
                    state,
                    stage='score_update',
                )
            if phase == 'campus_snapshots':
                return _run_snapshot_stage(
                    celery_app,
                    db,
                    root,
                    state,
                    snapshot_type='campus_set',
                )
            if phase == 'campus_reports':
                return _run_report_stage(
                    celery_app,
                    db,
                    root,
                    state,
                    stage='campus_reports',
                )
            if phase == 'ho_snapshots':
                return _run_snapshot_stage(
                    celery_app,
                    db,
                    root,
                    state,
                    snapshot_type='ho',
                )
            if phase == 'ho_reports':
                return _run_report_stage(
                    celery_app,
                    db,
                    root,
                    state,
                    stage='ho_reports',
                )
            return {
                'ok': True,
                'status': 'ready',
                'phase': phase,
                'root_job_id': str(root.id),
            }
        except ContinuationPublishError as exc:
            db.rollback()
            return {
                'ok': False,
                'status': 'dispatch_pending',
                'root_job_id': str(root_job_id),
                'error': str(exc.original)[:500],
                'error_class': exc.original.__class__.__name__,
            }


def run_daily_academic_pipeline(celery_app, root_job_id: str) -> dict[str, object]:
    return _run_daily_academic_pipeline_locked(celery_app, root_job_id)


def resume_daily_academic_pipeline(
    celery_app, root_job_id: str, *, now: datetime | None = None, actor: str = 'operator',
) -> dict[str, object]:
    """Resume only a transport-failed root, preserving frozen scope and attempts."""
    current_time = now or datetime.utcnow()
    with _daily_coordinator_session() as (db, acquired):
        if not acquired:
            return {'ok': False, 'status': 'coordinator_busy'}
        root = db.get(AcademicBulkOperationJob, str(root_job_id))
        if root is None or root.job_type != DAILY_ROOT_JOB_TYPE:
            return {'ok': False, 'code': 'root_job_not_found'}
        if root.status in ACTIVE:
            return {'ok': True, 'status': 'already_running', 'root_job_id': str(root.id)}
        state = dict(root.result_json or {})
        code = str(state.get('code') or '')
        if (root.status != 'failed'
                or code not in {'continuation_recovery_exhausted', 'continuation_dispatch_exhausted'}
                or str(state.get('phase') or '') not in set(_ROOT_PHASE_PROGRESS) - {'completed'}):
            return {'ok': False, 'code': 'root_failure_not_resumable'}
        created_at = _parse_state_time(root.created_at)
        if created_at is None or (current_time-created_at).total_seconds() > DAILY_MAX_RUNTIME_SECONDS:
            return {'ok': False, 'code': 'pipeline_runtime_exceeded'}
        other_roots = db.query(AcademicBulkOperationJob).filter(
            AcademicBulkOperationJob.job_type == DAILY_ROOT_JOB_TYPE,
            AcademicBulkOperationJob.id != str(root.id),
        ).all()
        date = str((root.request_json or {}).get('run_date_vn') or '')
        if any(other.status in ACTIVE or str((other.request_json or {}).get('run_date_vn') or '') > date
               for other in other_roots):
            return {'ok': False, 'code': 'newer_or_active_daily_root_exists'}
        original_error = root.error_message
        history = list(state.get('resume_history') or [])
        history.append({'at': current_time.isoformat(), 'actor': str(actor),
                        'code': code, 'error': original_error})
        state['resume_history'] = history[-10:]
        for key in ('code', 'failed_target_key'):
            state.pop(key, None)
        state['continuation'] = {'status': 'confirmed', 'attempt_count': 0,
                                 'publish_failure_count': 0, 'task_name': DAILY_ROOT_TASK}
        root.status = 'running'
        root.error_message = None
        root.finished_at = None
        for scope in db.query(AcademicBulkOperationJob).filter(
                AcademicBulkOperationJob.parent_job_id == str(root.id),
                AcademicBulkOperationJob.job_type.in_(
                    ['academic_daily_provision_scope', 'academic_daily_score-report_scope'])).all():
            if (scope.status == 'failed'
                    and ((scope.result_json or {}).get('root_failure_code') == code
                         or (original_error and scope.error_message == original_error))):
                scope.status = 'queued'
                scope.finished_at = None
                scope.error_message = None
                payload = dict(scope.result_json or {})
                payload.pop('root_failure_code', None)
                scope.result_json = json_safe_value(payload)
                db.add(scope)
        _save_root_state(db, root, state)
        try:
            _publish_root_continuation(celery_app, db, root)
        except ContinuationPublishError:
            return {'ok': False, 'status': 'dispatch_pending', 'root_job_id': str(root.id)}
        return {'ok': True, 'status': 'resumed', 'phase': state.get('phase'),
                'root_job_id': str(root.id)}


def register_daily_academic_pipeline_tasks(celery_app) -> None:
    @celery_app.task(name=DAILY_START_TASK)
    def _daily_pipeline_start_task():
        return start_daily_academic_pipeline(celery_app)

    @celery_app.task(name=DAILY_ROOT_TASK)
    def _daily_pipeline_root_task(root_job_id: str):
        return run_daily_academic_pipeline(celery_app, root_job_id)

    routes = dict(getattr(celery_app.conf, 'task_routes', {}) or {})
    routes.update({
        DAILY_START_TASK: {'queue': DAILY_COORDINATOR_QUEUE},
        DAILY_ROOT_TASK: {'queue': DAILY_COORDINATOR_QUEUE},
    })
    celery_app.conf.task_routes = routes

    annotations = dict(getattr(celery_app.conf, 'task_annotations', {}) or {})
    annotations.update({
        DAILY_START_TASK: {'soft_time_limit': 120, 'time_limit': 180},
        DAILY_ROOT_TASK: {'soft_time_limit': 120, 'time_limit': 180},
    })
    celery_app.conf.task_annotations = annotations

    beat_schedule = dict(getattr(celery_app.conf, 'beat_schedule', {}) or {})
    beat_schedule.pop('academic-ap-sync-and-auto-map-03-vn', None)
    beat_schedule.pop('academic-score-sync-all-students', None)
    beat_schedule['academic-daily-pipeline-01-vn'] = {
        'task': DAILY_START_TASK,
        'schedule': crontab(hour=1, minute=0),
    }
    celery_app.conf.beat_schedule = beat_schedule
