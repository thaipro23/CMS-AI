from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any
from zoneinfo import ZoneInfo

from celery.schedules import crontab
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.json_safe import json_safe_value
from app.db.session import SessionLocal
from app.models.academic import (
    AcademicBulkOperationJob,
    AcademicCampus,
    AcademicClass,
    AcademicTerm,
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
        state = root.result_json if isinstance(root.result_json, dict) else {}
        return {
            'ok': True,
            'status': 'ready',
            'phase': str(state.get('phase') or 'ap_sync'),
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
