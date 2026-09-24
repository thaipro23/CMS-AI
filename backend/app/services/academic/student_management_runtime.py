from __future__ import annotations

import logging
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from fastapi import HTTPException
from sqlalchemy import func, or_
from sqlalchemy.exc import IntegrityError

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
    AcademicTerm,
)
from app.schemas.academic import AcademicAPSyncIn
from app.services.academic.ap_sync import AcademicAPSyncWorkflowService
from app.services.academic.batch_coordinator import plan_batch_dispatch
from app.services.academic.job_runtime import (
    class_sync_queued_timeout_seconds,
    reconcile_stale_rows,
)
from app.services.academic.scheduled_parent import (
    ContinuationPublishError,
    confirm_parent_continuation,
    create_or_load_scheduled_parent,
    publish_parent_continuation,
    scheduled_parent_key,
)
from app.services.academic.scheduled_scope import (
    ScheduledScopeError,
    freeze_scheduled_scope,
    scheduled_auto_map_contract,
    scheduled_auto_map_key,
)
from app.services.academic_service import AcademicService


logger = logging.getLogger(__name__)

SCHEDULER_ACTOR = 'academic-ap-scheduler'
LATEST_SCORE_JOB_TYPE = 'learning_refresh_filter'
LATEST_SCORE_TASK = 'academic_learning_refresh_filter_task'
LATEST_SCORE_WATCHDOG_TASK = 'academic_learning_refresh_filter_watchdog_task'
AP_03_TASK = 'academic_ap_03_schedule_task'
AP_03_FOLLOWUP_TASK = 'academic_ap_03_followup_task'
AP_03_PARENT_JOB_TYPE = 'ap_daily_pipeline'
AUTO_MAP_TASK = 'academic_subject_auto_map_all_sync_task'
CLASS_SYNC_TASK = 'academic_class_sync_task'


def _now() -> datetime:
    return datetime.utcnow()


def _ap_parent_publisher(celery_app):
    def publish(*, task_name: str, args: list[Any], queue: str, countdown: int):
        return celery_app.send_task(
            task_name,
            args=args,
            queue=queue,
            countdown=countdown,
        )

    return publish


def _publish_ap_followup(
    celery_app,
    db,
    parent: AcademicBulkOperationJob,
    run_id: str,
    *,
    countdown: int,
) -> str:
    return publish_parent_continuation(
        db,
        parent,
        publisher=_ap_parent_publisher(celery_app),
        task_name=AP_03_FOLLOWUP_TASK,
        args=[str(run_id)],
        queue='sync-bulk',
        countdown=countdown,
    )


def _publish_auto_map_job(
    celery_app,
    db,
    parent: AcademicBulkOperationJob,
    auto_map_job_id: str,
) -> str:
    return publish_parent_continuation(
        db,
        parent,
        publisher=_ap_parent_publisher(celery_app),
        task_name=AUTO_MAP_TASK,
        args=[str(auto_map_job_id)],
        queue='sync-bulk',
        countdown=0,
    )


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
            'source': 'academic_ap_03_scheduler',
        },
    )


def _scheduler_requester_context() -> dict[str, Any]:
    return {
        'user_id': SCHEDULER_ACTOR,
        'username': SCHEDULER_ACTOR,
        'email': None,
        'role': 'admin',
        'permissions': [],
        'course_ids': None,
        'authenticated_admin_claims': {'ai_system_admin': True},
    }


def _active_configured_terms(db) -> list[AcademicTerm]:
    rows = (
        db.query(AcademicTerm)
        .join(AcademicSubjectDelivery, AcademicSubjectDelivery.term_id == AcademicTerm.id)
        .filter(
            AcademicTerm.active.is_(True),
            AcademicSubjectDelivery.active.is_(True),
            AcademicSubjectDelivery.learning_platform.in_(['cms', 'udemy']),
        )
        .order_by(AcademicTerm.start_date.desc().nullslast(), AcademicTerm.created_at.desc())
        .all()
    )
    seen: set[str] = set()
    result: list[AcademicTerm] = []
    for term in rows:
        if term.id in seen:
            continue
        seen.add(term.id)
        result.append(term)
    return result


def _campus_codes_for_term(db, term: AcademicTerm, branch: str) -> list[str]:
    configured = [
        str(value).strip().lower()
        for (value,) in (
            db.query(AcademicCampus.campus_code)
            .filter(
                AcademicCampus.active.is_(True),
                func.lower(AcademicCampus.branch) == branch,
            )
            .order_by(AcademicCampus.sort_order.asc(), AcademicCampus.campus_code.asc())
            .all()
        )
        if str(value or '').strip()
    ]
    if configured:
        return list(dict.fromkeys(configured))

    # Defensive fallback for installations that already have AP classes but have
    # not yet populated the campus master table.
    existing = [
        str(value).strip().lower()
        for (value,) in (
            db.query(AcademicClass.campus)
            .filter(
                AcademicClass.active.is_(True),
                AcademicClass.term_id == term.id,
                func.lower(AcademicClass.branch) == branch,
                AcademicClass.campus.isnot(None),
            )
            .distinct()
            .order_by(AcademicClass.campus.asc())
            .all()
        )
        if str(value or '').strip()
    ]
    return list(dict.fromkeys(existing))


def _load_latest_score_children(db, parent: AcademicBulkOperationJob, state: dict[str, Any]) -> list[AcademicClassSyncJob]:
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


def _dispatch_latest_score_window(celery_app, db, parent: AcademicBulkOperationJob) -> tuple[dict[str, Any], Any]:
    request = parent.request_json if isinstance(parent.request_json, dict) else {}
    targets = list(dict.fromkeys(
        str(item).strip()
        for item in (request.get('approved_class_ids') or [])
        if str(item or '').strip()
    ))
    state = dict(parent.result_json or {}) if isinstance(parent.result_json, dict) else {}
    children = _load_latest_score_children(db, parent, state)
    stale = reconcile_stale_rows(
        children,
        now=_now(),
        queued_timeout_seconds=class_sync_queued_timeout_seconds(),
        running_timeout_seconds=int(settings.academic_class_sync_stale_seconds),
    )
    if stale:
        db.add_all(stale)
        db.commit()
        children = _load_latest_score_children(db, parent, state)

    child_ids_by_class = {
        str(key): str(value)
        for key, value in (state.get('child_job_ids_by_class') or {}).items()
        if key and value
    }
    for child in children:
        child_ids_by_class.setdefault(str(child.class_id), str(child.id))

    plan = plan_batch_dispatch(
        targets,
        children,
        window=int(settings.academic_bulk_sync_dispatch_window),
    )
    queued = int(state.get('queued') or 0)
    reused = int(state.get('reused') or 0)
    failed_to_enqueue = int(state.get('failed_to_enqueue') or 0)
    requester_context = request.get('requester_context') if isinstance(request.get('requester_context'), dict) else {}
    force = bool(request.get('force', True))
    limit = max(1, min(500, int(request.get('limit') or 500)))
    mode = request.get('mode')

    for class_id in plan.dispatch_class_ids:
        active = (
            db.query(AcademicClassSyncJob)
            .filter(
                AcademicClassSyncJob.class_id == class_id,
                AcademicClassSyncJob.job_type == 'learning_sync',
                AcademicClassSyncJob.status.in_(['queued', 'running']),
            )
            .order_by(AcademicClassSyncJob.created_at.desc())
            .first()
        )
        if active:
            child_ids_by_class[class_id] = str(active.id)
            reused += 1
            continue
        child = AcademicClassSyncJob(
            job_type='learning_sync',
            status='queued',
            class_id=class_id,
            parent_job_id=parent.id,
            idempotency_key=f'bulk:{parent.id}:learning_sync:{class_id}',
            requested_by=parent.requested_by,
            force=force,
            limit=limit,
            mode=mode,
            progress_current=0,
            progress_total=100,
            progress_label='Đang chờ lấy điểm CMS mới nhất',
            request_json=json_safe_value({
                'force': force,
                'limit': limit,
                'mode': mode,
                'requester_context': requester_context,
                'approved_class_id': class_id,
                'parent_job_id': parent.id,
                'parent_job_type': LATEST_SCORE_JOB_TYPE,
                'operation': 'latest_learning_scores_only',
            }),
            result_json={},
        )
        db.add(child)
        db.commit()
        db.refresh(child)
        child_ids_by_class[class_id] = str(child.id)
        try:
            celery_app.send_task(CLASS_SYNC_TASK, args=[child.id], queue='sync-bulk')
            queued += 1
        except Exception as exc:
            child.status = 'failed'
            child.progress_label = 'Không đưa được job lấy điểm vào hàng đợi'
            child.error_message = str(exc)[:4000]
            child.result_json = json_safe_value({'ok': False, 'message': child.progress_label})
            child.finished_at = _now()
            child.updated_at = _now()
            db.add(child)
            db.commit()
            failed_to_enqueue += 1

    state.update({
        'ok': True,
        'child_job_ids_by_class': child_ids_by_class,
        'child_job_ids': list(child_ids_by_class.values()),
        'class_total': len(targets),
        'queued': queued,
        'reused': reused,
        'failed_to_enqueue': failed_to_enqueue,
        'skipped_unmapped_count': int(request.get('skipped_unmapped_count') or 0),
        'operation': 'latest_learning_scores_only',
    })
    children = _load_latest_score_children(db, parent, state)
    plan = plan_batch_dispatch(
        targets,
        children,
        window=int(settings.academic_bulk_sync_dispatch_window),
    )
    state.update({
        'active': plan.active_count,
        'completed': plan.completed_count,
        'failed': plan.failed_count,
        'terminal': plan.terminal_count,
        'dispatch_window': plan.window,
    })
    return state, plan


def _persist_latest_score_progress(db, parent: AcademicBulkOperationJob, state: dict[str, Any], plan: Any) -> None:
    parent.progress_total = 100
    parent.updated_at = _now()
    if plan.finished:
        parent.progress_current = 100
        parent.finished_at = _now()
        if plan.completed_count > 0 or plan.target_count == 0:
            parent.status = 'completed'
            parent.progress_label = (
                f'Đã lấy điểm mới nhất cho {plan.completed_count}/{plan.target_count} lớp'
                + (f' · {plan.failed_count} lỗi' if plan.failed_count else '')
            )
            state['ok'] = True
        else:
            parent.status = 'failed'
            parent.progress_label = 'Không lớp nào lấy điểm thành công'
            parent.error_message = f'{plan.failed_count} job lỗi'[:4000]
            state['ok'] = False
    else:
        parent.status = 'running'
        parent.progress_current = min(
            99,
            10 + int((plan.terminal_count / max(plan.target_count, 1)) * 89),
        )
        parent.progress_label = (
            f'Đang lấy điểm: {plan.terminal_count}/{plan.target_count} lớp hoàn tất; '
            f'{plan.active_count} đang chạy/chờ (tối đa {plan.window})'
        )
    parent.result_json = json_safe_value(state)
    db.add(parent)
    db.commit()


def _enqueue_latest_score_children(celery_app, parent: AcademicBulkOperationJob) -> dict[str, Any]:
    db = SessionLocal()
    try:
        parent = db.get(AcademicBulkOperationJob, parent.id)
        if not parent:
            return {'ok': False, 'error': 'job_not_found'}
        if parent.job_type != LATEST_SCORE_JOB_TYPE:
            raise RuntimeError(f'Unsupported bulk job_type: {parent.job_type}')
        if parent.status not in {'queued', 'running'}:
            return parent.result_json or {'ok': parent.status == 'completed', 'status': parent.status}
        parent.status = 'running'
        parent.started_at = parent.started_at or _now()
        parent.updated_at = _now()
        db.add(parent)
        db.commit()

        state, plan = _dispatch_latest_score_window(celery_app, db, parent)
        _persist_latest_score_progress(db, parent, state, plan)
        if not plan.finished:
            celery_app.send_task(
                LATEST_SCORE_WATCHDOG_TASK,
                args=[parent.id],
                queue='sync-bulk',
                countdown=10,
            )
        return parent.result_json or state
    finally:
        db.close()


def _watch_latest_score_children(celery_app, parent_job_id: str) -> dict[str, Any]:
    db = SessionLocal()
    try:
        parent = db.get(AcademicBulkOperationJob, parent_job_id)
        if not parent:
            return {'ok': False, 'error': 'job_not_found'}
        if parent.status not in {'queued', 'running'}:
            return parent.result_json or {'ok': parent.status == 'completed', 'status': parent.status}
        state, plan = _dispatch_latest_score_window(celery_app, db, parent)
        _persist_latest_score_progress(db, parent, state, plan)
        if not plan.finished:
            celery_app.send_task(
                LATEST_SCORE_WATCHDOG_TASK,
                args=[parent.id],
                queue='sync-bulk',
                countdown=15,
            )
        return parent.result_json or state
    finally:
        db.close()


def _mark_ap_03_run(
    db,
    run: AcademicSyncRun,
    *,
    term_id: str,
    branch: str,
    campuses: list[str],
    parent_job_id: str,
) -> None:
    data = dict(run.counters_json or {}) if isinstance(run.counters_json, dict) else {}
    marker = dict(data.get('scheduled_03_auto_map') or {})
    marker.update({
        'enabled': True,
        'term_id': term_id,
        'branch': branch,
        'campuses': campuses,
        'schedule_time': '03:00',
        'timezone': 'Asia/Ho_Chi_Minh',
        'queued_at': marker.get('queued_at') or _now().isoformat(),
        'scheduled_parent_job_id': parent_job_id,
    })
    data['scheduled_03_auto_map'] = marker
    run.counters_json = json_safe_value(data)
    db.add(run)
    db.commit()


def _load_or_freeze_ap_scope(
    db,
    *,
    parent: AcademicBulkOperationJob,
    term: AcademicTerm,
    branch: str,
) -> tuple[dict[str, Any], list[str], list[str]]:
    """Discover the 03:00 class scope once, then replay only the snapshot."""
    parent_request = (
        parent.request_json if isinstance(parent.request_json, dict) else {}
    )
    frozen_scope = (
        parent_request.get('frozen_scope')
        if isinstance(parent_request.get('frozen_scope'), dict)
        else None
    )
    if frozen_scope is not None:
        approved_class_ids = [
            str(value)
            for value in (frozen_scope.get('class_ids') or [])
            if str(value)
        ]
        approved_subject_ids = [
            str(value)
            for value in (parent_request.get('approved_subject_ids') or [])
            if str(value)
        ]
        if not approved_class_ids:
            raise ScheduledScopeError(
                'scope_empty',
                '03:00 mapping discovery returned no mandatory classes.',
            )
        if not approved_subject_ids:
            raise ScheduledScopeError(
                'scope_missing_subjects',
                '03:00 frozen class scope has no subject identities.',
            )
        return frozen_scope, approved_class_ids, approved_subject_ids

    preview = AcademicService(db).auto_map_subject_courses_for_filter(
        _scheduler_user(),
        term_id=str(term.id),
        branch=branch,
        campus=None,
        search=None,
        learning_status=None,
        max_classes=5000,
        dry_run=True,
    )
    if preview.get('scope_truncated'):
        reason = str(
            preview.get('scope_truncated_reason') or 'scope_safety_cap'
        )
        raise ScheduledScopeError(
            'scope_truncated',
            f'03:00 scope discovery was truncated: {reason}.',
        )

    approved_class_ids = list(dict.fromkeys(
        str(item).strip()
        for item in (preview.get('class_ids') or [])
        if str(item or '').strip()
    ))
    if not approved_class_ids:
        raise ScheduledScopeError(
            'scope_empty',
            '03:00 mapping discovery returned no mandatory classes.',
        )
    class_rows = (
        db.query(AcademicClass)
        .filter(AcademicClass.id.in_(approved_class_ids))
        .all()
    )
    class_to_campus = {
        str(item.id): str(item.campus or '').strip().lower() or None
        for item in class_rows
    }
    missing_class_ids = sorted(set(approved_class_ids) - set(class_to_campus))
    if missing_class_ids:
        class_to_campus[missing_class_ids[0]] = None
    approved_subject_ids = sorted({
        str(item.subject_id)
        for item in class_rows
        if str(item.subject_id or '').strip()
    })
    if not approved_subject_ids:
        raise ScheduledScopeError(
            'scope_missing_subjects',
            '03:00 discovered class scope has no subject identities.',
        )
    frozen_scope = freeze_scheduled_scope(
        term_id=str(term.id),
        branch=branch,
        run_date_vn=str(parent_request.get('run_date_vn') or ''),
        class_to_campus=class_to_campus,
        requested_maximum={'classes': 5000},
    )
    parent.request_json = json_safe_value({
        **parent_request,
        'approved_class_ids': frozen_scope['class_ids'],
        'approved_subject_ids': approved_subject_ids,
        'class_to_campus': frozen_scope['class_to_campus'],
        'campuses': frozen_scope['campuses'],
        'scope_hash': frozen_scope['scope_hash'],
        'frozen_scope': frozen_scope,
    })
    parent.result_json = json_safe_value({
        **(parent.result_json or {}),
        'phase': 'scope_frozen',
        'frozen_scope': frozen_scope,
    })
    parent.updated_at = _now()
    db.add(parent)
    db.commit()
    return frozen_scope, list(frozen_scope['class_ids']), approved_subject_ids


def _start_ap_03_schedule(celery_app) -> dict[str, Any]:
    db = SessionLocal()
    queued_runs: list[str] = []
    created_parent_ids: list[str] = []
    reused_parent_ids: list[str] = []
    skipped: list[dict[str, Any]] = []
    publish_errors: list[ContinuationPublishError] = []
    try:
        user = _scheduler_user()
        terms = _active_configured_terms(db)
        run_date_vn = datetime.now(ZoneInfo('Asia/Ho_Chi_Minh')).date().isoformat()
        for term in terms:
            branch = str(term.branch or 'poly').strip().lower() or 'poly'
            parent_key = scheduled_parent_key(
                'ap-daily',
                run_date_vn=run_date_vn,
                term_id=str(term.id),
                branch=branch,
            )
            campuses = _campus_codes_for_term(db, term, branch)
            if not campuses:
                parent, created = create_or_load_scheduled_parent(
                    db,
                    idempotency_key=parent_key,
                    values={
                        'job_type': AP_03_PARENT_JOB_TYPE,
                        'status': 'failed',
                        'term_id': str(term.id),
                        'branch': branch,
                        'campus': None,
                        'requested_by': SCHEDULER_ACTOR,
                        'progress_current': 100,
                        'progress_total': 100,
                        'progress_label': '03:00 +07 · không có cơ sở trong phạm vi',
                        'request_json': json_safe_value({
                            'scheduled': True,
                            'schedule_time': '03:00',
                            'timezone': 'Asia/Ho_Chi_Minh',
                            'run_date_vn': run_date_vn,
                            'term_id': str(term.id),
                            'branch': branch,
                            'campuses': [],
                        }),
                        'result_json': {
                            'ok': False,
                            'phase': 'failed',
                            'code': 'scope_empty',
                            'reason': 'no_campus_scope',
                        },
                        'error_message': '03:00 has no campus scope.',
                        'started_at': _now(),
                        'finished_at': _now(),
                        'updated_at': _now(),
                    },
                )
                (created_parent_ids if created else reused_parent_ids).append(
                    str(parent.id)
                )
                skipped.append({'term_id': term.id, 'branch': branch, 'reason': 'no_campus_scope'})
                continue
            parent, created = create_or_load_scheduled_parent(
                db,
                idempotency_key=parent_key,
                values={
                    'job_type': AP_03_PARENT_JOB_TYPE,
                    'status': 'running',
                    'term_id': str(term.id),
                    'branch': branch,
                    'campus': None,
                    'requested_by': SCHEDULER_ACTOR,
                    'progress_current': 1,
                    'progress_total': 100,
                    'progress_label': '03:00 +07 · đang chờ đồng bộ AP',
                    'request_json': json_safe_value({
                        'scheduled': True,
                        'schedule_time': '03:00',
                        'timezone': 'Asia/Ho_Chi_Minh',
                        'run_date_vn': run_date_vn,
                        'term_id': str(term.id),
                        'branch': branch,
                        'campuses': campuses,
                    }),
                    'result_json': {
                        'phase': 'ap_sync_pending',
                        'run_date_vn': run_date_vn,
                    },
                    'started_at': _now(),
                    'updated_at': _now(),
                },
            )
            if not created:
                reused_parent_ids.append(str(parent.id))
                state = parent.result_json if isinstance(parent.result_json, dict) else {}
                prior_run_id = str(state.get('source_ap_sync_run_id') or '')
                if parent.status in {'queued', 'running'} and prior_run_id:
                    _publish_ap_followup(
                        celery_app,
                        db,
                        parent,
                        prior_run_id,
                        countdown=5,
                    )
                    queued_runs.append(prior_run_id)
                continue
            created_parent_ids.append(str(parent.id))
            try:
                payload = AcademicAPSyncIn(
                    term_name=term.term_name,
                    sync_scope='all',
                    campus=None,
                    campuses=campuses,
                    branch=branch,
                    subject_codes=[],
                    max_subjects=0,
                    dry_run=False,
                )
                response = AcademicAPSyncWorkflowService(db).enqueue_sync_from_ap_job(payload, user=user)
                run = response.get('sync_run')
                if not run:
                    parent.status = 'failed'
                    parent.error_message = 'AP scheduler did not return a sync run.'
                    parent.finished_at = _now()
                    parent.updated_at = parent.finished_at
                    db.add(parent)
                    db.commit()
                    skipped.append({'term_id': term.id, 'branch': branch, 'reason': 'missing_sync_run'})
                    continue
                _mark_ap_03_run(
                    db,
                    run,
                    term_id=str(term.id),
                    branch=branch,
                    campuses=campuses,
                    parent_job_id=str(parent.id),
                )
                queued_runs.append(str(run.id))
                parent.result_json = json_safe_value({
                    **(parent.result_json or {}),
                    'phase': 'waiting_ap_sync',
                    'source_ap_sync_run_id': str(run.id),
                })
                parent.progress_current = 5
                parent.progress_label = '03:00 +07 · đang chờ AP hoàn tất'
                parent.updated_at = _now()
                db.add(parent)
                db.commit()
                _publish_ap_followup(
                    celery_app,
                    db,
                    parent,
                    str(run.id),
                    countdown=30,
                )
            except HTTPException as exc:
                db.rollback()
                parent = db.get(AcademicBulkOperationJob, parent.id)
                if parent:
                    parent.status = 'failed'
                    parent.error_message = str(exc.detail)[:4000]
                    parent.finished_at = _now()
                    parent.updated_at = parent.finished_at
                    db.add(parent)
                    db.commit()
                skipped.append({
                    'term_id': term.id,
                    'branch': branch,
                    'reason': f'http_{exc.status_code}',
                    'detail': str(exc.detail)[:500],
                })
            except ContinuationPublishError as exc:
                db.rollback()
                logger.exception(
                    '03:00 AP scheduler could not publish follow-up for term %s/%s',
                    term.id,
                    branch,
                )
                publish_errors.append(exc)
                skipped.append({
                    'term_id': term.id,
                    'branch': branch,
                    'reason': 'continuation_dispatch_pending',
                })
            except Exception as exc:
                db.rollback()
                parent = db.get(AcademicBulkOperationJob, parent.id)
                if parent:
                    parent.status = 'failed'
                    parent.error_message = str(exc)[:4000]
                    parent.finished_at = _now()
                    parent.updated_at = parent.finished_at
                    db.add(parent)
                    db.commit()
                logger.exception('03:00 AP scheduler could not enqueue term %s/%s', term.id, branch)
                skipped.append({
                    'term_id': term.id,
                    'branch': branch,
                    'reason': exc.__class__.__name__,
                })
        if publish_errors:
            raise publish_errors[0]
        return json_safe_value({
            'ok': True,
            'scheduled': True,
            'schedule': '03:00',
            'timezone': 'Asia/Ho_Chi_Minh',
            'run_date_vn': run_date_vn,
            'term_total': len(terms),
            'created_parent_ids': created_parent_ids,
            'reused_parent_ids': reused_parent_ids,
            'queued_run_ids': queued_runs,
            'queued': len(queued_runs),
            'skipped': skipped,
        })
    finally:
        db.close()


def _create_scheduled_auto_map_after_ap(celery_app, run_id: str) -> dict[str, Any]:
    db = SessionLocal()
    try:
        run = db.get(AcademicSyncRun, run_id)
        if not run:
            return {'ok': False, 'error': 'sync_run_not_found'}
        data = dict(run.counters_json or {}) if isinstance(run.counters_json, dict) else {}
        marker = dict(data.get('scheduled_03_auto_map') or {})
        if not marker.get('enabled'):
            return {'ok': True, 'skipped': True, 'reason': 'not_03_scheduler_run'}
        parent_job_id = str(marker.get('scheduled_parent_job_id') or '')
        parent = (
            db.get(AcademicBulkOperationJob, parent_job_id)
            if parent_job_id
            else None
        )
        if parent is None:
            marker['followup_status'] = 'scheduled_parent_missing'
            marker['finished_at'] = _now().isoformat()
            data['scheduled_03_auto_map'] = marker
            run.counters_json = json_safe_value(data)
            db.add(run)
            db.commit()
            return {'ok': False, 'error': 'scheduled_parent_missing'}
        if parent.status not in {'queued', 'running'}:
            return {
                'ok': parent.status == 'completed',
                'status': parent.status,
                'parent_job_id': str(parent.id),
            }
        confirm_parent_continuation(
            db,
            parent,
            now=_now(),
            expected_task_name=AP_03_FOLLOWUP_TASK,
        )
        if marker.get('auto_map_job_id'):
            marked_job = db.get(
                AcademicBulkOperationJob,
                str(marker.get('auto_map_job_id')),
            )
            if marked_job is None:
                marker.pop('auto_map_job_id', None)
                marker['followup_status'] = 'auto_map_job_missing'
                data['scheduled_03_auto_map'] = marker
                run.counters_json = json_safe_value(data)
                db.add(run)
                db.commit()
            else:
                if marked_job.status in {'completed', 'failed'}:
                    parent.status = marked_job.status
                    parent.progress_current = 100
                    parent.progress_total = 100
                    parent.progress_label = (
                        '03:00 +07 · hoàn tất AP, auto-map và đồng bộ CMS'
                        if marked_job.status == 'completed'
                        else '03:00 +07 · pipeline AP/CMS thất bại'
                    )
                    parent.error_message = marked_job.error_message
                    parent.finished_at = marked_job.finished_at or _now()
                    parent.updated_at = _now()
                    parent.result_json = json_safe_value({
                        **(parent.result_json or {}),
                        'phase': marked_job.status,
                        'auto_map_job_id': str(marked_job.id),
                    })
                    db.add(parent)
                    db.commit()
                return {
                    'ok': marked_job.status != 'failed',
                    'reused': True,
                    'auto_map_job_id': marker.get('auto_map_job_id'),
                    'status': marked_job.status,
                }

        if run.status in {'queued', 'running'}:
            checks = int(marker.get('followup_checks') or 0) + 1
            marker['followup_checks'] = checks
            marker['last_checked_at'] = _now().isoformat()
            data['scheduled_03_auto_map'] = marker
            run.counters_json = json_safe_value(data)
            db.add(run)
            db.commit()
            if checks >= 120:
                marker['followup_status'] = 'timeout_waiting_for_ap'
                data['scheduled_03_auto_map'] = marker
                run.counters_json = json_safe_value(data)
                db.add(run)
                if parent:
                    parent.status = 'failed'
                    parent.error_message = '03:00 AP sync follow-up timed out.'
                    parent.finished_at = _now()
                    parent.updated_at = parent.finished_at
                    db.add(parent)
                db.commit()
                return {'ok': False, 'error': 'timeout_waiting_for_ap'}
            if parent:
                parent.result_json = json_safe_value({
                    **(parent.result_json or {}),
                    'phase': 'waiting_ap_sync',
                    'source_ap_sync_run_id': str(run.id),
                    'followup_checks': checks,
                })
                db.add(parent)
                db.commit()
                _publish_ap_followup(
                    celery_app,
                    db,
                    parent,
                    str(run.id),
                    countdown=60,
                )
            else:
                celery_app.send_task(
                    AP_03_FOLLOWUP_TASK,
                    args=[run_id],
                    queue='sync-bulk',
                    countdown=60,
                )
            return {'ok': True, 'waiting': True, 'status': run.status, 'check': checks}

        if run.status != 'completed':
            marker['followup_status'] = 'ap_failed'
            marker['ap_status'] = run.status
            marker['finished_at'] = _now().isoformat()
            data['scheduled_03_auto_map'] = marker
            run.counters_json = json_safe_value(data)
            db.add(run)
            if parent:
                parent.status = 'failed'
                parent.error_message = f'AP sync ended with status {run.status}.'
                parent.finished_at = _now()
                parent.updated_at = parent.finished_at
                db.add(parent)
            db.commit()
            return {'ok': False, 'error': 'ap_sync_failed', 'status': run.status}

        term_id = str(marker.get('term_id') or '').strip()
        branch = str(marker.get('branch') or run.branch or 'poly').strip().lower() or 'poly'
        term = db.get(AcademicTerm, term_id) if term_id else None
        if not term:
            term = (
                db.query(AcademicTerm)
                .filter(
                    AcademicTerm.term_name == run.term_name,
                    func.lower(AcademicTerm.branch) == branch,
                )
                .order_by(AcademicTerm.active.desc(), AcademicTerm.updated_at.desc())
                .first()
            )
        if not term:
            marker['followup_status'] = 'term_not_found'
            data['scheduled_03_auto_map'] = marker
            run.counters_json = json_safe_value(data)
            db.add(run)
            db.commit()
            return {'ok': False, 'error': 'term_not_found'}

        parent = (
            db.query(AcademicBulkOperationJob)
            .filter(AcademicBulkOperationJob.id == parent.id)
            .with_for_update()
            .one()
        )
        try:
            (
                frozen_scope,
                approved_class_ids,
                approved_subject_ids,
            ) = _load_or_freeze_ap_scope(
                db,
                parent=parent,
                term=term,
                branch=branch,
            )
        except ScheduledScopeError as exc:
            marker.update({
                'followup_status': exc.code,
                'finished_at': _now().isoformat(),
            })
            data['scheduled_03_auto_map'] = marker
            run.counters_json = json_safe_value(data)
            db.add(run)
            parent.status = 'failed'
            parent.error_message = str(exc)
            parent.result_json = json_safe_value({
                **(parent.result_json or {}),
                'phase': 'failed',
                'code': exc.code,
            })
            parent.finished_at = _now()
            parent.updated_at = parent.finished_at
            db.add(parent)
            db.commit()
            return {'ok': False, 'error': exc.code, 'message': str(exc)}
        parent_request = (
            parent.request_json if isinstance(parent.request_json, dict) else {}
        )

        auto_map_contract = scheduled_auto_map_contract(
            scheduled_parent_job_id=parent_job_id,
            ap_sync_run_id=str(run.id),
            frozen_scope=frozen_scope,
        )
        auto_map_key = scheduled_auto_map_key(auto_map_contract)
        exact_existing = db.query(AcademicBulkOperationJob).filter(
            AcademicBulkOperationJob.idempotency_key == auto_map_key,
        ).one_or_none()
        if exact_existing is not None:
            marker['auto_map_job_id'] = exact_existing.id
            marker['followup_status'] = 'auto_map_reused'
            data['scheduled_03_auto_map'] = marker
            run.counters_json = json_safe_value(data)
            db.add(run)
            parent.request_json = json_safe_value({
                **parent_request,
                'approved_class_ids': frozen_scope['class_ids'],
                'class_to_campus': frozen_scope['class_to_campus'],
                'campuses': frozen_scope['campuses'],
                'scope_hash': frozen_scope['scope_hash'],
                'frozen_scope': frozen_scope,
            })
            parent.result_json = json_safe_value({
                **(parent.result_json or {}),
                'phase': (
                    'completed'
                    if exact_existing.status == 'completed'
                    else (
                        'failed'
                        if exact_existing.status == 'failed'
                        else 'auto_map_queued'
                    )
                ),
                'auto_map_job_id': str(exact_existing.id),
                'frozen_scope': frozen_scope,
            })
            if exact_existing.status in {'completed', 'failed'}:
                parent.status = exact_existing.status
                parent.progress_current = 100
                parent.finished_at = exact_existing.finished_at or _now()
                parent.updated_at = _now()
                parent.error_message = exact_existing.error_message
            db.add(parent)
            db.commit()
            return {
                'ok': exact_existing.status != 'failed',
                'reused': True,
                'auto_map_job_id': exact_existing.id,
                'status': exact_existing.status,
            }

        active_candidates = (
            db.query(AcademicBulkOperationJob)
            .filter(
                AcademicBulkOperationJob.job_type
                == 'subject_auto_map_all_sync',
                AcademicBulkOperationJob.term_id == term.id,
                AcademicBulkOperationJob.branch == branch,
                AcademicBulkOperationJob.status.in_(['queued', 'running']),
            )
            .order_by(AcademicBulkOperationJob.created_at.desc())
            .all()
        )
        foreign_active = next(
            (
                candidate
                for candidate in active_candidates
                if candidate.idempotency_key != auto_map_key
            ),
            None,
        )
        if foreign_active is not None:
            blocked_checks = int(marker.get('foreign_block_checks') or 0) + 1
            marker.update({
                'followup_status': 'blocked_by_foreign_job',
                'foreign_block_checks': blocked_checks,
                'blocking_job_id': str(foreign_active.id),
                'last_checked_at': _now().isoformat(),
            })
            data['scheduled_03_auto_map'] = marker
            run.counters_json = json_safe_value(data)
            db.add(run)
            if blocked_checks >= 120:
                if parent:
                    parent.status = 'failed'
                    parent.error_message = (
                        '03:00 auto-map remained blocked by a foreign active job.'
                    )
                    parent.finished_at = _now()
                    parent.updated_at = parent.finished_at
                    db.add(parent)
                db.commit()
                return {
                    'ok': False,
                    'error': 'foreign_job_block_timeout',
                    'blocking_job_id': str(foreign_active.id),
                }
            if parent:
                parent.result_json = json_safe_value({
                    **(parent.result_json or {}),
                    'phase': 'auto_map_blocked',
                    'blocking_job_id': str(foreign_active.id),
                    'frozen_scope': frozen_scope,
                })
                parent.request_json = json_safe_value({
                    **parent_request,
                    'scope_hash': frozen_scope['scope_hash'],
                    'frozen_scope': frozen_scope,
                })
                db.add(parent)
                db.commit()
                _publish_ap_followup(
                    celery_app,
                    db,
                    parent,
                    str(run.id),
                    countdown=60,
                )
            else:
                db.commit()
            return {
                'ok': True,
                'waiting': True,
                'reason': 'blocked_by_foreign_job',
                'blocking_job_id': str(foreign_active.id),
            }

        campus_codes = list(frozen_scope['campuses'])
        request_json = json_safe_value({
            'term_id': str(term.id),
            'branch': branch,
            'campus': None,
            'search': None,
            'learning_status': None,
            'force': False,
            'limit': 500,
            'mode': None,
            'sync_learning': False,
            'max_classes': 5000,
            'approved_class_ids': approved_class_ids,
            'approved_class_total': len(approved_class_ids),
            'approved_subject_ids': approved_subject_ids,
            'approved_campus_codes_from_preview': campus_codes,
            'scheduled_parent_job_id': parent_job_id,
            'scheduled_scope_hash': frozen_scope['scope_hash'],
            'scheduled_scope_contract': auto_map_contract,
            'frozen_scope': frozen_scope,
            'policy_version': frozen_scope['policy_version'],
            'requester_context': _scheduler_requester_context(),
            'scope_enforced_by_backend': True,
            'scheduled': True,
            'schedule_time': '03:00',
            'timezone': 'Asia/Ho_Chi_Minh',
            'source_ap_sync_run_id': run.id,
            'operation': 'auto_map_without_learning_sync',
        })
        job = AcademicBulkOperationJob(
            job_type='subject_auto_map_all_sync',
            status='queued',
            term_id=str(term.id),
            branch=branch,
            campus=None,
            requested_by=SCHEDULER_ACTOR,
            progress_current=0,
            progress_total=100,
            progress_label='03:00 AP đã xong · đang chờ tự động ghép Course CMS',
            request_json=request_json,
            result_json={},
            idempotency_key=auto_map_key,
        )
        db.add(job)
        try:
            db.flush()
        except IntegrityError:
            db.rollback()
            job = db.query(AcademicBulkOperationJob).filter(
                AcademicBulkOperationJob.idempotency_key == auto_map_key,
            ).one_or_none()
            if job is None:
                raise
            return {
                'ok': job.status != 'failed',
                'reused': True,
                'auto_map_job_id': job.id,
                'status': job.status,
            }
        db.refresh(job)

        marker['auto_map_job_id'] = job.id
        marker['followup_status'] = 'auto_map_queued'
        marker['ap_completed_at'] = (run.finished_at or _now()).isoformat()
        marker['auto_map_queued_at'] = _now().isoformat()
        data['scheduled_03_auto_map'] = marker
        run.counters_json = json_safe_value(data)
        db.add(run)
        if parent:
            parent.request_json = json_safe_value({
                **parent_request,
                'approved_class_ids': frozen_scope['class_ids'],
                'class_to_campus': frozen_scope['class_to_campus'],
                'campuses': frozen_scope['campuses'],
                'scope_hash': frozen_scope['scope_hash'],
                'frozen_scope': frozen_scope,
            })
            parent.result_json = json_safe_value({
                **(parent.result_json or {}),
                'phase': 'auto_map_queued',
                'auto_map_job_id': str(job.id),
                'frozen_scope': frozen_scope,
            })
            parent.progress_current = 20
            parent.progress_label = '03:00 AP đã xong · đã xếp hàng auto-map'
            parent.updated_at = _now()
            db.add(parent)
        _publish_auto_map_job(
            celery_app,
            db,
            parent,
            str(job.id),
        )
        return {
            'ok': True,
            'auto_map_job_id': job.id,
            'class_total': len(approved_class_ids),
            'subject_total': len(approved_subject_ids),
            'sync_learning': False,
        }
    finally:
        db.close()


def register_student_management_runtime_tasks(celery_app) -> None:
    """Register manual/compatibility handlers used by the unified pipeline."""

    @celery_app.task(name=LATEST_SCORE_TASK)
    def _latest_score_task(job_id: str):
        db = SessionLocal()
        try:
            job = db.get(AcademicBulkOperationJob, job_id)
            if not job:
                return {'ok': False, 'error': 'job_not_found'}
            # Detach before the helper opens its own session.
            db.expunge(job)
        finally:
            db.close()
        return _enqueue_latest_score_children(celery_app, job)

    @celery_app.task(name=LATEST_SCORE_WATCHDOG_TASK)
    def _latest_score_watchdog_task(job_id: str):
        return _watch_latest_score_children(celery_app, job_id)

    @celery_app.task(name=AP_03_TASK)
    def _ap_03_schedule_task():
        return _start_ap_03_schedule(celery_app)

    @celery_app.task(name=AP_03_FOLLOWUP_TASK)
    def _ap_03_followup_task(run_id: str):
        return _create_scheduled_auto_map_after_ap(celery_app, run_id)

    routes = dict(getattr(celery_app.conf, 'task_routes', {}) or {})
    routes.update({
        LATEST_SCORE_TASK: {'queue': 'sync-bulk'},
        LATEST_SCORE_WATCHDOG_TASK: {'queue': 'sync-bulk'},
        AP_03_TASK: {'queue': 'sync-bulk'},
        AP_03_FOLLOWUP_TASK: {'queue': 'sync-bulk'},
    })
    celery_app.conf.task_routes = routes

    annotations = dict(getattr(celery_app.conf, 'task_annotations', {}) or {})
    annotations.update({
        LATEST_SCORE_TASK: {'soft_time_limit': 540, 'time_limit': 600},
        LATEST_SCORE_WATCHDOG_TASK: {'soft_time_limit': 45, 'time_limit': 55},
        AP_03_TASK: {'soft_time_limit': 540, 'time_limit': 600},
        AP_03_FOLLOWUP_TASK: {'soft_time_limit': 120, 'time_limit': 180},
    })
    celery_app.conf.task_annotations = annotations
