from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import func

from app.core.rbac import UserContext, get_user_context, require_permission
from app.db.session import get_db
from app.models.academic import (
    AcademicCampus,
    AcademicClass,
    AcademicClassStudent,
    AcademicStudent,
    AcademicSyncRun,
    AcademicTeacherAssignment,
    AcademicTerm,
)
from app.schemas.academic import (
    AcademicAPSyncIn,
    AcademicAPSyncOptionsOut,
    AcademicCampusOut,
    AcademicCampusUpsertIn,
    AcademicBlockOut,
    AcademicClassListOut,
    AcademicClassOut,
    AcademicClassCourseMappingCreateIn,
    AcademicClassCourseMappingOut,
    AcademicClassCourseMappingProposalOut,
    AcademicClassCourseMappingValidateIn,
    AcademicCourseMappingCreateIn,
    AcademicCourseMappingListOut,
    AcademicCourseMappingOut,
    AcademicCourseMappingValidateIn,
    AcademicCourseMappingValidationOut,
    AcademicHealthOut,
    AcademicImportFromJsonIn,
    AcademicImportResultOut,
    AcademicMappingResolveOut,
    AcademicMappingSummaryOut,
    AcademicManualMappingImportIn,
    AcademicManualMappingImportOut,
    AcademicResolveClassUsersIn,
    AcademicStudentListOut,
    AcademicSubjectOut,
    AcademicSyncCounters,
    AcademicSyncRunOut,
    AcademicTermOut,
    AcademicTermUpsertIn,
    AcademicTermWithBlocksOut,
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




@router.get('/terms/{term_id}/with-blocks', response_model=AcademicTermWithBlocksOut)
def get_term_with_blocks(
    term_id: str,
    active_blocks: bool | None = None,
    user: UserContext = Depends(require_permission('manage_settings')),
    db: Session = Depends(get_db),
):
    _require_academic_admin(db, user)
    service = AcademicService(db)
    term = db.query(AcademicTerm).filter(AcademicTerm.id == term_id).first()
    if not term:
        raise HTTPException(status_code=404, detail='Không tìm thấy học kỳ')
    blocks = service.list_blocks(term_id=term_id, active=active_blocks)
    data = AcademicTermOut.model_validate(term).model_dump()
    data['blocks'] = [AcademicBlockOut.model_validate(item).model_dump() for item in blocks]
    return data


@router.post('/terms', response_model=AcademicTermWithBlocksOut)
def save_academic_term(
    payload: AcademicTermUpsertIn,
    user: UserContext = Depends(require_permission('manage_settings')),
    db: Session = Depends(get_db),
):
    _require_academic_admin(db, user)
    term = AcademicService(db).save_term_with_blocks(payload.model_dump())
    blocks = AcademicService(db).list_blocks(term_id=term.id, active=None)
    log_audit(db, action='academic.term.upsert', status='success', message='Lưu học kỳ/block thành công', user=user, target_type='academic_term', target_id=term.id, metadata={'term_code': term.term_code, 'branch': term.branch, 'block_count': len(blocks)})
    data = AcademicTermOut.model_validate(term).model_dump()
    data['blocks'] = [AcademicBlockOut.model_validate(item).model_dump() for item in blocks]
    return data


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



@router.get('/course-mappings', response_model=AcademicCourseMappingListOut)
def list_academic_course_mappings(
    term_id: str | None = None,
    block_id: str | None = None,
    subject_id: str | None = None,
    search: str | None = None,
    active: bool | None = True,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    user: UserContext = Depends(require_permission('manage_settings')),
    db: Session = Depends(get_db),
):
    _require_academic_admin(db, user)
    return AcademicService(db).list_course_mappings(user, term_id=term_id, block_id=block_id, subject_id=subject_id, search=search, active=active, page=page, page_size=page_size)


@router.post('/course-mappings/validate', response_model=AcademicCourseMappingValidationOut)
def validate_academic_course_mapping(
    payload: AcademicCourseMappingValidateIn,
    user: UserContext = Depends(require_permission('manage_settings')),
    db: Session = Depends(get_db),
):
    _require_academic_admin(db, user)
    result = AcademicService(db).validate_course_mapping_payload(**payload.model_dump())
    log_audit(
        db,
        action='academic.course_mapping.validate',
        status='success' if result.get('ok') else 'failed',
        error_type=None if result.get('ok') else AuditErrorType.VALIDATION_ERROR,
        message=result.get('message', ''),
        user=user,
        course_id=payload.openedx_course_id,
        target_type='academic_course_mapping',
        metadata=result,
    )
    return result


@router.post('/course-mappings', response_model=AcademicCourseMappingOut)
def create_academic_course_mapping(
    payload: AcademicCourseMappingCreateIn,
    user: UserContext = Depends(require_permission('manage_settings')),
    db: Session = Depends(get_db),
):
    _require_academic_admin(db, user)
    try:
        item = AcademicService(db).create_or_update_course_mapping(user, payload.model_dump())
        log_audit(db, action='academic.course_mapping.save', status='success', message='Lưu mapping AP ↔ Open edX course thành công', user=user, course_id=item.get('openedx_course_id'), target_type='academic_course_mapping', target_id=item.get('id'), metadata={'validation_status': item.get('validation_status')})
        return item
    except HTTPException:
        raise
    except Exception as exc:
        db.rollback()
        log_audit(db, action='academic.course_mapping.save', status='failed', error_type=AuditErrorType.VALIDATION_ERROR, message=str(exc), user=user, target_type='academic_course_mapping')
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.delete('/course-mappings/{mapping_id}', response_model=AcademicCourseMappingOut)
def deactivate_academic_course_mapping(
    mapping_id: str,
    user: UserContext = Depends(require_permission('manage_settings')),
    db: Session = Depends(get_db),
):
    _require_academic_admin(db, user)
    item = AcademicService(db).deactivate_course_mapping(user, mapping_id)
    log_audit(db, action='academic.course_mapping.deactivate', status='success', message='Đã tắt mapping course cấp môn/kỳ/block', user=user, course_id=item.get('openedx_course_id'), target_type='academic_course_mapping', target_id=mapping_id)
    return item


@router.get('/classes/{class_id}/course-mapping/proposal', response_model=AcademicClassCourseMappingProposalOut)
def get_class_course_mapping_proposal(
    class_id: str,
    user: UserContext = Depends(require_permission('view_questions')),
    db: Session = Depends(get_db),
):
    return AcademicService(db).class_course_mapping_proposal(user, class_id)


@router.post('/classes/{class_id}/course-mapping/validate', response_model=AcademicCourseMappingValidationOut)
def validate_class_course_mapping(
    class_id: str,
    payload: AcademicClassCourseMappingValidateIn,
    user: UserContext = Depends(require_permission('manage_settings')),
    db: Session = Depends(get_db),
):
    _require_academic_admin(db, user)
    result = AcademicService(db).validate_class_course_mapping(user, class_id, payload.model_dump())
    log_audit(db, action='academic.class_course_mapping.validate', status='success' if result.get('ok') else 'failed', error_type=None if result.get('ok') else AuditErrorType.VALIDATION_ERROR, message=result.get('message', ''), user=user, course_id=payload.openedx_course_id, target_type='academic_class', target_id=class_id, metadata=result)
    return result


@router.post('/classes/{class_id}/course-mapping', response_model=AcademicClassCourseMappingOut)
def save_class_course_mapping(
    class_id: str,
    payload: AcademicClassCourseMappingCreateIn,
    user: UserContext = Depends(require_permission('manage_settings')),
    db: Session = Depends(get_db),
):
    _require_academic_admin(db, user)
    try:
        item = AcademicService(db).create_or_update_class_course_mapping(user, class_id, payload.model_dump())
        log_audit(db, action='academic.class_course_mapping.save', status='success', message='Lưu mapping lớp AP sang Open edX course thành công', user=user, course_id=item.get('openedx_course_id'), target_type='academic_class', target_id=class_id, metadata={'validation_status': item.get('validation_status'), 'cohort': item.get('openedx_cohort_name')})
        return item
    except HTTPException:
        raise
    except Exception as exc:
        db.rollback()
        log_audit(db, action='academic.class_course_mapping.save', status='failed', error_type=AuditErrorType.VALIDATION_ERROR, message=str(exc), user=user, target_type='academic_class', target_id=class_id)
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.delete('/classes/{class_id}/course-mapping', response_model=AcademicClassCourseMappingOut)
def deactivate_class_course_mapping(
    class_id: str,
    user: UserContext = Depends(require_permission('manage_settings')),
    db: Session = Depends(get_db),
):
    _require_academic_admin(db, user)
    item = AcademicService(db).deactivate_class_course_mapping(user, class_id)
    log_audit(db, action='academic.class_course_mapping.deactivate', status='success', message='Đã tắt mapping course riêng của lớp', user=user, course_id=item.get('openedx_course_id'), target_type='academic_class', target_id=class_id)
    return item


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


@router.get('/classes/{class_id}/mapping-summary', response_model=AcademicMappingSummaryOut)
def get_class_mapping_summary(
    class_id: str,
    user: UserContext = Depends(require_permission('view_questions')),
    db: Session = Depends(get_db),
):
    return AcademicService(db).mapping_summary_for_class(user, class_id)


@router.post('/classes/{class_id}/resolve-openedx-users', response_model=AcademicMappingResolveOut)
def resolve_class_openedx_users(
    class_id: str,
    payload: AcademicResolveClassUsersIn,
    user: UserContext = Depends(require_permission('view_questions')),
    db: Session = Depends(get_db),
):
    service = AcademicService(db)
    try:
        result = service.resolve_class_openedx_users(user, class_id, force=payload.force, limit=payload.limit)
        log_audit(
            db,
            action='academic.openedx_user_mapping.resolve_class',
            status='success',
            message='Resolve Open edX user mapping theo AP username thành công',
            user=user,
            target_type='academic_class',
            target_id=class_id,
            metadata={'counts': result.get('counts', {}), 'updated': result.get('updated', 0)},
        )
        return result
    except HTTPException:
        raise
    except Exception as exc:
        db.rollback()
        log_audit(
            db,
            action='academic.openedx_user_mapping.resolve_class',
            status='failed',
            error_type=AuditErrorType.EXTERNAL_SERVICE_ERROR,
            message=str(exc),
            user=user,
            target_type='academic_class',
            target_id=class_id,
        )
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@router.post('/openedx-user-mappings/import', response_model=AcademicManualMappingImportOut)
def import_openedx_user_mappings(
    payload: AcademicManualMappingImportIn,
    user: UserContext = Depends(require_permission('manage_settings')),
    db: Session = Depends(get_db),
):
    _require_academic_admin(db, user)
    result = AcademicService(db).import_openedx_user_mappings([item.model_dump() for item in payload.records], requested_by=user.user_id)
    log_audit(
        db,
        action='academic.openedx_user_mapping.import',
        status='success',
        message='Import mapping AP username sang Open edX user thành công',
        user=user,
        target_type='openedx_user_mappings',
        target_id='bulk',
        metadata={'counters': result.get('counters', {}), 'total': result.get('total', 0)},
    )
    return result



@router.get('/campuses', response_model=list[AcademicCampusOut])
def list_academic_campuses(
    branch: str | None = Query('poly'),
    active: bool | None = True,
    user: UserContext = Depends(require_permission('manage_settings')),
    db: Session = Depends(get_db),
):
    _require_academic_admin(db, user)
    query = db.query(AcademicCampus)
    if branch:
        query = query.filter(AcademicCampus.branch == branch)
    if active is not None:
        query = query.filter(AcademicCampus.active.is_(active))
    return query.order_by(AcademicCampus.sort_order.asc(), AcademicCampus.campus_code.asc()).all()


@router.post('/campuses', response_model=AcademicCampusOut)
def upsert_academic_campus(
    payload: AcademicCampusUpsertIn,
    user: UserContext = Depends(require_permission('manage_settings')),
    db: Session = Depends(get_db),
):
    _require_academic_admin(db, user)
    code = (payload.campus_code or '').strip().lower()
    branch = (payload.branch or 'poly').strip().lower()
    if not code:
        raise HTTPException(status_code=400, detail='Thiếu mã cơ sở AP')
    campus = db.query(AcademicCampus).filter(AcademicCampus.campus_code == code, AcademicCampus.branch == branch).first()
    if not campus:
        campus = AcademicCampus(campus_code=code, branch=branch, created_at=func.now(), updated_at=func.now())
        db.add(campus)
    campus.campus_name = payload.campus_name.strip() or code.upper()
    campus.active = payload.active
    campus.sort_order = payload.sort_order
    campus.metadata_json = {'source': 'manual_ui'}
    db.commit()
    db.refresh(campus)
    log_audit(db, action='academic.campus.upsert', status='success', message='Lưu cơ sở AP thành công', user=user, target_type='academic_campus', target_id=campus.id, metadata={'campus_code': code, 'branch': branch})
    return campus


@router.post('/campuses/seed-from-env', response_model=list[AcademicCampusOut])
def seed_academic_campuses_from_env(
    branch: str = Query('poly'),
    user: UserContext = Depends(require_permission('manage_settings')),
    db: Session = Depends(get_db),
):
    _require_academic_admin(db, user)
    items = AcademicImportService(db).seed_campuses_from_settings(branch=branch)
    log_audit(db, action='academic.campus.seed_from_env', status='success', message='Seed cơ sở AP từ env thành công', user=user, target_type='academic_campus', target_id='bulk', metadata={'branch': branch, 'count': len(items)})
    return items


@router.get('/sync/ap/options', response_model=AcademicAPSyncOptionsOut)
def get_ap_sync_options(
    term_name: str = Query('', description='Tên kỳ AP, ví dụ Summer 2026. Có term_name thì backend gọi AP /get-course để lấy môn.'),
    branch: str = Query('poly'),
    include_subjects: bool = Query(True),
    user: UserContext = Depends(require_permission('manage_settings')),
    db: Session = Depends(get_db),
):
    _require_academic_admin(db, user)
    return AcademicImportService(db).get_ap_sync_options(term_name=term_name or None, branch=branch, include_subjects=include_subjects)


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
        sync_scope=payload.sync_scope,
        campuses=payload.campuses,
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
            'sync_scope': payload.sync_scope,
            'campus': payload.campus,
            'campuses': payload.campuses,
            'branch': payload.branch,
            'subject_count': len(payload.subject_codes),
            'dry_run': payload.dry_run,
            'counters': counters.as_dict(),
        },
    )
    if run.status != 'completed':
        raise HTTPException(status_code=502, detail=run.error_message or 'Đồng bộ AP thất bại')
    return {'ok': True, 'message': 'Đã đồng bộ dữ liệu AP', 'sync_run': run, 'counters': counters.as_dict()}
