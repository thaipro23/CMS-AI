from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import func

from app.core.rbac import UserContext, get_user_context, require_permission
from app.db.session import get_db
from app.models.academic import (
    AcademicClass,
    AcademicClassStudent,
    AcademicStudent,
    AcademicSyncRun,
    AcademicTeacherAssignment,
    AcademicTerm,
)
from app.schemas.academic import (
    AcademicAPSyncIn,
    AcademicBlockOut,
    AcademicClassListOut,
    AcademicClassOut,
    AcademicHealthOut,
    AcademicImportFromJsonIn,
    AcademicImportResultOut,
    AcademicStudentListOut,
    AcademicSubjectOut,
    AcademicSyncCounters,
    AcademicSyncRunOut,
    AcademicTermOut,
)
from app.services.academic_service import AcademicService
from app.services.ap_academic_sync import AcademicImportService
from app.services.audit_log import AuditErrorType, log_audit
from app.services.business_rbac import BusinessRBACService

router = APIRouter()


def _require_academic_admin(db: Session, user: UserContext) -> None:
    service = BusinessRBACService(db)
    if not service.is_system_admin(user):
        # manage_settings also lets current legacy admins pass through the normal require_permission bridge.
        service.require_system_admin(user)


@router.get('/health', response_model=AcademicHealthOut)
def academic_health(user: UserContext = Depends(require_permission('view_questions')), db: Session = Depends(get_db)):
    last_sync = db.query(AcademicSyncRun).order_by(AcademicSyncRun.created_at.desc()).first()
    return {
        'ok': True,
        'terms': db.query(func.count(AcademicTerm.id)).scalar() or 0,
        'classes': db.query(func.count(AcademicClass.id)).scalar() or 0,
        'students': db.query(func.count(AcademicStudent.id)).scalar() or 0,
        'assignments': db.query(func.count(AcademicTeacherAssignment.id)).scalar() or 0,
        'last_sync': last_sync,
    }


@router.get('/terms', response_model=list[AcademicTermOut])
def list_terms(
    branch: str | None = None,
    active: bool | None = True,
    user: UserContext = Depends(require_permission('view_questions')),
    db: Session = Depends(get_db),
):
    return AcademicService(db).list_terms(branch=branch, active=active)


@router.get('/blocks', response_model=list[AcademicBlockOut])
def list_blocks(
    term_id: str,
    active: bool | None = True,
    user: UserContext = Depends(require_permission('view_questions')),
    db: Session = Depends(get_db),
):
    return AcademicService(db).list_blocks(term_id=term_id, active=active)


@router.get('/subjects', response_model=list[AcademicSubjectOut])
def list_subjects(
    term_id: str | None = None,
    block_id: str | None = None,
    search: str | None = None,
    branch: str | None = None,
    user: UserContext = Depends(require_permission('view_questions')),
    db: Session = Depends(get_db),
):
    return AcademicService(db).list_subjects(term_id=term_id, block_id=block_id, search=search, branch=branch)


@router.get('/teacher/classes', response_model=AcademicClassListOut)
def list_teacher_classes(
    term_id: str | None = None,
    block_id: str | None = None,
    subject_id: str | None = None,
    search: str | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    user: UserContext = Depends(require_permission('view_questions')),
    db: Session = Depends(get_db),
):
    return AcademicService(db).list_teacher_classes(
        user,
        term_id=term_id,
        block_id=block_id,
        subject_id=subject_id,
        search=search,
        page=page,
        page_size=page_size,
    )


@router.get('/classes/{class_id}', response_model=AcademicClassOut)
def get_class_detail(
    class_id: str,
    user: UserContext = Depends(require_permission('view_questions')),
    db: Session = Depends(get_db),
):
    return AcademicService(db).get_class_detail(user, class_id)


@router.get('/classes/{class_id}/students', response_model=AcademicStudentListOut)
def list_class_students(
    class_id: str,
    search: str | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    user: UserContext = Depends(require_permission('view_questions')),
    db: Session = Depends(get_db),
):
    return AcademicService(db).list_class_students(user, class_id, search=search, page=page, page_size=page_size)


@router.post('/sync/from-json', response_model=AcademicImportResultOut)
def sync_from_json(
    payload: AcademicImportFromJsonIn,
    user: UserContext = Depends(require_permission('manage_settings')),
    db: Session = Depends(get_db),
):
    _require_academic_admin(db, user)
    importer = AcademicImportService(db)
    run = importer.create_run(source=payload.source or 'ap_json', mode='json', requested_by=user.user_id, campus=payload.campus, branch=payload.branch)
    try:
        counters = importer.import_payload(payload.payload, run=run, campus=payload.campus, branch=payload.branch)
        run = importer.finish_run(run, counters)
        log_audit(
            db,
            action='academic.ap.import_json',
            status='success',
            message='Đồng bộ dữ liệu AP từ JSON thành công',
            user=user,
            target_type='academic_sync_run',
            target_id=run.id,
            metadata={'counters': counters.as_dict(), 'campus': payload.campus, 'branch': payload.branch},
        )
        return {'ok': True, 'message': 'Đã import dữ liệu AP từ JSON', 'sync_run': run, 'counters': counters.as_dict()}
    except Exception as exc:
        db.rollback()
        run = importer.finish_run(run, error=str(exc))
        log_audit(db, action='academic.ap.import_json', status='failed', error_type=AuditErrorType.SYSTEM_ERROR, message=str(exc), user=user, target_type='academic_sync_run', target_id=run.id)
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post('/sync/ap', response_model=AcademicImportResultOut)
def sync_from_ap(
    payload: AcademicAPSyncIn,
    user: UserContext = Depends(require_permission('manage_settings')),
    db: Session = Depends(get_db),
):
    _require_academic_admin(db, user)
    importer = AcademicImportService(db)
    run, counters = importer.sync_from_ap(
        requested_by=user.user_id,
        term_name=payload.term_name,
        campus=payload.campus,
        branch=payload.branch,
        subject_codes=payload.subject_codes,
        max_subjects=payload.max_subjects,
        dry_run=payload.dry_run,
    )
    status = 'success' if run.status == 'completed' else 'failed'
    log_audit(
        db,
        action='academic.ap.sync_api',
        status=status,
        error_type=None if status == 'success' else AuditErrorType.EXTERNAL_SERVICE_ERROR,
        message='Đồng bộ dữ liệu AP qua API hoàn tất' if status == 'success' else run.error_message,
        user=user,
        target_type='academic_sync_run',
        target_id=run.id,
        metadata={
            'term_name': payload.term_name,
            'campus': payload.campus,
            'branch': payload.branch,
            'subject_count': len(payload.subject_codes),
            'dry_run': payload.dry_run,
            'counters': counters.as_dict(),
        },
    )
    if run.status != 'completed':
        raise HTTPException(status_code=502, detail=run.error_message or 'Đồng bộ AP thất bại')
    return {'ok': True, 'message': 'Đã đồng bộ dữ liệu AP', 'sync_run': run, 'counters': counters.as_dict()}
