from __future__ import annotations

import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import func, or_

from app.core.config import settings
from app.core.json_safe import json_safe_value
from app.core.rbac import UserContext
from app.db.session import SessionLocal
from app.models.academic import (
    AcademicBulkOperationJob,
    AcademicClass,
    AcademicClassSyncJob,
    AcademicTeacherReportJob,
    AcademicTerm,
)
from app.services.academic.batch_coordinator import plan_batch_dispatch
from app.services.academic.job_runtime import class_sync_queued_timeout_seconds, reconcile_stale_rows
from app.services.academic.scheduled_parent import (
    ContinuationPublishError,
    confirm_parent_continuation,
    create_or_load_scheduled_parent,
    publish_parent_continuation,
    recover_due_parent_continuations,
    scheduled_parent_key,
)
from app.services.academic_service import AcademicService
from app.services.object_storage import get_object_storage


VN_TZ = ZoneInfo('Asia/Ho_Chi_Minh')
DAILY_PARENT_JOB_TYPE = 'daily_score_report_pipeline'
SCHEDULED_EXPORT_JOB_TYPE = 'scheduled_export_excel'
SCHEDULER_ACTOR = 'academic-score-scheduler'

MANAGEMENT_REPORT_PREBUILT_ONLY = 'MANAGEMENT_REPORT_PREBUILT_ONLY'
WORKER_HEARTBEAT_LOST = 'WORKER_HEARTBEAT_LOST'
JOB_PROGRESS_STALLED = 'JOB_PROGRESS_STALLED'
JOB_RUNTIME_EXCEEDED = 'JOB_RUNTIME_EXCEEDED'


def utc_now_naive() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _aware_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def vn_iso(value: datetime | None = None) -> str:
    value = value or utc_now_naive()
    return _aware_utc(value).astimezone(VN_TZ).isoformat()


def _parse_runtime_time(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value))
    except Exception:
        return None
    if parsed.tzinfo is None:
        return parsed
    return parsed.astimezone(timezone.utc).replace(tzinfo=None)


def _runtime_payload(job: Any) -> tuple[dict[str, Any], dict[str, Any]]:
    payload = dict(getattr(job, 'result_json', None) or {})
    runtime = dict(payload.get('_runtime') or {})
    return payload, runtime


def touch_job_runtime(
    job: Any,
    *,
    current: int | None = None,
    total: int | None = None,
    label: str | None = None,
    phase: str | None = None,
    now: datetime | None = None,
    force_progress_changed: bool = False,
) -> None:
    """Persist a durable heartbeat separately from real progress.

    ``updated_at`` is intentionally not treated as proof of progress. The
    production ghost job from 2026-09-14 showed that another code path may touch
    ``updated_at`` while the actual task no longer exists in Celery.
    """
    now = now or utc_now_naive()
    previous_current = int(getattr(job, 'progress_current', 0) or 0)
    previous_total = int(getattr(job, 'progress_total', 100) or 100)
    previous_label = str(getattr(job, 'progress_label', '') or '')
    payload, runtime = _runtime_payload(job)
    previous_phase = str(runtime.get('phase') or '')

    if current is not None:
        job.progress_current = int(current)
    if total is not None:
        job.progress_total = int(total)
    if label is not None:
        job.progress_label = str(label)[:255]

    changed = force_progress_changed
    if current is not None and int(current) != previous_current:
        changed = True
    if total is not None and int(total) != previous_total:
        changed = True
    if label is not None and str(label) != previous_label:
        changed = True
    if phase is not None and str(phase) != previous_phase:
        changed = True

    runtime['heartbeat_at'] = vn_iso(now)
    runtime.setdefault('started_at', vn_iso(getattr(job, 'started_at', None) or now))
    if changed or not runtime.get('progress_changed_at'):
        runtime['progress_changed_at'] = vn_iso(now)
    if phase is not None:
        runtime['phase'] = str(phase)
    runtime['progress_current'] = int(getattr(job, 'progress_current', 0) or 0)
    runtime['progress_total'] = int(getattr(job, 'progress_total', 100) or 100)
    runtime['progress_label'] = str(getattr(job, 'progress_label', '') or '')

    payload['_runtime'] = runtime
    job.result_json = json_safe_value(payload)
    job.updated_at = now


def _mark_failed(job: Any, *, code: str, message: str, now: datetime | None = None) -> None:
    now = now or utc_now_naive()
    payload, runtime = _runtime_payload(job)
    runtime['failed_at'] = vn_iso(now)
    runtime['failure_code'] = code
    payload['_runtime'] = runtime
    payload['ok'] = False
    payload['code'] = code
    payload['message'] = message
    job.status = 'failed'
    job.error_message = message[:4000]
    job.progress_label = message[:255]
    job.result_json = json_safe_value(payload)
    job.finished_at = now
    job.updated_at = now


def _job_health_failure(
    job: Any,
    *,
    now: datetime,
    heartbeat_timeout_seconds: int,
    progress_stall_seconds: int,
    max_runtime_seconds: int,
) -> tuple[str, str] | None:
    started_at = getattr(job, 'started_at', None) or getattr(job, 'created_at', None)
    if started_at and (now - started_at).total_seconds() > max(1, int(max_runtime_seconds)):
        return (
            JOB_RUNTIME_EXCEEDED,
            'Tác vụ vượt thời gian chạy tối đa và đã được watchdog kết thúc.',
        )

    _payload, runtime = _runtime_payload(job)
    heartbeat_at = _parse_runtime_time(runtime.get('heartbeat_at'))
    progress_changed_at = _parse_runtime_time(runtime.get('progress_changed_at'))

    # Legacy rows have no _runtime payload. Use started_at as the conservative
    # progress baseline; never use updated_at as the only liveness signal.
    if heartbeat_at is None:
        heartbeat_at = started_at
    if progress_changed_at is None:
        progress_changed_at = started_at

    if heartbeat_at and (now - heartbeat_at).total_seconds() > max(1, int(heartbeat_timeout_seconds)):
        return (
            WORKER_HEARTBEAT_LOST,
            'Worker không còn heartbeat; tác vụ đã được đánh dấu thất bại để tránh treo vô hạn.',
        )
    if progress_changed_at and (now - progress_changed_at).total_seconds() > max(1, int(progress_stall_seconds)):
        return (
            JOB_PROGRESS_STALLED,
            'Tác vụ còn trạng thái chạy nhưng tiến độ không thay đổi quá lâu; watchdog đã kết thúc tác vụ.',
        )
    return None


def reconcile_teacher_report_watchdog(db, *, now: datetime | None = None) -> dict[str, int]:
    now = now or utc_now_naive()
    teacher_failed = 0
    parent_failed = 0

    rows = db.query(AcademicTeacherReportJob).filter(
        AcademicTeacherReportJob.status.in_(['queued', 'running']),
    ).all()
    for job in rows:
        request = job.request_json if isinstance(job.request_json, dict) else {}
        teacher_id = str(request.get('teacher_id') or '').strip()
        class_id = str(request.get('class_id') or '').strip()
        management_scope = not teacher_id and not class_id

        if str(job.status) == 'queued' and job.started_at is None:
            queued_age = (now - (job.created_at or now)).total_seconds()
            if queued_age > 15 * 60:
                _mark_failed(
                    job,
                    code=WORKER_HEARTBEAT_LOST,
                    message='Tác vụ không được worker nhận trong 15 phút; đã hủy trạng thái chờ.',
                    now=now,
                )
                teacher_failed += 1
            continue

        if management_scope:
            failure = _job_health_failure(
                job,
                now=now,
                heartbeat_timeout_seconds=10 * 60,
                progress_stall_seconds=10 * 60,
                max_runtime_seconds=20 * 60,
            )
        else:
            failure = _job_health_failure(
                job,
                now=now,
                heartbeat_timeout_seconds=15 * 60,
                progress_stall_seconds=30 * 60,
                max_runtime_seconds=100 * 60,
            )
        if failure:
            _mark_failed(job, code=failure[0], message=failure[1], now=now)
            teacher_failed += 1

    parents = db.query(AcademicBulkOperationJob).filter(
        AcademicBulkOperationJob.job_type == DAILY_PARENT_JOB_TYPE,
        AcademicBulkOperationJob.status.in_(['queued', 'running']),
    ).all()
    for job in parents:
        if str(job.status) == 'queued' and job.started_at is None:
            if (now - (job.created_at or now)).total_seconds() > 15 * 60:
                _mark_failed(
                    job,
                    code=WORKER_HEARTBEAT_LOST,
                    message='Daily score/report parent không được worker nhận trong 15 phút.',
                    now=now,
                )
                parent_failed += 1
            continue
        failure = _job_health_failure(
            job,
            now=now,
            heartbeat_timeout_seconds=5 * 60,
            progress_stall_seconds=90 * 60,
            max_runtime_seconds=6 * 60 * 60,
        )
        if failure:
            _mark_failed(job, code=failure[0], message=failure[1], now=now)
            parent_failed += 1

    if teacher_failed or parent_failed:
        db.commit()
    return {'teacher_failed': teacher_failed, 'parent_failed': parent_failed}


def _scheduler_user() -> UserContext:
    return UserContext(
        user_id=SCHEDULER_ACTOR,
        username=SCHEDULER_ACTOR,
        email=None,
        role='admin',
        permissions=set(),
        course_ids=None,
        raw_claims={
            'ai_system_admin': True,
            'source': 'daily_score_report_pipeline',
            'timezone': 'Asia/Ho_Chi_Minh',
        },
    )


def _daily_run_for_date(db, *, term_id: str, branch: str, run_date: str) -> AcademicBulkOperationJob | None:
    candidates = db.query(AcademicBulkOperationJob).filter(
        AcademicBulkOperationJob.job_type == DAILY_PARENT_JOB_TYPE,
        AcademicBulkOperationJob.term_id == term_id,
        func.lower(func.coalesce(AcademicBulkOperationJob.branch, '')) == str(branch or '').lower(),
    ).order_by(AcademicBulkOperationJob.created_at.desc()).limit(12).all()
    for item in candidates:
        request = item.request_json if isinstance(item.request_json, dict) else {}
        if str(request.get('run_date_vn') or '') == run_date:
            return item
    return None


def _enqueue_task(celery_app, name: str, args: list[Any], *, queue: str, countdown: int | None = None) -> str:
    options: dict[str, Any] = {'queue': queue}
    if countdown is not None:
        options['countdown'] = max(0, int(countdown))
    result = celery_app.send_task(name, args=args, **options)
    return str(getattr(result, 'id', '') or '')


def _continuation_publisher(celery_app):
    def publish(*, task_name: str, args: list[Any], queue: str, countdown: int):
        return celery_app.send_task(
            task_name,
            args=args,
            queue=queue,
            countdown=countdown,
        )

    return publish


def _publish_daily_parent_continuation(
    celery_app,
    db,
    parent: AcademicBulkOperationJob,
    *,
    countdown: int,
) -> str:
    return publish_parent_continuation(
        db,
        parent,
        publisher=_continuation_publisher(celery_app),
        task_name='academic_daily_score_report_parent_task',
        args=[str(parent.id)],
        queue='sync-bulk',
        countdown=countdown,
    )


def recover_daily_score_report_continuations(celery_app) -> dict[str, Any]:
    db = SessionLocal()
    try:
        return recover_due_parent_continuations(
            db,
            publisher=_continuation_publisher(celery_app),
            job_types={DAILY_PARENT_JOB_TYPE, 'ap_daily_pipeline'},
            max_attempts=5,
            max_runtime_seconds=6 * 60 * 60,
        )
    finally:
        db.close()


def _daily_score_children(db, parent: AcademicBulkOperationJob, state: dict[str, Any]) -> list[AcademicClassSyncJob]:
    tracked_ids = {
        str(value)
        for value in (state.get('child_job_ids_by_class') or {}).values()
        if value
    }
    filters = [AcademicClassSyncJob.parent_job_id == parent.id]
    if tracked_ids:
        filters.append(AcademicClassSyncJob.id.in_(tracked_ids))
    return (
        db.query(AcademicClassSyncJob)
        .filter(or_(*filters))
        .order_by(AcademicClassSyncJob.created_at.desc())
        .all()
    )


def _dispatch_daily_score_window(celery_app, db, parent: AcademicBulkOperationJob, state: dict[str, Any]):
    target_class_ids = list(dict.fromkeys(
        str(item)
        for item in (state.get('target_class_ids') or [])
        if str(item)
    ))
    children = _daily_score_children(db, parent, state)
    stale = reconcile_stale_rows(
        children,
        now=utc_now_naive(),
        queued_timeout_seconds=class_sync_queued_timeout_seconds(),
        running_timeout_seconds=int(settings.academic_class_sync_stale_seconds),
    )
    if stale:
        db.add_all(stale)
        db.commit()
        children = _daily_score_children(db, parent, state)
    child_ids_by_class = {
        str(key): str(value)
        for key, value in (state.get('child_job_ids_by_class') or {}).items()
        if key and value
    }
    for child in children:
        child_ids_by_class.setdefault(str(child.class_id), str(child.id))
    plan = plan_batch_dispatch(
        target_class_ids,
        children,
        window=int(settings.academic_bulk_sync_dispatch_window),
    )
    request = parent.request_json if isinstance(parent.request_json, dict) else {}
    requester_context = request.get('requester_context') if isinstance(request.get('requester_context'), dict) else {}
    max_students = max(1000, min(int(request.get('limit') or getattr(settings, 'academic_class_sync_max_students', 5000) or 5000), 20000))
    enqueue_failed = int(state.get('enqueue_failed_count') or 0)
    queued_count = int(state.get('queued_count') or 0)
    reused_count = int(state.get('reused_count') or 0)

    for class_id in plan.dispatch_class_ids:
        active = db.query(AcademicClassSyncJob).filter(
            AcademicClassSyncJob.class_id == class_id,
            AcademicClassSyncJob.job_type == 'learning_sync',
            AcademicClassSyncJob.status.in_(['queued', 'running']),
        ).order_by(AcademicClassSyncJob.created_at.desc()).first()
        if active:
            child_ids_by_class[class_id] = str(active.id)
            reused_count += 1
            continue
        child = AcademicClassSyncJob(
            job_type='learning_sync',
            status='queued',
            class_id=class_id,
            parent_job_id=str(parent.id),
            requested_by=SCHEDULER_ACTOR,
            force=True,
            limit=max_students,
            progress_current=0,
            progress_total=100,
            progress_label='05:00 +07 · đang chờ cập nhật điểm CMS',
            request_json=json_safe_value({
                'force': True,
                'limit': max_students,
                'scheduled': True,
                'schedule_timezone': 'Asia/Ho_Chi_Minh',
                'schedule_time': '05:00',
                'daily_parent_job_id': str(parent.id),
                'requester_context': requester_context,
                'approved_class_id': class_id,
            }),
            result_json={},
        )
        db.add(child)
        db.commit()
        db.refresh(child)
        child_ids_by_class[class_id] = str(child.id)
        try:
            celery_task_id = _enqueue_task(celery_app, 'academic_class_sync_task', [child.id], queue='sync-bulk')
            child.result_json = json_safe_value({
                'daily_enqueue': {'celery_task_id': celery_task_id, 'enqueued_at': vn_iso()},
            })
            child.updated_at = utc_now_naive()
            db.add(child)
            db.commit()
            queued_count += 1
        except Exception as exc:
            child.status = 'failed'
            child.error_message = 'Không đưa được job cập nhật điểm 05:00 vào Celery.'
            child.progress_label = 'Xếp hàng cập nhật điểm thất bại'
            child.result_json = json_safe_value({'ok': False, 'error_type': exc.__class__.__name__})
            child.finished_at = utc_now_naive()
            child.updated_at = child.finished_at
            db.add(child)
            db.commit()
            enqueue_failed += 1

    state.update({
        'child_job_ids_by_class': child_ids_by_class,
        'child_job_ids': list(child_ids_by_class.values()),
        'target_class_count': len(target_class_ids),
        'enqueue_failed_count': enqueue_failed,
        'queued_count': queued_count,
        'reused_count': reused_count,
        'dispatch_window': int(settings.academic_bulk_sync_dispatch_window),
    })
    children = _daily_score_children(db, parent, state)
    plan = plan_batch_dispatch(
        target_class_ids,
        children,
        window=int(settings.academic_bulk_sync_dispatch_window),
    )
    return children, plan


def start_daily_score_report_pipeline(celery_app) -> dict[str, Any]:
    """Create one durable 05:00 parent per active term/branch.

    The parent owns child ``learning_sync`` jobs and does not publish Excel until
    every child reaches a terminal state. This replaces the legacy fire-and-forget
    scheduler that returned immediately after enqueueing class jobs.
    """
    db = SessionLocal()
    now = utc_now_naive()
    local_now = _aware_utc(now).astimezone(VN_TZ)
    run_date_vn = local_now.date().isoformat()
    created_parent_ids: list[str] = []
    reused_parent_ids: list[str] = []
    try:
        terms = db.query(AcademicTerm).filter(AcademicTerm.active.is_(True)).order_by(AcademicTerm.start_date.desc().nullslast()).all()
        for term in terms:
            branch = str(term.branch or 'poly').strip().lower() or 'poly'
            parent_key = scheduled_parent_key(
                'score-report-daily',
                run_date_vn=run_date_vn,
                term_id=str(term.id),
                branch=branch,
            )
            existing = db.query(AcademicBulkOperationJob).filter(
                AcademicBulkOperationJob.idempotency_key == parent_key,
            ).one_or_none()
            if existing is None:
                existing = _daily_run_for_date(
                    db,
                    term_id=str(term.id),
                    branch=branch,
                    run_date=run_date_vn,
                )
                if existing is not None and not existing.idempotency_key:
                    existing.idempotency_key = parent_key
                    db.add(existing)
                    db.commit()
            if existing:
                reused_parent_ids.append(str(existing.id))
                if existing.status in {'queued', 'running'}:
                    _publish_daily_parent_continuation(
                        celery_app,
                        db,
                        existing,
                        countdown=5,
                    )
                continue

            classes = db.query(AcademicClass).filter(
                AcademicClass.active.is_(True),
                AcademicClass.term_id == str(term.id),
                func.lower(func.coalesce(AcademicClass.branch, branch)) == branch,
            ).order_by(AcademicClass.id.asc()).all()
            if not classes:
                continue

            parent, created = create_or_load_scheduled_parent(
                db,
                idempotency_key=parent_key,
                values={
                    'job_type': DAILY_PARENT_JOB_TYPE,
                    'status': 'running',
                    'term_id': str(term.id),
                    'branch': branch,
                    'campus': None,
                    'requested_by': SCHEDULER_ACTOR,
                    'progress_current': 1,
                    'progress_total': 100,
                    'progress_label': '05:00 +07 · đang xếp hàng cập nhật điểm CMS',
                    'request_json': json_safe_value({
                        'scheduled': True,
                        'schedule_time': '05:00',
                        'schedule_timezone': 'Asia/Ho_Chi_Minh',
                        'run_date_vn': run_date_vn,
                        'term_id': str(term.id),
                        'branch': branch,
                    }),
                    'result_json': {},
                    'started_at': now,
                    'updated_at': now,
                },
            )
            if not created:
                reused_parent_ids.append(str(parent.id))
                if parent.status in {'queued', 'running'}:
                    _publish_daily_parent_continuation(
                        celery_app,
                        db,
                        parent,
                        countdown=5,
                    )
                continue
            touch_job_runtime(parent, current=1, label=parent.progress_label, phase='dispatching', now=now, force_progress_changed=True)

            class_ids = [str(cls.id) for cls in classes]
            requester_context = {
                'user_id': SCHEDULER_ACTOR,
                'username': SCHEDULER_ACTOR,
                'role': 'admin',
                'permissions': [],
                'authenticated_admin_claims': {'ai_system_admin': True},
            }
            max_students = max(1000, min(int(getattr(settings, 'academic_class_sync_max_students', 5000) or 5000), 20000))
            parent = db.get(AcademicBulkOperationJob, parent.id)
            parent.request_json = json_safe_value({
                **(parent.request_json or {}),
                'approved_class_ids': class_ids,
                'requester_context': requester_context,
                'limit': max_students,
            })
            parent_result = dict(parent.result_json or {})
            parent_result.update({
                'phase': 'waiting_children',
                'daily_score_report_pipeline': True,
                'run_date_vn': run_date_vn,
                'target_class_ids': class_ids,
                'target_class_count': len(class_ids),
                'terminal_count': 0,
                'enqueue_failed_count': 0,
                'report_job_ids': [],
                'skipped_report_scopes': [],
            })
            children, plan = _dispatch_daily_score_window(
                celery_app,
                db,
                parent,
                parent_result,
            )
            parent.result_json = json_safe_value(parent_result)
            touch_job_runtime(
                parent,
                current=5,
                label=(
                    f'05:00 +07 · đã xếp {len(children)}/{len(class_ids)} lớp; '
                    f'tối đa {plan.window} lớp đang chạy/chờ'
                ),
                phase='waiting_children',
                force_progress_changed=True,
            )
            db.add(parent)
            db.commit()
            _publish_daily_parent_continuation(
                celery_app,
                db,
                parent,
                countdown=15,
            )
            created_parent_ids.append(str(parent.id))

        return {
            'ok': True,
            'timezone': 'Asia/Ho_Chi_Minh',
            'schedule': '05:00',
            'run_date_vn': run_date_vn,
            'created_parent_ids': created_parent_ids,
            'reused_parent_ids': reused_parent_ids,
        }
    finally:
        db.close()


def _scope_class_ids(db, *, term_id: str, branch: str, campus: str | None) -> set[str]:
    query = db.query(AcademicClass.id).filter(
        AcademicClass.active.is_(True),
        AcademicClass.term_id == term_id,
        func.lower(func.coalesce(AcademicClass.branch, branch)) == branch,
    )
    if campus:
        query = query.filter(func.lower(func.coalesce(AcademicClass.campus, '')) == campus.lower())
    return {str(row[0]) for row in query.all()}


def _create_scheduled_export_job(
    db,
    celery_app,
    *,
    parent: AcademicBulkOperationJob,
    campus: str | None,
    source_synced_at: datetime,
    request_overrides: dict[str, Any] | None = None,
) -> AcademicTeacherReportJob:
    request = {
        'term_id': str(parent.term_id),
        'branch': str(parent.branch or 'poly'),
        'campus': campus,
        'learning_platform': 'cms',
        'teacher_id': None,
        'class_id': None,
        'scheduled': True,
        'management_scope': True,
        'source_sync_parent_id': str(parent.id),
        'source_synced_at': vn_iso(source_synced_at),
        'schedule_timezone': 'Asia/Ho_Chi_Minh',
        'scope': 'campus' if campus else 'ho',
        'requester_context': {
            'user_id': SCHEDULER_ACTOR,
            'username': SCHEDULER_ACTOR,
            'role': 'admin',
            'permissions': [],
            'authenticated_admin_claims': {'ai_system_admin': True},
        },
        'scope_enforced_by_backend': True,
    }
    if request_overrides:
        request.update(json_safe_value(request_overrides))
    job = AcademicTeacherReportJob(
        job_type=SCHEDULED_EXPORT_JOB_TYPE,
        status='queued',
        term_id=str(parent.term_id),
        branch=str(parent.branch or 'poly'),
        campus=campus,
        requested_by=SCHEDULER_ACTOR,
        progress_current=0,
        progress_total=100,
        progress_label='Đang chờ tạo file báo cáo tự động',
        request_json=json_safe_value(request),
        result_json={},
    )
    db.add(job)
    db.commit()
    db.refresh(job)
    try:
        task_id = _enqueue_task(celery_app, 'academic_teacher_report_job_task', [job.id], queue='exports')
        job.result_json = json_safe_value({'enqueue': {'celery_task_id': task_id, 'enqueued_at': vn_iso()}})
        job.updated_at = utc_now_naive()
        db.add(job)
        db.commit()
    except Exception as exc:
        _mark_failed(
            job,
            code='CELERY_ENQUEUE_FAILED',
            message='Không đưa được tác vụ tạo báo cáo tự động vào hàng đợi exports.',
        )
        payload = dict(job.result_json or {})
        payload['enqueue_error_type'] = exc.__class__.__name__
        job.result_json = json_safe_value(payload)
        db.add(job)
        db.commit()
    return job


def run_daily_score_report_parent(celery_app, parent_job_id: str) -> dict[str, Any]:
    db = SessionLocal()
    try:
        parent = db.query(AcademicBulkOperationJob).filter(
            AcademicBulkOperationJob.id == parent_job_id,
        ).with_for_update().one_or_none()
        if not parent:
            return {'ok': False, 'error': 'parent_not_found'}
        if parent.status not in {'queued', 'running'}:
            return parent.result_json or {'ok': parent.status == 'completed', 'status': parent.status}

        now = utc_now_naive()
        parent.status = 'running'
        parent.started_at = parent.started_at or now
        confirm_parent_continuation(db, parent, now=now)
        state = dict(parent.result_json or {})
        phase = str(state.get('phase') or 'waiting_children')

        if phase in {'dispatching', 'waiting_children'}:
            children, plan = _dispatch_daily_score_window(celery_app, db, parent, state)
            completed = [item for item in children if item.status == 'completed']
            failed = [item for item in children if item.status == 'failed']
            terminal_count = plan.terminal_count
            target_count = plan.target_count
            previous_terminal = int(state.get('terminal_count') or 0)
            state['terminal_count'] = terminal_count
            state['completed_class_count'] = len(completed)
            state['failed_class_count'] = len(failed)
            state['failed_class_ids'] = [str(item.class_id) for item in failed]
            state['active_class_count'] = plan.active_count
            state['dispatch_window'] = plan.window
            parent.result_json = json_safe_value(state)

            if not plan.finished:
                progress = min(64, 5 + int((terminal_count / max(1, target_count)) * 59))
                touch_job_runtime(
                    parent,
                    current=progress,
                    label=(
                        f'05:00 +07 · cập nhật điểm xong {terminal_count}/{target_count} lớp; '
                        f'{plan.active_count} đang chạy/chờ (tối đa {plan.window})'
                    ),
                    phase='waiting_children',
                    force_progress_changed=terminal_count != previous_terminal,
                )
                db.add(parent)
                db.commit()
                _publish_daily_parent_continuation(
                    celery_app,
                    db,
                    parent,
                    countdown=30,
                )
                return {'ok': True, 'status': 'running', 'terminal_count': terminal_count, 'target_count': target_count}

            source_synced_at = max(
                [item.finished_at for item in children if item.finished_at] or [now]
            )
            target_class_ids = {str(item) for item in (state.get('target_class_ids') or []) if str(item)}
            failed_class_ids = {str(item.class_id) for item in failed}
            campuses = sorted({
                str(value or '').strip().lower()
                for (value,) in db.query(AcademicClass.campus).filter(
                    AcademicClass.id.in_(target_class_ids),
                ).all()
                if str(value or '').strip()
            }) if target_class_ids else []

            campus_report_job_ids: list[str] = []
            skipped_scopes: list[dict[str, Any]] = []
            for campus in campuses:
                scope_ids = _scope_class_ids(
                    db,
                    term_id=str(parent.term_id),
                    branch=str(parent.branch or 'poly'),
                    campus=campus,
                )
                failed_in_scope = sorted(scope_ids.intersection(failed_class_ids))
                if failed_in_scope:
                    skipped_scopes.append({
                        'scope': campus,
                        'failed_class_count': len(failed_in_scope),
                        'failed_class_ids': failed_in_scope[:50],
                        'reason': 'score_sync_failed',
                    })
                    continue
                export_job = _create_scheduled_export_job(
                    db,
                    celery_app,
                    parent=parent,
                    campus=campus,
                    source_synced_at=source_synced_at,
                )
                campus_report_job_ids.append(str(export_job.id))

            state = dict(parent.result_json or {})
            state.update({
                'phase': 'campus_reporting',
                'source_synced_at': vn_iso(source_synced_at),
                'campus_report_job_ids': campus_report_job_ids,
                'report_job_ids': list(campus_report_job_ids),
                'skipped_report_scopes': skipped_scopes,
            })
            parent.result_json = json_safe_value(state)
            touch_job_runtime(
                parent,
                current=70,
                label=f'Đã cập nhật điểm; đang tạo {len(campus_report_job_ids)} file báo cáo cơ sở',
                phase='campus_reporting',
                force_progress_changed=True,
            )
            db.add(parent)
            db.commit()
            _publish_daily_parent_continuation(
                celery_app,
                db,
                parent,
                countdown=30,
            )
            return {
                'ok': True,
                'status': 'campus_reporting',
                'campus_report_job_ids': campus_report_job_ids,
                'skipped_scopes': skipped_scopes,
            }

        if phase == 'campus_reporting':
            campus_report_job_ids = [
                str(item) for item in (state.get('campus_report_job_ids') or []) if str(item)
            ]
            campus_reports = (
                db.query(AcademicTeacherReportJob)
                .filter(AcademicTeacherReportJob.id.in_(campus_report_job_ids))
                .all()
                if campus_report_job_ids else []
            )
            completed_campus_reports = [item for item in campus_reports if item.status == 'completed']
            failed_campus_reports = [item for item in campus_reports if item.status == 'failed']
            terminal_count = len(completed_campus_reports) + len(failed_campus_reports)
            if terminal_count < len(campus_report_job_ids):
                progress = min(88, 70 + int((terminal_count / max(1, len(campus_report_job_ids))) * 18))
                touch_job_runtime(
                    parent,
                    current=progress,
                    label=f'Đang tạo Excel cơ sở: {terminal_count}/{len(campus_report_job_ids)} hoàn tất',
                    phase='campus_reporting',
                    force_progress_changed=terminal_count != int(state.get('campus_report_terminal_count') or 0),
                )
                state['campus_report_terminal_count'] = terminal_count
                parent.result_json = json_safe_value(state)
                db.add(parent)
                db.commit()
                _publish_daily_parent_continuation(
                    celery_app,
                    db,
                    parent,
                    countdown=30,
                )
                return {'ok': True, 'status': 'campus_reporting', 'campus_report_terminal_count': terminal_count}

            skipped_scopes = list(state.get('skipped_report_scopes') or [])
            if failed_campus_reports or skipped_scopes:
                state.update({
                    'phase': 'finished',
                    'report_completed_count': len(completed_campus_reports),
                    'report_failed_count': len(failed_campus_reports),
                    'artifact_job_ids': [str(item.id) for item in completed_campus_reports],
                    'finished_at': vn_iso(now),
                })
                parent.result_json = json_safe_value(state)
                parent.status = 'failed'
                parent.finished_at = now
                parent.error_message = (
                    'Không tạo báo cáo HO vì còn cơ sở lỗi cập nhật điểm hoặc lỗi tạo Excel.'
                )
                touch_job_runtime(
                    parent,
                    current=100,
                    label='Dừng trước báo cáo HO vì còn cơ sở thất bại',
                    phase='finished',
                    force_progress_changed=True,
                )
                db.add(parent)
                db.commit()
                return json_safe_value({'ok': False, **state})

            source_synced_at = _parse_runtime_time(state.get('source_synced_at')) or now
            # Persist the HO aggregation contract before publishing the task.
            # _create_scheduled_export_job() enqueues immediately, so mutating
            # request_json afterwards races a fast exports worker.
            ho_job = _create_scheduled_export_job(
                db,
                celery_app,
                parent=parent,
                campus=None,
                source_synced_at=source_synced_at,
                request_overrides={
                    'source_campus_report_job_ids': [
                        str(item.id) for item in completed_campus_reports
                    ],
                    'aggregate_after_campus_reports': True,
                },
            )
            state.update({
                'phase': 'ho_reporting',
                'ho_report_job_id': str(ho_job.id),
                'report_job_ids': [
                    *[str(item.id) for item in completed_campus_reports],
                    str(ho_job.id),
                ],
            })
            parent.result_json = json_safe_value(state)
            touch_job_runtime(
                parent,
                current=90,
                label='Excel các cơ sở đã xong; đang tổng hợp báo cáo HO',
                phase='ho_reporting',
                force_progress_changed=True,
            )
            db.add(parent)
            db.commit()
            _publish_daily_parent_continuation(
                celery_app,
                db,
                parent,
                countdown=30,
            )
            return {'ok': True, 'status': 'ho_reporting', 'ho_report_job_id': str(ho_job.id)}

        ho_report_job_id = str(state.get('ho_report_job_id') or '')
        ho_report = db.get(AcademicTeacherReportJob, ho_report_job_id) if ho_report_job_id else None
        if ho_report and ho_report.status in {'queued', 'running'}:
            touch_job_runtime(
                parent,
                current=95,
                label='Đang tổng hợp báo cáo HO sau các báo cáo cơ sở',
                phase='ho_reporting',
            )
            db.add(parent)
            db.commit()
            _publish_daily_parent_continuation(
                celery_app,
                db,
                parent,
                countdown=30,
            )
            return {'ok': True, 'status': 'ho_reporting'}

        report_job_ids = [str(item) for item in (state.get('report_job_ids') or []) if str(item)]
        reports = db.query(AcademicTeacherReportJob).filter(AcademicTeacherReportJob.id.in_(report_job_ids)).all() if report_job_ids else []
        completed_reports = [item for item in reports if item.status == 'completed']
        failed_reports = [item for item in reports if item.status == 'failed']
        state.update({
            'phase': 'finished',
            'report_completed_count': len(completed_reports),
            'report_failed_count': len(failed_reports),
            'artifact_job_ids': [str(item.id) for item in completed_reports],
            'finished_at': vn_iso(now),
        })
        parent.result_json = json_safe_value(state)
        parent.status = 'completed' if ho_report and ho_report.status == 'completed' and not failed_reports else 'failed'
        parent.finished_at = now
        parent.error_message = None if parent.status == 'completed' else 'Không tạo được báo cáo HO sau báo cáo cơ sở.'
        touch_job_runtime(
            parent,
            current=100,
            label=(
                f'Hoàn tất 05:00 +07 · {len(completed_reports)} file cơ sở/HO'
                if parent.status == 'completed'
                else 'Đợt 05:00 thất bại khi tổng hợp báo cáo HO'
            ),
            phase='finished',
            force_progress_changed=True,
        )
        db.add(parent)
        db.commit()
        return json_safe_value({'ok': parent.status == 'completed', **state})
    except ContinuationPublishError as exc:
        db.rollback()
        parent = db.get(AcademicBulkOperationJob, parent_job_id)
        return {
            'ok': False,
            'status': 'dispatch_pending',
            'parent_job_id': str(parent_job_id),
            'error': str(exc.original)[:500],
            'error_class': exc.original.__class__.__name__,
            'continuation': (
                (parent.result_json or {}).get('continuation')
                if parent and isinstance(parent.result_json, dict)
                else {}
            ),
        }
    except Exception as exc:
        db.rollback()
        parent = db.get(AcademicBulkOperationJob, parent_job_id)
        if parent:
            _mark_failed(
                parent,
                code='DAILY_SCORE_REPORT_PIPELINE_FAILED',
                message='Không thể hoàn tất pipeline cập nhật điểm và tạo báo cáo 05:00.',
            )
            payload = dict(parent.result_json or {})
            payload['exception_class'] = exc.__class__.__name__
            parent.result_json = json_safe_value(payload)
            db.add(parent)
            db.commit()
        raise
    finally:
        db.close()


def _job_request(job: AcademicTeacherReportJob) -> dict[str, Any]:
    return job.request_json if isinstance(job.request_json, dict) else {}


def _write_teacher_report_file(
    db,
    job: AcademicTeacherReportJob,
    *,
    service: AcademicService,
    user: UserContext,
    scheduled: bool,
) -> dict[str, Any]:
    from app.api.routes.academic import _write_training_teacher_report_xlsx

    request = _job_request(job)
    term_id = str(job.term_id or request.get('term_id') or '')
    branch = str(job.branch or request.get('branch') or 'poly').strip().lower() or 'poly'
    campus = str(job.campus or request.get('campus') or '').strip().lower() or None
    teacher_id = str(request.get('teacher_id') or '').strip() or None
    class_id = str(request.get('class_id') or '').strip() or None
    learning_platform = str(request.get('learning_platform') or 'cms').strip().lower() or 'cms'
    management_scope = not teacher_id and not class_id

    if job.job_type == 'export_excel' and management_scope:
        raise RuntimeError(
            f'{MANAGEMENT_REPORT_PREBUILT_ONLY}: Báo cáo HO/cơ sở chỉ được tải từ file 05:00 đã tạo sẵn.'
        )

    refresh_result = None
    if not management_scope and learning_platform == 'cms':
        # Teacher/class export intentionally keeps the existing live-refresh flow.
        touch_job_runtime(
            job,
            current=15,
            label='Đang lấy điểm CMS mới nhất cho Excel giảng viên/lớp',
            phase='refreshing_cms',
            force_progress_changed=True,
        )
        db.add(job)
        db.commit()

        def progress(done: int, total: int, label: str) -> None:
            current = 15 if not total else min(60, 15 + int((done / max(1, total)) * 45))
            current_job = db.get(AcademicTeacherReportJob, job.id)
            if not current_job or current_job.status not in {'queued', 'running'}:
                raise RuntimeError('Teacher report job was cancelled by watchdog.')
            touch_job_runtime(current_job, current=current, label=label, phase='refreshing_cms')
            db.add(current_job)
            db.commit()

        refresh_result = service.refresh_training_teacher_learning_data(
            user,
            term_id=term_id,
            branch=branch,
            campus=campus,
            learning_platform='cms',
            class_id=class_id,
            strict=True,
            progress_callback=progress,
            max_snapshot_age_seconds=0,
        )

    # Management scope reaches this point only for the scheduled 05:00 artifact.
    # It reads PostgreSQL snapshots/cache only and NEVER calls CMS/Open edX.
    if scheduled and management_scope:
        touch_job_runtime(
            job,
            current=25,
            label='Đang tính cache báo cáo từ dữ liệu 05:00 đã đồng bộ',
            phase='building_cache',
            force_progress_changed=True,
        )
        db.add(job)
        db.commit()
        service.rebuild_training_teacher_report_cache(
            user,
            term_id=term_id,
            branch=branch,
            campus=campus,
            source_sync_run_id=str(request.get('source_sync_parent_id') or '') or None,
        )

    touch_job_runtime(
        job,
        current=60 if scheduled else 65,
        label='Đang dựng file Excel từ dữ liệu đã lưu',
        phase='building_excel',
        force_progress_changed=True,
    )
    db.add(job)
    db.commit()

    report = service.training_teacher_report(
        user,
        term_id=term_id,
        branch=branch,
        campus=campus,
        search=request.get('search'),
        learning_status=request.get('learning_status'),
        learning_platform=learning_platform,
        teacher_id=teacher_id,
        class_id=class_id,
        page=1,
        page_size=200,
        include_all=True,
        include_students=True,
        use_cache=False,
    )
    report['learning_refresh'] = json_safe_value(refresh_result) if refresh_result else None

    term = db.get(AcademicTerm, term_id) if term_id else None
    term_code = str(getattr(term, 'term_code', None) or getattr(term, 'term_name', None) or term_id or 'term')
    safe_term = ''.join(char if char.isalnum() or char in {'-', '_'} else '-' for char in term_code)
    safe_branch = ''.join(char if char.isalnum() or char in {'-', '_'} else '-' for char in branch)
    local_date = _aware_utc(utc_now_naive()).astimezone(VN_TZ).strftime('%Y%m%d')
    if scheduled:
        scope_label = (campus or 'HO').upper()
        safe_scope = ''.join(char if char.isalnum() or char in {'-', '_'} else '-' for char in scope_label)
        filename = f'teacher-report-{safe_term}-{safe_branch}-{safe_scope}-{local_date}.xlsx'
        storage_key = f'teacher-report-snapshots/{term_id}/{safe_branch}/{local_date}/{safe_scope}/{filename}'
    elif class_id:
        cls = db.get(AcademicClass, class_id)
        safe_class = str(getattr(cls, 'class_code', None) or class_id).replace('/', '-').replace(' ', '-')
        filename = f'class-report-{safe_class}-{job.id[:8]}.xlsx'
        storage_key = f'teacher-reports/{filename}'
    else:
        safe_teacher = teacher_id or 'teacher'
        filename = f'teacher-report-{safe_teacher}-{job.id[:8]}.xlsx'
        storage_key = f'teacher-reports/{filename}'

    tmp_dir = Path(tempfile.mkdtemp())
    path = tmp_dir / filename
    try:
        _write_training_teacher_report_xlsx(report, path)
        raw = path.read_bytes()
        storage_ref = get_object_storage().put_bytes(
            storage_key,
            raw,
            content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        )
    finally:
        try:
            path.unlink(missing_ok=True)
        except Exception:
            pass
        try:
            tmp_dir.rmdir()
        except Exception:
            pass

    generated_at = vn_iso()
    source_synced_at = request.get('source_synced_at') if scheduled else generated_at
    return {
        'ok': True,
        'scheduled': scheduled,
        'management_scope': management_scope,
        'scope': request.get('scope') if scheduled else ('class' if class_id else 'teacher'),
        'term_id': term_id,
        'branch': branch,
        'campus': campus,
        'file_name': filename,
        'storage_ref': storage_ref,
        'bytes': len(raw),
        'summary': report.get('summary') or {},
        'learning_refresh': refresh_result,
        'generated_at': generated_at,
        'source_synced_at': source_synced_at,
        'timezone': 'Asia/Ho_Chi_Minh',
    }


def run_teacher_report_job(job_id: str) -> dict[str, Any]:
    db = SessionLocal()
    try:
        job = db.query(AcademicTeacherReportJob).filter(
            AcademicTeacherReportJob.id == job_id,
        ).with_for_update().one_or_none()
        if not job:
            return {'ok': False, 'error': 'job_not_found'}
        if job.status not in {'queued', 'running'}:
            return job.result_json or {'ok': job.status == 'completed', 'status': job.status}

        request = _job_request(job)
        now = utc_now_naive()
        job.status = 'running'
        job.started_at = job.started_at or now
        touch_job_runtime(job, current=max(5, int(job.progress_current or 0)), label='Đang chuẩn bị báo cáo', phase='starting', now=now, force_progress_changed=True)
        db.add(job)
        db.commit()

        user = _scheduler_user() if bool(request.get('scheduled')) else UserContext(
            user_id=str((request.get('requester_context') or {}).get('user_id') or job.requested_by or 'teacher-report-worker'),
            username=str((request.get('requester_context') or {}).get('username') or job.requested_by or 'teacher-report-worker'),
            email=(request.get('requester_context') or {}).get('email'),
            role=str((request.get('requester_context') or {}).get('role') or 'viewer'),
            permissions={str(item) for item in ((request.get('requester_context') or {}).get('permissions') or [])},
            course_ids=(request.get('requester_context') or {}).get('course_ids'),
            raw_claims={
                **({key: True for key, value in ((request.get('requester_context') or {}).get('authenticated_admin_claims') or {}).items() if value is True}),
                'source': 'daily_teacher_report_runtime',
                'job_id': job.id,
            },
        )
        service = AcademicService(db)

        if job.job_type == 'rebuild_cache':
            # Manual "Làm mới dữ liệu" is local-only now: no CMS call.
            result = service.rebuild_training_teacher_report_cache(
                user,
                term_id=str(job.term_id or request.get('term_id') or ''),
                branch=job.branch or request.get('branch'),
                campus=job.campus or request.get('campus'),
                source_sync_run_id=None,
            )
            result = {**(result or {}), 'cms_refreshed': False, 'timezone': 'Asia/Ho_Chi_Minh'}
            job.file_path = None
            job.file_name = None
            final_label = 'Đã tính lại báo cáo từ dữ liệu đã lưu; không gọi CMS'
        elif job.job_type in {'export_excel', SCHEDULED_EXPORT_JOB_TYPE}:
            result = _write_teacher_report_file(
                db,
                job,
                service=service,
                user=user,
                scheduled=job.job_type == SCHEDULED_EXPORT_JOB_TYPE,
            )
            job.file_path = result.get('storage_ref')
            job.file_name = result.get('file_name')
            final_label = (
                'Đã tạo file báo cáo 05:00 từ dữ liệu đã đồng bộ'
                if job.job_type == SCHEDULED_EXPORT_JOB_TYPE
                else 'Đã xuất Excel giảng viên/lớp từ điểm CMS mới nhất'
            )
        else:
            raise RuntimeError(f'Unsupported teacher report job_type: {job.job_type}')

        job = db.get(AcademicTeacherReportJob, job_id)
        if not job or job.status not in {'queued', 'running'}:
            return {'ok': False, 'status': getattr(job, 'status', 'missing'), 'watchdog_cancelled': True}
        job.status = 'completed'
        job.progress_current = 100
        job.progress_total = 100
        job.progress_label = final_label[:255]
        payload = dict(result or {})
        existing_runtime = dict((job.result_json or {}).get('_runtime') or {}) if isinstance(job.result_json, dict) else {}
        payload['_runtime'] = existing_runtime
        job.result_json = json_safe_value(payload)
        job.error_message = None
        job.finished_at = utc_now_naive()
        touch_job_runtime(job, current=100, label=job.progress_label, phase='finished', force_progress_changed=True)
        db.add(job)
        db.commit()
        return json_safe_value(result)
    except Exception as exc:
        db.rollback()
        job = db.get(AcademicTeacherReportJob, job_id)
        if job and job.status in {'queued', 'running'}:
            message = str(exc)
            code = 'ACADEMIC_TEACHER_REPORT_FAILED'
            if MANAGEMENT_REPORT_PREBUILT_ONLY in message:
                code = MANAGEMENT_REPORT_PREBUILT_ONLY
                public_message = 'Báo cáo HO/cơ sở chỉ tải file 05:00 đã tạo sẵn; thao tác này không tạo file mới.'
            else:
                public_message = 'Không thể hoàn tất báo cáo giáo viên. Vui lòng kiểm tra Nhật ký hoạt động.'
            _mark_failed(job, code=code, message=public_message)
            payload = dict(job.result_json or {})
            payload['exception_class'] = exc.__class__.__name__
            job.result_json = json_safe_value(payload)
            db.add(job)
            db.commit()
        raise
    finally:
        db.close()


def register_daily_teacher_report_tasks(celery_app) -> None:
    """Replace legacy task handlers while keeping their public task names.

    API code already enqueues ``academic_teacher_report_job_task`` by name. The
    worker entrypoint unregisters the legacy implementation and registers this
    implementation under the same name, so existing API contracts remain stable.
    """
    for task_name in ('academic_sync_all_student_scores_task', 'academic_teacher_report_job_task'):
        try:
            celery_app.tasks.unregister(task_name)
        except Exception:
            celery_app.tasks.pop(task_name, None)

    @celery_app.task(name='academic_sync_all_student_scores_task')
    def _daily_score_start_task():
        return start_daily_score_report_pipeline(celery_app)

    @celery_app.task(name='academic_daily_score_report_parent_task')
    def _daily_score_parent_task(parent_job_id: str):
        return run_daily_score_report_parent(celery_app, parent_job_id)

    @celery_app.task(name='academic_teacher_report_job_task')
    def _teacher_report_task(job_id: str):
        return run_teacher_report_job(job_id)

    @celery_app.task(name='academic_teacher_report_watchdog_task')
    def _teacher_report_watchdog_task():
        db = SessionLocal()
        try:
            return reconcile_teacher_report_watchdog(db)
        finally:
            db.close()

    @celery_app.task(name='academic_scheduled_parent_recovery_task')
    def _scheduled_parent_recovery_task():
        return recover_daily_score_report_continuations(celery_app)

    routes = dict(getattr(celery_app.conf, 'task_routes', {}) or {})
    routes.update({
        'academic_daily_score_report_parent_task': {'queue': 'sync-bulk'},
        'academic_teacher_report_watchdog_task': {'queue': 'sync-fast'},
        'academic_scheduled_parent_recovery_task': {'queue': 'sync-bulk'},
    })
    celery_app.conf.task_routes = routes

    annotations = dict(getattr(celery_app.conf, 'task_annotations', {}) or {})
    annotations.update({
        'academic_daily_score_report_parent_task': {'soft_time_limit': 120, 'time_limit': 180},
        'academic_teacher_report_watchdog_task': {'soft_time_limit': 45, 'time_limit': 55},
        'academic_scheduled_parent_recovery_task': {'soft_time_limit': 45, 'time_limit': 55},
    })
    celery_app.conf.task_annotations = annotations

    beat_schedule = dict(getattr(celery_app.conf, 'beat_schedule', {}) or {})
    beat_schedule['academic-teacher-report-watchdog'] = {
        'task': 'academic_teacher_report_watchdog_task',
        'schedule': 300,
    }
    beat_schedule['academic-scheduled-parent-recovery'] = {
        'task': 'academic_scheduled_parent_recovery_task',
        'schedule': 60,
    }
    celery_app.conf.beat_schedule = beat_schedule
