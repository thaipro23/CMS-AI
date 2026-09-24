from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any
from zoneinfo import ZoneInfo

from celery.schedules import crontab
from sqlalchemy import func, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.json_safe import json_safe_value
from app.core.rbac import UserContext
from app.db.session import SessionLocal
from app.models.academic import (
    AcademicBulkOperationJob,
    AcademicCampus,
    AcademicClass,
    AcademicClassSyncJob,
    AcademicSyncRun,
    AcademicTerm,
)
from app.schemas.academic import AcademicAPSyncIn
from app.services.academic.ap_sync import AcademicAPSyncWorkflowService
from app.services.academic.daily_pipeline_state import (
    ACTIVE,
    MAX_STAGE_RETRY_ROUNDS,
    plan_stage_barrier,
    select_global_dispatch_targets,
)
from app.services.academic.job_identity import (
    CLASS_SYNC_POLICY_VERSION,
    ClassSyncJobBlocked,
    choose_active_class_sync_job,
    class_sync_contract,
    class_sync_idempotency_key,
)
from app.services.academic.scheduled_parent import (
    confirm_parent_continuation,
    create_or_load_scheduled_parent,
    publish_parent_continuation,
)


VN_TZ = ZoneInfo('Asia/Ho_Chi_Minh')
DAILY_ROOT_JOB_TYPE = 'academic_daily_pipeline_v2'
DAILY_START_TASK = 'academic_daily_pipeline_start_task'
DAILY_ROOT_TASK = 'academic_daily_pipeline_task'
DAILY_POLICY_VERSION = 'academic-daily/v2'
DAILY_STATE_VERSION = 'academic-daily-state.v2'
DAILY_SCHEDULER_ACTOR = 'academic-daily-scheduler'
REQUIRED_BRANCHES = ('poly', 'ptcd')


class DailyScopeError(ValueError):
    def __init__(self, code: str, message: str):
        self.code = code
        super().__init__(message)


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
            db.query(AcademicClass)
            .filter(
                AcademicClass.active.is_(True),
                AcademicClass.term_id == str(term.id),
                func.lower(func.coalesce(AcademicClass.branch, branch)) == branch,
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
        idempotency_key=_attempt_key(
            root,
            scope_data,
            stage='ap',
            round_no=round_no,
        ),
        run_metadata=metadata,
    )
    run = result['sync_run']
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
        db.query(AcademicClass)
        .filter(
            AcademicClass.active.is_(True),
            AcademicClass.term_id == str(scope['term_id']),
            func.lower(func.coalesce(AcademicClass.branch, branch)) == branch,
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
        if key not in {'scope_hash', 'class_ids', 'class_to_campus'}
    }
    refreshed.update({
        'class_ids': sorted(class_to_campus),
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
        for (value,) in db.query(AcademicClass.subject_id).filter(
            AcademicClass.id.in_(class_ids),
        ).distinct().all()
        if value
    ] if class_ids else []
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


def _save_root_state(
    db: Session,
    root: AcademicBulkOperationJob,
    state: dict[str, Any],
) -> None:
    root.result_json = json_safe_value(state)
    root.updated_at = datetime.utcnow()
    db.add(root)
    db.commit()


def _publish_root_continuation(celery_app, db: Session, root: AcademicBulkOperationJob) -> None:
    publish_parent_continuation(
        db,
        root,
        publisher=_continuation_publisher(celery_app),
        task_name=DAILY_ROOT_TASK,
        args=[str(root.id)],
        queue='sync-bulk',
        countdown=15,
    )


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
    })
    root.status = 'failed'
    root.progress_current = 100
    root.progress_label = f'01:00 +07 · {stage} thất bại sau retry'
    root.error_message = f'{stage} exhausted: {", ".join(failed_target_keys)}'
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
        'force': False,
        'limit': 5000,
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

    state.update({
        'phase': 'campus_reports',
        'stage_round': 0,
        'stage_target_keys': [
            f'{scope["scope_key"]}:{campus}'
            for scope in scopes
            for campus in scope.get('campuses') or []
        ],
    })
    _save_root_state(db, root, state)
    return {
        'ok': True,
        'status': 'stage_complete',
        'phase': 'campus_reports',
        'root_job_id': str(root.id),
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
    db = SessionLocal()
    try:
        existing_root = (
            db.query(AcademicBulkOperationJob)
            .filter(
                AcademicBulkOperationJob.idempotency_key
                == daily_root_key(run_date_vn),
            )
            .one_or_none()
        )
        if existing_root is not None:
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
                    publish_parent_continuation(
                        db,
                        existing_root,
                        publisher=_continuation_publisher(celery_app),
                        task_name=DAILY_ROOT_TASK,
                        args=[str(existing_root.id)],
                        queue='sync-bulk',
                        countdown=5,
                    )
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
            publish_parent_continuation(
                db,
                root,
                publisher=_continuation_publisher(celery_app),
                task_name=DAILY_ROOT_TASK,
                args=[str(root.id)],
                queue='sync-bulk',
                countdown=0 if created else 5,
            )
        return {
            'ok': True,
            'created': created,
            'root_job_id': str(root.id),
            'scope_count': len(frozen_scopes),
        }
    finally:
        db.close()


def run_daily_academic_pipeline(celery_app, root_job_id: str) -> dict[str, object]:
    db = SessionLocal()
    try:
        root = db.get(AcademicBulkOperationJob, str(root_job_id))
        if root is None or root.job_type != DAILY_ROOT_JOB_TYPE:
            return {'ok': False, 'code': 'root_job_not_found'}
        confirm_parent_continuation(
            db,
            root,
            expected_task_name=DAILY_ROOT_TASK,
        )
        if root.status not in {'queued', 'running'}:
            return {
                'ok': root.status == 'completed',
                'status': root.status,
                'root_job_id': str(root.id),
            }
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
        return {
            'ok': True,
            'status': 'ready',
            'phase': phase,
            'root_job_id': str(root.id),
        }
    finally:
        db.close()


def register_daily_academic_pipeline_tasks(celery_app) -> None:
    @celery_app.task(name=DAILY_START_TASK)
    def _daily_pipeline_start_task():
        return start_daily_academic_pipeline(celery_app)

    @celery_app.task(name=DAILY_ROOT_TASK)
    def _daily_pipeline_root_task(root_job_id: str):
        return run_daily_academic_pipeline(celery_app, root_job_id)

    routes = dict(getattr(celery_app.conf, 'task_routes', {}) or {})
    routes.update({
        DAILY_START_TASK: {'queue': 'sync-bulk'},
        DAILY_ROOT_TASK: {'queue': 'sync-bulk'},
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
