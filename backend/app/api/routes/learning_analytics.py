from __future__ import annotations

from typing import Any
from pathlib import Path

from fastapi import APIRouter, Depends, Query, HTTPException
from pydantic import BaseModel, Field, model_validator
from sqlalchemy import func
from sqlalchemy.orm import Session
from fastapi.responses import Response

from app.core.rbac import UserContext, require_permission
from app.core.config import settings
from app.db.session import get_db
from app.services.learning_analytics.analytics_core_service import LearningAnalyticsCoreService
from app.services.audit_log import log_audit
from app.core.json_safe import json_safe_value
from app.models.academic import AcademicClassSyncJob
from app.services.academic_service import AcademicService
from app.schemas.academic import AcademicClassSyncJobOut

router = APIRouter()


def _allowed_class_ids_for_analytics(db: Session, user: UserContext) -> set[str] | None:
    """Return class ids visible to the actor, or None for unrestricted admin.

    Analytics can expose sensitive student behavior signals. Production routes
    therefore reuse the academic RBAC decision instead of only hiding UI links.
    """
    service = AcademicService(db)
    decision = service.access_decision(user)
    if decision.unrestricted:
        return None
    from app.models.academic import AcademicClass, AcademicTeacherAssignment, AcademicSubject
    filters = []
    if decision.teacher_ids:
        teacher_class_ids = [r[0] for r in db.query(AcademicTeacherAssignment.class_id).filter(AcademicTeacherAssignment.teacher_id.in_(decision.teacher_ids)).all() if r[0]]
        if teacher_class_ids:
            filters.append(AcademicClass.id.in_(teacher_class_ids))
    if decision.subject_codes:
        filters.append(AcademicClass.subject_id.in_([r[0] for r in db.query(AcademicSubject.id).filter(func.lower(AcademicSubject.subject_code).in_(decision.subject_codes)).all()]))
    if decision.campus_codes:
        filters.append(func.lower(AcademicClass.campus).in_(sorted(decision.campus_codes)))
    if not filters:
        return set()
    from sqlalchemy import or_
    rows = db.query(AcademicClass.id).filter(or_(*filters)).all()
    return {str(r[0]) for r in rows if r[0]}




def _analytics_permission_scope(db: Session, user: UserContext) -> dict[str, Any]:
    """Small, user-safe explanation of the effective analytics visibility.

    The enforcement is done by AcademicService.assert_can_access_class and by
    passing allowed_class_ids into aggregate queries. This payload is only for UI
    transparency so teachers understand why they see a subset of data.
    """
    service = AcademicService(db)
    decision = service.access_decision(user)
    if decision.unrestricted:
        return {
            'mode': 'all',
            'unrestricted': True,
            'teacher_ids': [],
            'subject_codes': [],
            'campus_codes': [],
            'enforced_by_backend': True,
            'label': 'Toàn hệ thống',
        }
    return {
        'mode': 'scoped',
        'unrestricted': False,
        'teacher_ids': sorted(str(item) for item in (decision.teacher_ids or set())),
        'subject_codes': sorted(str(item) for item in (decision.subject_codes or set())),
        'campus_codes': sorted(str(item) for item in (decision.campus_codes or set())),
        'enforced_by_backend': True,
        'label': 'Đã lọc theo phân quyền cơ sở, môn hoặc lớp AP được phân công',
    }

def _assert_analytics_class_access(db: Session, user: UserContext, class_id: str | None) -> None:
    if not class_id:
        return
    AcademicService(db).assert_can_access_class(user, class_id)


def _enqueue_analytics_recalculate_job(
    *,
    db: Session,
    user: UserContext,
    class_id: str,
    course_id: str,
    username: str | None = None,
    force: bool = False,
    limit: int | None = None,
) -> AcademicClassSyncJob:
    AcademicService(db).assert_can_access_class(user, class_id)
    service = LearningAnalyticsCoreService(db)
    rollout = service.rollout_control_report(class_id=class_id, course_id=course_id, allowed_class_ids=None, limit=10)
    rollout_item = next((item for item in (rollout.get('items') or []) if item.get('class_id') == class_id), None)
    if not rollout.get('enabled') or not rollout.get('allow_backfill') or (rollout_item is not None and not rollout_item.get('in_rollout')):
        raise HTTPException(status_code=409, detail={'code': 'ANALYTICS_CLASS_NOT_IN_ROLLOUT', 'message': 'Lớp chưa nằm trong phạm vi rollout học online hoặc backfill đang tắt.', 'rollout': rollout})
    guard = service.analytics_enqueue_guard(class_id=class_id)
    active = db.query(AcademicClassSyncJob).filter(
        AcademicClassSyncJob.class_id == class_id,
        AcademicClassSyncJob.job_type == 'learning_analytics_recalculate',
        AcademicClassSyncJob.status.in_(['queued', 'running']),
    ).order_by(AcademicClassSyncJob.created_at.desc()).first()
    if active:
        return active
    if not guard.get('allowed'):
        raise HTTPException(status_code=409, detail=guard)
    safe_limit = max(1, min(int(getattr(settings, 'analytics_recalculate_max_students_per_job', 500) or 500), int(limit or 500)))
    job = AcademicClassSyncJob(
        job_type='learning_analytics_recalculate',
        status='queued',
        class_id=class_id,
        requested_by=user.user_id,
        force=bool(force),
        limit=safe_limit,
        progress_current=0,
        progress_total=100,
        progress_label='Đang chờ tính lại học online',
        request_json=json_safe_value({'course_id': course_id, 'username': username, 'force': force, 'limit': safe_limit, 'guard': guard}),
        result_json={},
    )
    db.add(job)
    db.commit()
    db.refresh(job)
    from app.worker import analytics_class_recalculate_task
    async_result = analytics_class_recalculate_task.delay(job.id)
    data = job.request_json if isinstance(job.request_json, dict) else {}
    data['enqueue'] = {'task_name': 'analytics_class_recalculate_task', 'celery_task_id': getattr(async_result, 'id', None)}
    job.request_json = json_safe_value(data)
    db.add(job)
    db.commit()
    db.refresh(job)
    return job



class RebuildSessionStructureRequest(BaseModel):
    blocks: list[dict[str, Any]] = Field(default_factory=list)
    course_start_at: str | None = None




class AnalyticsClassRecalculateRequest(BaseModel):
    course_id: str | None = None
    force: bool = False
    limit: int | None = Field(default=None, ge=1, le=500)


class AnalyticsIngestRequest(BaseModel):
    file_path: str | None = None
    max_lines: int | None = Field(default=None, ge=1, le=200000)

    @model_validator(mode='after')
    def validate_file_path(self) -> 'AnalyticsIngestRequest':
        if not self.file_path:
            return self
        configured = Path(getattr(settings, 'openedx_tracking_log_path', '/openedx-data/lms/logs/tracking.log')).resolve()
        requested = Path(self.file_path).resolve()
        if requested != configured:
            raise ValueError('Chỉ được ingest tracking.log đã cấu hình trong OPENEDX_TRACKING_LOG_PATH.')
        self.file_path = str(requested)
        return self


@router.get('/learning/schema-inspect')
def learning_schema_inspect(db: Session = Depends(get_db), user: UserContext = Depends(require_permission('view_dashboard'))):
    return LearningAnalyticsCoreService(db).schema_inspect()


@router.post('/ingest/run')
def run_ingest(
    payload: AnalyticsIngestRequest | None = None,
    db: Session = Depends(get_db),
    user: UserContext = Depends(require_permission('manage_settings')),
):
    payload = payload or AnalyticsIngestRequest()
    result = LearningAnalyticsCoreService(db).run_ingest(file_path=payload.file_path, max_lines=payload.max_lines)
    log_audit(db, action='analytics.ingest.run', status='success', message='Chạy ingest tracking log học online', user=user, target_type='learning_analytics', metadata={'result': result})
    return result


@router.get('/ingest/status')
def ingest_status(db: Session = Depends(get_db), user: UserContext = Depends(require_permission('view_dashboard'))):
    return LearningAnalyticsCoreService(db).ingest_status()


@router.post('/ingest/jobs')
def enqueue_ingest_job(
    payload: AnalyticsIngestRequest | None = None,
    db: Session = Depends(get_db),
    user: UserContext = Depends(require_permission('manage_settings')),
):
    payload = payload or AnalyticsIngestRequest()
    guard = LearningAnalyticsCoreService(db).analytics_ingest_enqueue_guard()
    if not guard.get('allowed'):
        raise HTTPException(status_code=409, detail=guard)
    max_allowed = int(getattr(settings, 'analytics_max_lines_per_run', 50000) or 50000)
    safe_max_lines = max(1, min(int(payload.max_lines or max_allowed), max_allowed))
    from app.worker import analytics_ingest_task
    async_result = analytics_ingest_task.delay(payload.file_path, safe_max_lines)
    log_audit(db, action='analytics.ingest.enqueue', status='success', message='Đưa ingest tracking log học online vào hàng đợi', user=user, target_type='learning_analytics', metadata={'task_name': 'analytics_ingest_task', 'celery_task_id': getattr(async_result, 'id', None), 'file_path': payload.file_path, 'max_lines': safe_max_lines, 'guard': guard})
    return {'status': 'queued', 'task_name': 'analytics_ingest_task', 'celery_task_id': getattr(async_result, 'id', None), 'max_lines': safe_max_lines, 'message': 'Đã đưa ingest tracking log vào hàng đợi.', 'safe_policy': 'signals_only_not_violation'}


@router.get('/ops/status')
def analytics_ops_status(db: Session = Depends(get_db), user: UserContext = Depends(require_permission('view_dashboard'))):
    return LearningAnalyticsCoreService(db).ops_status()


@router.get('/ops/production-readiness')
def analytics_production_readiness(db: Session = Depends(get_db), user: UserContext = Depends(require_permission('view_dashboard'))):
    allowed_class_ids = _allowed_class_ids_for_analytics(db, user)
    return LearningAnalyticsCoreService(db).production_readiness_report(allowed_class_ids=allowed_class_ids)


@router.get('/ops/rollout-control')
def analytics_rollout_control(
    campus: str | None = None,
    branch: str | None = None,
    class_id: str | None = None,
    course_id: str | None = None,
    limit: int = Query(default=100, ge=1, le=500),
    db: Session = Depends(get_db),
    user: UserContext = Depends(require_permission('view_dashboard')),
):
    if class_id:
        _assert_analytics_class_access(db, user, class_id)
    allowed_class_ids = _allowed_class_ids_for_analytics(db, user)
    return LearningAnalyticsCoreService(db).rollout_control_report(campus=campus, branch=branch, class_id=class_id, course_id=course_id, allowed_class_ids=allowed_class_ids, limit=limit)


@router.get('/ops/monitoring')
def analytics_monitoring(
    class_id: str | None = None,
    course_id: str | None = None,
    db: Session = Depends(get_db),
    user: UserContext = Depends(require_permission('view_dashboard')),
):
    if class_id:
        _assert_analytics_class_access(db, user, class_id)
    allowed_class_ids = _allowed_class_ids_for_analytics(db, user)
    return LearningAnalyticsCoreService(db).analytics_monitoring_report(class_id=class_id, course_id=course_id, allowed_class_ids=allowed_class_ids)


@router.get('/ops/data-quality')
def analytics_data_quality(
    class_id: str | None = None,
    course_id: str | None = None,
    db: Session = Depends(get_db),
    user: UserContext = Depends(require_permission('view_dashboard')),
):
    if class_id:
        _assert_analytics_class_access(db, user, class_id)
    allowed_class_ids = _allowed_class_ids_for_analytics(db, user)
    return LearningAnalyticsCoreService(db).analytics_data_quality_report(class_id=class_id, course_id=course_id, allowed_class_ids=allowed_class_ids)


@router.get('/backfill/plan')
def analytics_backfill_plan(
    campus: str | None = None,
    branch: str | None = None,
    class_id: str | None = None,
    course_id: str | None = None,
    limit: int = Query(default=50, ge=1, le=200),
    db: Session = Depends(get_db),
    user: UserContext = Depends(require_permission('view_dashboard')),
):
    if class_id:
        _assert_analytics_class_access(db, user, class_id)
    allowed_class_ids = _allowed_class_ids_for_analytics(db, user)
    return LearningAnalyticsCoreService(db).analytics_backfill_plan(campus=campus, branch=branch, class_id=class_id, course_id=course_id, limit=limit, allowed_class_ids=allowed_class_ids)


@router.post('/backfill/jobs')
def enqueue_analytics_backfill_jobs(
    campus: str | None = None,
    branch: str | None = None,
    class_id: str | None = None,
    course_id: str | None = None,
    limit: int = Query(default=20, ge=1, le=50),
    db: Session = Depends(get_db),
    user: UserContext = Depends(require_permission('view_dashboard')),
):
    if class_id:
        _assert_analytics_class_access(db, user, class_id)
    allowed_class_ids = _allowed_class_ids_for_analytics(db, user)
    service = LearningAnalyticsCoreService(db)
    rollout = service.rollout_control_report(campus=campus, branch=branch, class_id=class_id, course_id=course_id, allowed_class_ids=allowed_class_ids, limit=50)
    if not rollout.get('allow_backfill') or not rollout.get('enabled'):
        raise HTTPException(status_code=409, detail={'code': 'ANALYTICS_ROLLOUT_BACKFILL_DISABLED', 'message': 'Backfill học online đang bị tắt theo rollout control.', 'rollout': rollout})
    max_jobs = int(getattr(settings, 'analytics_backfill_max_jobs_per_request', 25) or 25)
    safe_limit = max(1, min(int(limit or max_jobs), max_jobs))
    global_guard = service.analytics_enqueue_guard(class_id=None)
    if not global_guard.get('allowed'):
        raise HTTPException(status_code=409, detail=global_guard)
    plan = service.analytics_backfill_plan(campus=campus, branch=branch, class_id=class_id, course_id=course_id, limit=safe_limit, allowed_class_ids=allowed_class_ids)
    jobs: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    for item in plan.get('items') or []:
        rollout_item = next((r for r in (rollout.get('items') or []) if r.get('class_id') == item.get('class_id')), None)
        if rollout_item is not None and not rollout_item.get('in_rollout'):
            skipped.append({'class_id': item.get('class_id'), 'class_code': item.get('class_code'), 'reasons': ['CLASS_NOT_IN_ROLLOUT'] + (rollout_item.get('rollout_reasons') or [])})
            continue
        if not item.get('can_enqueue'):
            skipped.append({'class_id': item.get('class_id'), 'class_code': item.get('class_code'), 'reasons': item.get('reasons') or []})
            continue
        job = _enqueue_analytics_recalculate_job(
            db=db,
            user=user,
            class_id=str(item.get('class_id')),
            course_id=str(item.get('course_id')),
            force=True,
            limit=500,
        )
        jobs.append({'job_id': job.id, 'class_id': job.class_id, 'course_id': item.get('course_id'), 'status': job.status, 'progress_label': job.progress_label})
    log_audit(
        db,
        action='analytics.backfill.enqueue',
        status='success',
        message='Đưa backfill học online vào hàng đợi',
        user=user,
        course_id=course_id,
        target_type='learning_analytics',
        target_id=class_id,
        metadata={'filters': {'campus': campus, 'branch': branch, 'class_id': class_id, 'course_id': course_id, 'limit': safe_limit}, 'queued_jobs': len(jobs), 'skipped': len(skipped), 'signals_only_not_violation': True},
    )
    return {'status': 'queued', 'requested_limit': safe_limit, 'queued_jobs': len(jobs), 'skipped_count': len(skipped), 'jobs': jobs, 'skipped': skipped, 'safe_policy': 'signals_only_not_violation'}


@router.get('/ops/pilot-acceptance')
def analytics_pilot_acceptance(
    class_id: str | None = None,
    course_id: str | None = None,
    campus: str | None = None,
    branch: str | None = None,
    sample_limit: int = Query(default=5, ge=1, le=20),
    db: Session = Depends(get_db),
    user: UserContext = Depends(require_permission('view_dashboard')),
):
    if class_id:
        _assert_analytics_class_access(db, user, class_id)
    allowed_class_ids = _allowed_class_ids_for_analytics(db, user)
    result = LearningAnalyticsCoreService(db).pilot_acceptance_report(class_id=class_id, course_id=course_id, campus=campus, branch=branch, sample_limit=sample_limit, allowed_class_ids=allowed_class_ids)
    log_audit(db, action='analytics.pilot_acceptance.view', status='success', message='Xem báo cáo pilot production học online', user=user, course_id=course_id, target_type='learning_analytics', target_id=class_id, metadata={'pilot_status': result.get('pilot_status'), 'signals_only_not_violation': True})
    return result


@router.get('/courses/{course_id}/session-structure')
def get_session_structure(course_id: str, class_id: str | None = None, db: Session = Depends(get_db), user: UserContext = Depends(require_permission('view_dashboard'))):
    return {'course_id': course_id, 'class_id': class_id, 'sessions': LearningAnalyticsCoreService(db).get_session_structure(course_id=course_id, class_id=class_id)}


@router.post('/courses/{course_id}/session-structure/rebuild')
def rebuild_session_structure(course_id: str, payload: RebuildSessionStructureRequest, db: Session = Depends(get_db), user: UserContext = Depends(require_permission('manage_settings'))):
    from datetime import datetime
    course_start_at = None
    if payload.course_start_at:
        course_start_at = datetime.fromisoformat(payload.course_start_at.replace('Z', '+00:00')).replace(tzinfo=None)
    return LearningAnalyticsCoreService(db).rebuild_session_structure_from_blocks(course_id=course_id, blocks=payload.blocks, course_start_at=course_start_at)


@router.post('/courses/{course_id}/videos/recalculate')
def recalculate_video_progress(course_id: str, username: str | None = None, db: Session = Depends(get_db), user: UserContext = Depends(require_permission('manage_settings'))):
    return LearningAnalyticsCoreService(db).recalculate_course_video_progress(course_id=course_id, username=username)


@router.post('/classes/{class_id}/learning-behavior/recalculate')
def recalculate_class_behavior(class_id: str, course_id: str, username: str | None = None, db: Session = Depends(get_db), user: UserContext = Depends(require_permission('view_dashboard'))):
    _assert_analytics_class_access(db, user, class_id)
    service = LearningAnalyticsCoreService(db)
    service.recalculate_course_video_progress(course_id=course_id, username=username)
    service.recalculate_student_session_progress(class_id=class_id, course_id=course_id, username=username)
    result = service.recalculate_learning_behavior(class_id=class_id, course_id=course_id, username=username)
    log_audit(db, action='analytics.learning_behavior.recalculate', status='success', message='Tính lại nhận định học online theo tín hiệu mềm', user=user, course_id=course_id, target_type='academic_class', target_id=class_id, metadata={'username': username, 'result': result})
    return result


@router.post('/classes/{class_id}/learning-behavior/jobs', response_model=AcademicClassSyncJobOut)
def enqueue_class_behavior_recalculate_job(
    class_id: str,
    course_id: str,
    username: str | None = None,
    force: bool = False,
    limit: int | None = Query(default=None, ge=1, le=500),
    db: Session = Depends(get_db),
    user: UserContext = Depends(require_permission('view_dashboard')),
):
    job = _enqueue_analytics_recalculate_job(db=db, user=user, class_id=class_id, course_id=course_id, username=username, force=force, limit=limit)
    log_audit(db, action='analytics.learning_behavior.recalculate.enqueue', status='success', message='Đưa tính lại học online vào hàng đợi', user=user, course_id=course_id, target_type='academic_class_sync_job', target_id=job.id, metadata={'class_id': class_id, 'username': username, 'signals_only_not_violation': True})
    return job



@router.get('/learning/dashboard')
def learning_dashboard(
    campus: str | None = None,
    branch: str | None = None,
    course_id: str | None = None,
    class_id: str | None = None,
    classification: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    limit: int = Query(default=50, ge=1, le=200),
    db: Session = Depends(get_db),
    user: UserContext = Depends(require_permission('view_dashboard')),
):
    _assert_analytics_class_access(db, user, class_id)
    allowed_class_ids = _allowed_class_ids_for_analytics(db, user)
    result = LearningAnalyticsCoreService(db).learning_dashboard(campus=campus, branch=branch, course_id=course_id, class_id=class_id, classification=classification, date_from=date_from, date_to=date_to, limit=limit, allowed_class_ids=allowed_class_ids)
    if classification == 'POSSIBLE_ANOMALY':
        log_audit(db, action='analytics.learning_behavior.view_attention_list', status='success', message='Xem danh sách dấu hiệu bất thường cần kiểm tra', user=user, course_id=course_id, target_type='learning_analytics', target_id=class_id, metadata={'classification_note': 'signals_only_not_violation', 'filters': result.get('filters')})
    return result


@router.get('/learning/export.csv')
def export_learning_behavior_csv(
    campus: str | None = None,
    branch: str | None = None,
    course_id: str | None = None,
    class_id: str | None = None,
    classification: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    db: Session = Depends(get_db),
    user: UserContext = Depends(require_permission('view_dashboard')),
):
    _assert_analytics_class_access(db, user, class_id)
    allowed_class_ids = _allowed_class_ids_for_analytics(db, user)
    service = LearningAnalyticsCoreService(db)
    rollout = service.rollout_control_report(campus=campus, branch=branch, class_id=class_id, course_id=course_id, allowed_class_ids=allowed_class_ids, limit=50)
    if not rollout.get('allow_export') or not rollout.get('enabled'):
        raise HTTPException(status_code=409, detail={'code': 'ANALYTICS_ROLLOUT_EXPORT_DISABLED', 'message': 'Export học online đang bị tắt theo rollout control.', 'rollout': rollout})
    content = service.export_learning_behavior_csv(campus=campus, branch=branch, course_id=course_id, class_id=class_id, classification=classification, date_from=date_from, date_to=date_to, allowed_class_ids=allowed_class_ids)
    log_audit(db, action='analytics.learning_behavior.export_csv', status='success', message='Xuất CSV nhận định học online', user=user, course_id=course_id, target_type='learning_analytics', target_id=class_id, metadata={'classification_note': 'signals_only_not_violation', 'filters': {'campus': campus, 'branch': branch, 'course_id': course_id, 'class_id': class_id, 'classification': classification, 'date_from': date_from, 'date_to': date_to}})
    return Response(content=content, media_type='text/csv; charset=utf-8', headers={'Content-Disposition': 'attachment; filename="learning-behavior-signals.csv"'})


@router.get('/classes/{class_id}/video-summary')
def class_video_summary(class_id: str, course_id: str | None = None, db: Session = Depends(get_db), user: UserContext = Depends(require_permission('view_dashboard'))):
    _assert_analytics_class_access(db, user, class_id)
    return LearningAnalyticsCoreService(db).class_video_summary(class_id=class_id, course_id=course_id)


@router.get('/classes/{class_id}/sessions/progress')
def class_sessions_progress(class_id: str, course_id: str | None = None, db: Session = Depends(get_db), user: UserContext = Depends(require_permission('view_dashboard'))):
    _assert_analytics_class_access(db, user, class_id)
    return LearningAnalyticsCoreService(db).class_sessions_progress(class_id=class_id, course_id=course_id)


@router.get('/videos/{video_id}/students')
def video_students(video_id: str, course_id: str | None = None, class_id: str | None = None, limit: int = Query(default=100, ge=1, le=200), offset: int = Query(default=0, ge=0), db: Session = Depends(get_db), user: UserContext = Depends(require_permission('view_dashboard'))):
    if class_id:
        _assert_analytics_class_access(db, user, class_id)
    else:
        # Without a class_id we cannot safely apply teacher/campus scope to a raw video list.
        allowed = _allowed_class_ids_for_analytics(db, user)
        if allowed is not None:
            return {'video_id': video_id, 'course_id': course_id, 'total': 0, 'items': [], 'message': 'Cần truyền class_id để xem danh sách sinh viên theo phân quyền.'}
    return LearningAnalyticsCoreService(db).video_students(video_id=video_id, course_id=course_id, limit=limit, offset=offset)


@router.get('/subjects/{subject_id}/classes/learning-behavior/overview')
def subject_class_behavior_overview(
    subject_id: str,
    term_id: str | None = None,
    campus: str | None = None,
    branch: str | None = None,
    classification: str | None = None,
    class_id: str | None = None,
    limit: int = Query(default=200, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    user: UserContext = Depends(require_permission('view_dashboard')),
):
    allowed_class_ids = _allowed_class_ids_for_analytics(db, user)
    result = LearningAnalyticsCoreService(db).class_behavior_overview(
        subject_id=subject_id,
        term_id=term_id,
        campus=campus,
        branch=branch,
        classification=classification,
        class_id=class_id,
        allowed_class_ids=allowed_class_ids,
        limit=limit,
        offset=offset,
    )
    result['permission_scope'] = _analytics_permission_scope(db, user)
    return result


@router.get('/classes/{class_id}/doctor')
def class_result_doctor(
    class_id: str,
    course_id: str | None = None,
    db: Session = Depends(get_db),
    user: UserContext = Depends(require_permission('view_dashboard')),
):
    _assert_analytics_class_access(db, user, class_id)
    result = LearningAnalyticsCoreService(db).class_result_doctor(class_id=class_id, course_id=course_id)
    log_audit(
        db,
        action='analytics.learning_behavior.class_doctor.view',
        status='success',
        message='Kiểm tra trạng thái dữ liệu học online của lớp',
        user=user,
        course_id=result.get('resolved_course_id') or course_id,
        target_type='academic_class',
        target_id=class_id,
        metadata={'data_gap': result.get('data_gap'), 'status': result.get('status'), 'signals_only_not_violation': True},
    )
    return result


@router.post('/classes/{class_id}/doctor/recalculate', response_model=AcademicClassSyncJobOut)
def class_result_doctor_enqueue_recalculate(
    class_id: str,
    payload: AnalyticsClassRecalculateRequest | None = None,
    course_id: str | None = None,
    force: bool = False,
    limit: int | None = Query(default=None, ge=1, le=500),
    db: Session = Depends(get_db),
    user: UserContext = Depends(require_permission('view_dashboard')),
):
    _assert_analytics_class_access(db, user, class_id)
    payload = payload or AnalyticsClassRecalculateRequest()
    requested_course_id = payload.course_id or course_id
    requested_force = bool(payload.force or force)
    requested_limit = payload.limit or limit
    doctor = LearningAnalyticsCoreService(db).class_result_doctor(class_id=class_id, course_id=requested_course_id)
    resolved_course_id = str(doctor.get('resolved_course_id') or '').strip()
    if not resolved_course_id:
        raise HTTPException(status_code=409, detail={'code': 'NO_RESOLVED_COURSE', 'message': 'Lớp chưa có Course CMS/Open edX rõ ràng nên chưa thể tính lại.', 'doctor': doctor})
    if doctor.get('data_gap') == 'AMBIGUOUS_COURSE_MAPPING':
        raise HTTPException(status_code=409, detail={'code': 'AMBIGUOUS_COURSE_MAPPING', 'message': 'Mapping Course CMS chưa rõ, hệ thống không tự tính bừa.', 'doctor': doctor})
    job = _enqueue_analytics_recalculate_job(db=db, user=user, class_id=class_id, course_id=resolved_course_id, force=requested_force, limit=requested_limit)
    log_audit(db, action='analytics.learning_behavior.class_doctor.recalculate_enqueue', status='success', message='Đưa tính lại học online từ doctor lớp vào hàng đợi', user=user, course_id=resolved_course_id, target_type='academic_class_sync_job', target_id=job.id, metadata={'class_id': class_id, 'data_gap': doctor.get('data_gap'), 'signals_only_not_violation': True})
    return job


@router.get('/classes/{class_id}/learning-behavior/summary')
def class_behavior_summary(class_id: str, course_id: str | None = None, db: Session = Depends(get_db), user: UserContext = Depends(require_permission('view_dashboard'))):
    _assert_analytics_class_access(db, user, class_id)
    return LearningAnalyticsCoreService(db).behavior_summary(class_id=class_id, course_id=course_id)


@router.get('/classes/{class_id}/learning-behavior')
def class_behavior_rows(
    class_id: str,
    course_id: str | None = None,
    classification: str | None = None,
    limit: int = Query(default=100, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    user: UserContext = Depends(require_permission('view_dashboard')),
):
    _assert_analytics_class_access(db, user, class_id)
    return LearningAnalyticsCoreService(db).behavior_rows(class_id=class_id, course_id=course_id, classification=classification, limit=limit, offset=offset)


@router.get('/classes/{class_id}/students/{username}/learning-behavior')
def student_behavior_detail(class_id: str, username: str, course_id: str | None = None, db: Session = Depends(get_db), user: UserContext = Depends(require_permission('view_dashboard'))):
    _assert_analytics_class_access(db, user, class_id)
    log_audit(db, action='analytics.learning_behavior.view_student', status='success', message='Xem chi tiết học online của sinh viên', user=user, course_id=course_id, target_type='academic_class_student', target_id=f'{class_id}:{username}', metadata={'classification_note': 'signals_only_not_violation'})
    return LearningAnalyticsCoreService(db).student_behavior_detail(class_id=class_id, course_id=course_id, username=username)


@router.get('/classes/{class_id}/students/{username}/session-progress')
def student_session_progress(class_id: str, username: str, course_id: str | None = None, db: Session = Depends(get_db), user: UserContext = Depends(require_permission('view_dashboard'))):
    _assert_analytics_class_access(db, user, class_id)
    detail = LearningAnalyticsCoreService(db).student_behavior_detail(class_id=class_id, course_id=course_id, username=username)
    return {'class_id': class_id, 'username': username, 'course_id': course_id, 'sessions': detail.get('sessions', []), 'timeline_weeks': detail.get('timeline_weeks', []), 'disclaimer': detail.get('disclaimer')}
