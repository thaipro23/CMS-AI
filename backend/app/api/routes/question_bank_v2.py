from datetime import datetime, timezone
from math import ceil

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, status
from sqlalchemy import and_, func, or_
from sqlalchemy.orm import Session

from app.core.rbac import UserContext, get_user_context, require_permission
from app.db.session import get_db
from app.models.question import Question
from app.models.question_bank import (
    Department,
    EdxCourseChapterMapping,
    EdxCourseMapping,
    LearningMaterialVersion,
    MaterialChunk,
    QuestionBankRelease,
    QuestionBankVersion,
    QuizBlueprint,
    CourseQuizInstance,
    Subject,
    SubjectOffering,
    SubjectChapter,
)
from app.schemas.question_bank import (
    BankReleaseCreate,
    BankReleaseOut,
    BankReleasePublishOut,
    BankReleasePublishRequest,
    BankReleaseQuizCreateOut,
    BankReleaseQuizCreateRequest,
    BankReleaseQuizPlanOut,
    BankReleaseQuizPreviewRequest,
    BankSummaryOut,
    BankVersionCreate,
    BankVersionOut,
    ChapterCreate,
    ChapterUpdate,
    ChapterOut,
    EntityDeleteOut,
    CourseChapterMappingCreate,
    CourseChapterMappingOut,
    CourseChapterMappingValidateRequest,
    CourseMappingCreate,
    CourseMappingOut,
    CourseMappingValidateRequest,
    MappingValidationOut,
    DepartmentCreate,
    DepartmentUpdate,
    DepartmentOut,
    MaterialVersionCreate,
    MaterialVersionOut,
    MaterialChunkOut,
    MaterialUploadOut,
    MaterialDeleteOut,
    BankGenerateRequest,
    BankGeneratePreviewOut,
    BankGenerateOut,
    BankVersionQuestionOut,
    BankQuestionListItemOut,
    BankQuestionDetailOut,
    BankVersionDiffPreviewRequest,
    BankVersionDiffPreviewOut,
    BankCarryOverRequest,
    BankCarryOverOut,
    BankRetireQuestionsRequest,
    BankRetireQuestionsOut,
    BankQuestionReviewRequest,
    BankQuestionUpdateRequest,
    BankQuestionReviewOut,
    BankQuestionBulkReviewRequest,
    BankQuestionBulkReviewOut,
    BankDocumentDiffResolveRequest,
    BankDocumentDiffResolveOut,
    BankReleaseReadinessOut,
    CourseQuizInstanceOut,
    CourseQuizRollbackRequest,
    CourseQuizRollbackOut,
    QuizBlueprintCreate,
    QuizBlueprintOut,
    QuizAutoMapRequest,
    QuizAutoMapOut,
    SubjectCreate,
    SubjectUpdate,
    SubjectOut,
    SubjectOfferingCreate,
    SubjectOfferingUpdate,
    SubjectOfferingOut,
    CursorPaginatedOut,
    PaginatedOut,
)
from app.services.audit_log import AuditErrorType, log_audit
from app.services.question_bank_service import VersionedQuestionBankService
from app.services.business_rbac import BusinessRBACService
from app.services.bank_dashboard_stats import BankDashboardStatsService
from app.services.bank_search import BankSearchService

router = APIRouter()


_BANK_UPLOAD_MAX_BYTES = 50 * 1024 * 1024




def _clamp_page(page: int, page_size: int, *, max_page_size: int = 100) -> tuple[int, int]:
    safe_page = max(1, int(page or 1))
    safe_page_size = max(1, min(int(page_size or 50), max_page_size))
    return safe_page, safe_page_size


def _empty_page(page: int, page_size: int, *, max_page_size: int = 100) -> dict:
    page, page_size = _clamp_page(page, page_size, max_page_size=max_page_size)
    return {
        'items': [],
        'total': 0,
        'page': page,
        'page_size': page_size,
        'total_pages': 0,
        'has_next': False,
    }


def _paginate(query, *, page: int = 1, page_size: int = 50, max_page_size: int = 100) -> dict:
    page, page_size = _clamp_page(page, page_size, max_page_size=max_page_size)
    total = int(query.order_by(None).count())
    items = query.offset((page - 1) * page_size).limit(page_size).all()
    total_pages = int(ceil(total / page_size)) if total else 0
    return {
        'items': items,
        'total': total,
        'page': page,
        'page_size': page_size,
        'total_pages': total_pages,
        'has_next': page * page_size < total,
    }

async def _read_bank_upload_limited(file: UploadFile, *, max_bytes: int = _BANK_UPLOAD_MAX_BYTES) -> bytes:
    content_length = None
    try:
        content_length = int(file.headers.get('content-length') or 0)
    except Exception:
        content_length = None
    if content_length and content_length > max_bytes:
        raise HTTPException(status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail='File quá lớn. Giới hạn hiện tại là 50MB/file.')
    chunks: list[bytes] = []
    total = 0
    while True:
        chunk = await file.read(1024 * 1024)
        if not chunk:
            break
        total += len(chunk)
        if total > max_bytes:
            raise HTTPException(status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail='File quá lớn. Giới hạn hiện tại là 50MB/file.')
        chunks.append(chunk)
    return b''.join(chunks)


def _biz(db: Session) -> BusinessRBACService:
    return BusinessRBACService(db)


def _require_business(db: Session, user: UserContext, permission: str, scope_type: str = 'SYSTEM', scope_id: str | None = '*') -> None:
    _biz(db).require_permission(user, permission, scope_type, scope_id)


def _require_bank_version(db: Session, user: UserContext, permission: str, bank_version_id: str) -> None:
    _require_business(db, user, permission, 'BANK_VERSION', bank_version_id)


def _require_release(db: Session, user: UserContext, permission: str, release_id: str) -> None:
    _require_business(db, user, permission, 'RELEASE', release_id)


@router.get('/summary', response_model=BankSummaryOut)
def summary(db: Session = Depends(get_db), user: UserContext = Depends(require_permission('view_questions'))):
    return VersionedQuestionBankService(db).summary()


@router.get('/dashboard/overview')
def dashboard_overview(db: Session = Depends(get_db), user: UserContext = Depends(require_permission('view_questions'))):
    return VersionedQuestionBankService(db).dashboard_overview()


@router.get('/dashboard/search')
def dashboard_search(q: str = '', limit: int = 20, db: Session = Depends(get_db), user: UserContext = Depends(require_permission('view_questions'))):
    return VersionedQuestionBankService(db).dashboard_search(q=q, limit=limit, user=user)


@router.get('/search')
def bank_search(q: str = Query('', min_length=0), limit: int = Query(20, ge=1, le=100), include_questions: bool = True, db: Session = Depends(get_db), user: UserContext = Depends(require_permission('view_questions'))):
    return BankSearchService(db).search_grouped(q=q, user=user, limit=limit, include_questions=include_questions)


@router.get('/admin/stats/health')
def bank_stats_health(db: Session = Depends(get_db), user: UserContext = Depends(require_permission('manage_settings'))):
    _biz(db).require_system_admin(user)
    return BankDashboardStatsService(db).stats_health()


@router.post('/admin/stats/rebuild')
def rebuild_bank_stats(chapter_id: str | None = Query(None), db: Session = Depends(get_db), user: UserContext = Depends(require_permission('manage_settings'))):
    _biz(db).require_system_admin(user)
    try:
        result = BankDashboardStatsService(db).rebuild_chapter_stats(chapter_id=chapter_id, commit=True)
        log_audit(db, action='question_bank.stats.rebuild', status='success', message='Rebuild Bank Dashboard stats thành công', user=user, target_type='chapter' if chapter_id else 'bank_dashboard_stats', target_id=chapter_id)
        return result
    except Exception as exc:
        log_audit(db, action='question_bank.stats.rebuild', status='failed', error_type=AuditErrorType.VALIDATION_ERROR, message=str(exc), user=user, target_type='chapter' if chapter_id else 'bank_dashboard_stats', target_id=chapter_id)
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get('/admin/search/health')
def bank_search_health(db: Session = Depends(get_db), user: UserContext = Depends(require_permission('manage_settings'))):
    _biz(db).require_system_admin(user)
    return BankSearchService(db).health()


@router.post('/admin/search/rebuild')
def rebuild_bank_search_index(bank_version_id: str | None = Query(None), chapter_id: str | None = Query(None), db: Session = Depends(get_db), user: UserContext = Depends(require_permission('manage_settings'))):
    _biz(db).require_system_admin(user)
    try:
        result = BankSearchService(db).rebuild(bank_version_id=bank_version_id, chapter_id=chapter_id, commit=True)
        log_audit(db, action='question_bank.search.rebuild', status='success', message='Rebuild Bank Search index thành công', user=user, target_type='bank_search_index', target_id=bank_version_id or chapter_id)
        return result
    except Exception as exc:
        log_audit(db, action='question_bank.search.rebuild', status='failed', error_type=AuditErrorType.VALIDATION_ERROR, message=str(exc), user=user, target_type='bank_search_index', target_id=bank_version_id or chapter_id)
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get('/departments/summary')
def department_summaries(db: Session = Depends(get_db), user: UserContext = Depends(require_permission('view_questions'))):
    return VersionedQuestionBankService(db).department_summaries()


@router.get('/departments/{department_id}/subjects/summary')
def subject_summaries(department_id: str, db: Session = Depends(get_db), user: UserContext = Depends(require_permission('view_questions'))):
    return VersionedQuestionBankService(db).subject_summaries(department_id=department_id)


@router.get('/subjects/{subject_id}/versions/summary')
def subject_version_summaries(subject_id: str, db: Session = Depends(get_db), user: UserContext = Depends(require_permission('view_questions'))):
    return VersionedQuestionBankService(db).subject_version_summaries(subject_id=subject_id)


@router.get('/subject-versions/{subject_offering_id}/chapters/summary')
def chapter_summaries(subject_offering_id: str, db: Session = Depends(get_db), user: UserContext = Depends(require_permission('view_questions'))):
    return VersionedQuestionBankService(db).chapter_summaries(subject_offering_id=subject_offering_id)


@router.get('/departments', response_model=PaginatedOut[DepartmentOut])
def list_departments(page: int = Query(1, ge=1), page_size: int = Query(50, ge=1, le=50), db: Session = Depends(get_db), user: UserContext = Depends(require_permission('view_questions'))):
    query = _biz(db).apply_department_filter(db.query(Department), user)
    return _paginate(query.order_by(Department.code.asc()), page=page, page_size=page_size, max_page_size=50)


@router.post('/departments', response_model=DepartmentOut)
def create_department(payload: DepartmentCreate, db: Session = Depends(get_db), user: UserContext = Depends(require_permission('manage_settings'))):
    _require_business(db, user, 'department.manage_all')
    try:
        item = VersionedQuestionBankService(db).create_department(**payload.model_dump())
        log_audit(db, action='question_bank.department.create', status='success', message='Tạo bộ môn thành công', user=user, target_type='department', target_id=item.id)
        return item
    except Exception as exc:
        log_audit(db, action='question_bank.department.create', status='failed', error_type=AuditErrorType.VALIDATION_ERROR, message=str(exc), user=user, target_type='department')
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.patch('/departments/{department_id}', response_model=DepartmentOut)
def update_department(department_id: str, payload: DepartmentUpdate, db: Session = Depends(get_db), user: UserContext = Depends(require_permission('manage_settings'))):
    _require_business(db, user, 'department.manage_all')
    try:
        item = VersionedQuestionBankService(db).update_department(department_id, **payload.model_dump(exclude_unset=True))
        log_audit(db, action='question_bank.department.update', status='success', message='Sửa bộ môn thành công', user=user, target_type='department', target_id=item.id)
        return item
    except Exception as exc:
        log_audit(db, action='question_bank.department.update', status='failed', error_type=AuditErrorType.VALIDATION_ERROR, message=str(exc), user=user, target_type='department', target_id=department_id)
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.delete('/departments/{department_id}', response_model=EntityDeleteOut)
def delete_department(department_id: str, db: Session = Depends(get_db), user: UserContext = Depends(require_permission('manage_settings'))):
    _require_business(db, user, 'department.manage_all')
    try:
        result = VersionedQuestionBankService(db).delete_department(department_id)
        log_audit(db, action='question_bank.department.delete', status='success', message=result.get('message', 'Đã xóa bộ môn'), user=user, target_type='department', target_id=department_id)
        return result
    except Exception as exc:
        log_audit(db, action='question_bank.department.delete', status='failed', error_type=AuditErrorType.VALIDATION_ERROR, message=str(exc), user=user, target_type='department', target_id=department_id)
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get('/subjects', response_model=PaginatedOut[SubjectOut])
def list_subjects(department_id: str | None = None, page: int = Query(1, ge=1), page_size: int = Query(50, ge=1, le=100), db: Session = Depends(get_db), user: UserContext = Depends(require_permission('view_questions'))):
    query = _biz(db).apply_subject_filter(db.query(Subject), user)
    if department_id:
        _require_business(db, user, 'bank.view', 'DEPARTMENT', department_id)
        query = query.filter(Subject.department_id == department_id)
    return _paginate(query.order_by(Subject.code.asc()), page=page, page_size=page_size, max_page_size=100)


@router.post('/subjects', response_model=SubjectOut)
def create_subject(payload: SubjectCreate, db: Session = Depends(get_db), user: UserContext = Depends(get_user_context)):
    _require_business(db, user, 'subject.create', 'DEPARTMENT', payload.department_id)
    try:
        item = VersionedQuestionBankService(db).create_subject(**payload.model_dump())
        log_audit(db, action='question_bank.subject.create', status='success', message='Tạo môn học thành công', user=user, target_type='subject', target_id=item.id)
        return item
    except Exception as exc:
        log_audit(db, action='question_bank.subject.create', status='failed', error_type=AuditErrorType.VALIDATION_ERROR, message=str(exc), user=user, target_type='subject')
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.patch('/subjects/{subject_id}', response_model=SubjectOut)
def update_subject(subject_id: str, payload: SubjectUpdate, db: Session = Depends(get_db), user: UserContext = Depends(get_user_context)):
    _require_business(db, user, 'subject.update', 'SUBJECT', subject_id)
    try:
        item = VersionedQuestionBankService(db).update_subject(subject_id, **payload.model_dump(exclude_unset=True))
        log_audit(db, action='question_bank.subject.update', status='success', message='Sửa môn thành công', user=user, target_type='subject', target_id=item.id)
        return item
    except Exception as exc:
        log_audit(db, action='question_bank.subject.update', status='failed', error_type=AuditErrorType.VALIDATION_ERROR, message=str(exc), user=user, target_type='subject', target_id=subject_id)
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.delete('/subjects/{subject_id}', response_model=EntityDeleteOut)
def delete_subject(subject_id: str, db: Session = Depends(get_db), user: UserContext = Depends(get_user_context)):
    _require_business(db, user, 'subject.update', 'SUBJECT', subject_id)
    try:
        result = VersionedQuestionBankService(db).delete_subject(subject_id)
        log_audit(db, action='question_bank.subject.delete', status='success', message=result.get('message', 'Đã xóa môn'), user=user, target_type='subject', target_id=subject_id)
        return result
    except Exception as exc:
        log_audit(db, action='question_bank.subject.delete', status='failed', error_type=AuditErrorType.VALIDATION_ERROR, message=str(exc), user=user, target_type='subject', target_id=subject_id)
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get('/subject-offerings', response_model=PaginatedOut[SubjectOfferingOut])
@router.get('/subject-versions', response_model=PaginatedOut[SubjectOfferingOut])
def list_subject_offerings(subject_id: str | None = None, page: int = Query(1, ge=1), page_size: int = Query(50, ge=1, le=100), db: Session = Depends(get_db), user: UserContext = Depends(require_permission('view_questions'))):
    query = db.query(SubjectOffering)
    subject_ids = _biz(db).accessible_subject_ids(user)
    if subject_ids is not None:
        if not subject_ids:
            return _empty_page(page, page_size, max_page_size=100)
        query = query.filter(SubjectOffering.subject_id.in_(subject_ids))
    if subject_id:
        _require_business(db, user, 'bank.view', 'SUBJECT', subject_id)
        query = query.filter(SubjectOffering.subject_id == subject_id)
    return _paginate(query.order_by(SubjectOffering.code.asc()), page=page, page_size=page_size, max_page_size=100)


@router.post('/subject-offerings', response_model=SubjectOfferingOut)
@router.post('/subject-versions', response_model=SubjectOfferingOut)
def create_subject_offering(payload: SubjectOfferingCreate, db: Session = Depends(get_db), user: UserContext = Depends(get_user_context)):
    _require_business(db, user, 'subject.update', 'SUBJECT', payload.subject_id)
    try:
        item = VersionedQuestionBankService(db).create_subject_offering(**payload.model_dump(), actor=user.user_id)
        log_audit(db, action='question_bank.subject_offering.create', status='success', message='Tạo phiên bản môn thành công', user=user, target_type='subject_offering', target_id=item.id)
        return item
    except Exception as exc:
        log_audit(db, action='question_bank.subject_offering.create', status='failed', error_type=AuditErrorType.VALIDATION_ERROR, message=str(exc), user=user, target_type='subject_offering')
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.patch('/subject-offerings/{subject_offering_id}', response_model=SubjectOfferingOut)
@router.patch('/subject-versions/{subject_offering_id}', response_model=SubjectOfferingOut)
def update_subject_offering(subject_offering_id: str, payload: SubjectOfferingUpdate, db: Session = Depends(get_db), user: UserContext = Depends(get_user_context)):
    _require_business(db, user, 'subject.update', 'SUBJECT_VERSION', subject_offering_id)
    try:
        item = VersionedQuestionBankService(db).update_subject_offering(subject_offering_id, **payload.model_dump(exclude_unset=True))
        log_audit(db, action='question_bank.subject_offering.update', status='success', message='Sửa phiên bản môn thành công', user=user, target_type='subject_offering', target_id=item.id)
        return item
    except Exception as exc:
        log_audit(db, action='question_bank.subject_offering.update', status='failed', error_type=AuditErrorType.VALIDATION_ERROR, message=str(exc), user=user, target_type='subject_offering', target_id=subject_offering_id)
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.delete('/subject-offerings/{subject_offering_id}', response_model=EntityDeleteOut)
@router.delete('/subject-versions/{subject_offering_id}', response_model=EntityDeleteOut)
def delete_subject_offering(subject_offering_id: str, db: Session = Depends(get_db), user: UserContext = Depends(get_user_context)):
    _require_business(db, user, 'subject.update', 'SUBJECT_VERSION', subject_offering_id)
    try:
        result = VersionedQuestionBankService(db).delete_subject_offering(subject_offering_id)
        log_audit(db, action='question_bank.subject_offering.delete', status='success', message=result.get('message', 'Đã xóa phiên bản môn'), user=user, target_type='subject_offering', target_id=subject_offering_id)
        return result
    except Exception as exc:
        log_audit(db, action='question_bank.subject_offering.delete', status='failed', error_type=AuditErrorType.VALIDATION_ERROR, message=str(exc), user=user, target_type='subject_offering', target_id=subject_offering_id)
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get('/chapters', response_model=PaginatedOut[ChapterOut])
def list_chapters(subject_id: str | None = None, subject_offering_id: str | None = None, page: int = Query(1, ge=1), page_size: int = Query(50, ge=1, le=100), db: Session = Depends(get_db), user: UserContext = Depends(require_permission('view_questions'))):
    query = db.query(SubjectChapter)
    subject_ids = _biz(db).accessible_subject_ids(user)
    if subject_ids is not None:
        if not subject_ids:
            return _empty_page(page, page_size, max_page_size=100)
        query = query.filter(SubjectChapter.subject_id.in_(subject_ids))
    if subject_id:
        _require_business(db, user, 'bank.view', 'SUBJECT', subject_id)
        query = query.filter(SubjectChapter.subject_id == subject_id)
    if subject_offering_id:
        _require_business(db, user, 'bank.view', 'SUBJECT_VERSION', subject_offering_id)
        query = query.filter(SubjectChapter.subject_offering_id == subject_offering_id)
    return _paginate(query.order_by(SubjectChapter.sort_order.asc(), SubjectChapter.chapter_no.asc(), SubjectChapter.id.asc()), page=page, page_size=page_size, max_page_size=100)


@router.post('/chapters', response_model=ChapterOut)
def create_chapter(payload: ChapterCreate, db: Session = Depends(get_db), user: UserContext = Depends(get_user_context)):
    if payload.subject_offering_id:
        _require_business(db, user, 'subject.update', 'SUBJECT_VERSION', payload.subject_offering_id)
    else:
        _require_business(db, user, 'subject.update', 'SUBJECT', payload.subject_id)
    try:
        item = VersionedQuestionBankService(db).create_chapter(**payload.model_dump())
        log_audit(db, action='question_bank.chapter.create', status='success', message='Tạo chapter/bài học thành công', user=user, target_type='chapter', target_id=item.id)
        return item
    except Exception as exc:
        log_audit(db, action='question_bank.chapter.create', status='failed', error_type=AuditErrorType.VALIDATION_ERROR, message=str(exc), user=user, target_type='chapter')
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.patch('/chapters/{chapter_id}', response_model=ChapterOut)
def update_chapter(chapter_id: str, payload: ChapterUpdate, db: Session = Depends(get_db), user: UserContext = Depends(get_user_context)):
    _require_business(db, user, 'subject.update', 'CHAPTER', chapter_id)
    try:
        item = VersionedQuestionBankService(db).update_chapter(chapter_id, **payload.model_dump(exclude_unset=True))
        log_audit(db, action='question_bank.chapter.update', status='success', message='Sửa bài/chapter thành công', user=user, target_type='chapter', target_id=item.id)
        return item
    except Exception as exc:
        log_audit(db, action='question_bank.chapter.update', status='failed', error_type=AuditErrorType.VALIDATION_ERROR, message=str(exc), user=user, target_type='chapter', target_id=chapter_id)
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.delete('/chapters/{chapter_id}', response_model=EntityDeleteOut)
def delete_chapter(chapter_id: str, db: Session = Depends(get_db), user: UserContext = Depends(get_user_context)):
    _require_business(db, user, 'subject.update', 'CHAPTER', chapter_id)
    try:
        result = VersionedQuestionBankService(db).delete_chapter(chapter_id)
        log_audit(db, action='question_bank.chapter.delete', status='success', message=result.get('message', 'Đã xóa bài/chapter'), user=user, target_type='chapter', target_id=chapter_id)
        return result
    except Exception as exc:
        log_audit(db, action='question_bank.chapter.delete', status='failed', error_type=AuditErrorType.VALIDATION_ERROR, message=str(exc), user=user, target_type='chapter', target_id=chapter_id)
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get('/bank-versions', response_model=PaginatedOut[BankVersionOut])
def list_bank_versions(chapter_id: str | None = None, subject_id: str | None = None, subject_offering_id: str | None = None, page: int = Query(1, ge=1), page_size: int = Query(50, ge=1, le=100), db: Session = Depends(get_db), user: UserContext = Depends(require_permission('view_questions'))):
    query = db.query(QuestionBankVersion)
    subject_ids = _biz(db).accessible_subject_ids(user)
    if subject_ids is not None:
        if not subject_ids:
            return _empty_page(page, page_size, max_page_size=100)
        query = query.filter(QuestionBankVersion.subject_id.in_(subject_ids))
    if chapter_id:
        _require_business(db, user, 'bank.view', 'CHAPTER', chapter_id)
        query = query.filter(QuestionBankVersion.chapter_id == chapter_id)
    if subject_id:
        _require_business(db, user, 'bank.view', 'SUBJECT', subject_id)
        query = query.filter(QuestionBankVersion.subject_id == subject_id)
    if subject_offering_id:
        _require_business(db, user, 'bank.view', 'SUBJECT_VERSION', subject_offering_id)
        query = query.filter(QuestionBankVersion.subject_offering_id == subject_offering_id)
    return _paginate(query.order_by(QuestionBankVersion.created_at.desc(), QuestionBankVersion.id.desc()), page=page, page_size=page_size, max_page_size=100)


@router.post('/bank-versions', response_model=BankVersionOut)
def create_bank_version(payload: BankVersionCreate, db: Session = Depends(get_db), user: UserContext = Depends(require_permission('edit_questions'))):
    _require_business(db, user, 'document.manage', 'CHAPTER', payload.chapter_id)
    try:
        item = VersionedQuestionBankService(db).create_bank_version(**payload.model_dump(), actor=user.user_id)
        log_audit(db, action='question_bank.version.create', status='success', message='Tạo phiên bản ngân hàng câu hỏi thành công', user=user, target_type='bank_version', target_id=item.id)
        return item
    except Exception as exc:
        log_audit(db, action='question_bank.version.create', status='failed', error_type=AuditErrorType.VALIDATION_ERROR, message=str(exc), user=user, target_type='bank_version')
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get('/material-versions', response_model=PaginatedOut[MaterialVersionOut])
def list_material_versions(bank_version_id: str | None = None, page: int = Query(1, ge=1), page_size: int = Query(50, ge=1, le=100), db: Session = Depends(get_db), user: UserContext = Depends(require_permission('view_questions'))):
    query = db.query(LearningMaterialVersion)
    if bank_version_id:
        _require_bank_version(db, user, 'bank.view', bank_version_id)
        query = query.filter(LearningMaterialVersion.bank_version_id == bank_version_id)
    else:
        subject_ids = _biz(db).accessible_subject_ids(user)
        if subject_ids is not None:
            if not subject_ids:
                return _empty_page(page, page_size, max_page_size=100)
            query = query.filter(LearningMaterialVersion.subject_id.in_(subject_ids))
    return _paginate(query.order_by(LearningMaterialVersion.created_at.desc(), LearningMaterialVersion.id.desc()), page=page, page_size=page_size, max_page_size=100)


@router.post('/material-versions', response_model=MaterialVersionOut)
def create_material_version(payload: MaterialVersionCreate, db: Session = Depends(get_db), user: UserContext = Depends(require_permission('edit_questions'))):
    _require_bank_version(db, user, 'document.manage', payload.bank_version_id)
    try:
        item = VersionedQuestionBankService(db).create_material_version(**payload.model_dump(), actor=user.user_id)
        log_audit(db, action='question_bank.material_version.create', status='success', message='Tạo phiên bản tài liệu thành công', user=user, target_type='material_version', target_id=item.id)
        return item
    except Exception as exc:
        log_audit(db, action='question_bank.material_version.create', status='failed', error_type=AuditErrorType.VALIDATION_ERROR, message=str(exc), user=user, target_type='material_version')
        raise HTTPException(status_code=400, detail=str(exc)) from exc






@router.delete('/material-versions/{material_version_id}', response_model=MaterialDeleteOut)
def delete_material_version(material_version_id: str, db: Session = Depends(get_db), user: UserContext = Depends(require_permission('edit_questions'))):
    material = db.get(LearningMaterialVersion, material_version_id)
    if not material:
        raise HTTPException(status_code=404, detail='Không tìm thấy tài liệu')
    _require_bank_version(db, user, 'document.manage', material.bank_version_id)
    try:
        result = VersionedQuestionBankService(db).delete_material_version(material_version_id=material_version_id, actor=user.user_id)
        log_audit(db, action='question_bank.material.delete', status='success', message=result.get('message', ''), user=user, target_type='material_version', target_id=material_version_id, metadata=result)
        return result
    except Exception as exc:
        log_audit(db, action='question_bank.material.delete', status='failed', error_type=AuditErrorType.VALIDATION_ERROR, message=str(exc), user=user, target_type='material_version', target_id=material_version_id)
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post('/bank-versions/{bank_version_id}/materials/upload', response_model=MaterialUploadOut)
async def upload_material_to_bank_version(
    bank_version_id: str,
    file: UploadFile = File(...),
    title: str = Form(default=''),
    change_type: str = Form(default='initial'),
    replace_existing: bool = Form(default=False),
    db: Session = Depends(get_db),
    user: UserContext = Depends(require_permission('edit_questions')),
):
    _require_bank_version(db, user, 'document.manage', bank_version_id)
    try:
        raw = await _read_bank_upload_limited(file)
        result = VersionedQuestionBankService(db).upload_material_bytes(
            bank_version_id=bank_version_id,
            filename=file.filename or 'uploaded-file',
            raw=raw,
            content_type=file.content_type or '',
            title=title,
            change_type=change_type,
            actor=user.user_id,
            replace_existing=replace_existing,
        )
        log_audit(
            db,
            action='question_bank.material.upload',
            status='success',
            message='Upload tài liệu vào Bank Version và tách chunk thành công',
            user=user,
            target_type='bank_version',
            target_id=bank_version_id,
            metadata={
                'chunks_created': result.get('chunks_created'),
                'tokens_indexed': result.get('tokens_indexed'),
                'reused_existing': result.get('reused_existing'),
                'diff_required': result.get('diff_required'),
                'diff_base_bank_version_id': result.get('diff_base_bank_version_id'),
            },
        )
        return result
    except Exception as exc:
        log_audit(db, action='question_bank.material.upload', status='failed', error_type=AuditErrorType.VALIDATION_ERROR, message=str(exc), user=user, target_type='bank_version', target_id=bank_version_id)
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get('/bank-versions/{bank_version_id}/material-chunks', response_model=PaginatedOut[MaterialChunkOut])
def list_bank_material_chunks(bank_version_id: str, material_version_id: str | None = None, page: int = Query(1, ge=1), page_size: int = Query(50, ge=1, le=100), db: Session = Depends(get_db), user: UserContext = Depends(require_permission('view_questions'))):
    _require_bank_version(db, user, 'bank.view', bank_version_id)
    query = db.query(MaterialChunk).filter(MaterialChunk.bank_version_id == bank_version_id)
    if material_version_id:
        query = query.filter(MaterialChunk.material_version_id == material_version_id)
    return _paginate(query.order_by(MaterialChunk.material_version_id.asc(), MaterialChunk.chunk_index.asc(), MaterialChunk.id.asc()), page=page, page_size=page_size, max_page_size=100)


@router.post('/bank-versions/{bank_version_id}/generate/preview', response_model=BankGeneratePreviewOut)
async def preview_generate_questions_from_bank_version(bank_version_id: str, payload: BankGenerateRequest, db: Session = Depends(get_db), user: UserContext = Depends(require_permission('estimate_cost'))):
    _require_bank_version(db, user, 'question.generate', bank_version_id)
    try:
        result = await VersionedQuestionBankService(db).preview_generate_from_bank_version(
            bank_version_id=bank_version_id,
            question_count=payload.question_count,
            target_question_count=payload.target_question_count,
            difficulty_easy=payload.difficulty_easy,
            difficulty_medium=payload.difficulty_medium,
            difficulty_hard=payload.difficulty_hard,
            material_version_ids=payload.material_version_ids,
        )
        log_audit(db, action='question_bank.bank_version.generate.preview', status='success', message='Đã tính chi phí dự kiến trước khi tạo câu hỏi', user=user, target_type='bank_version', target_id=bank_version_id, metadata={'question_count': payload.question_count, 'estimated_cost_usd': result.get('estimated_cost_usd'), 'difficulty_counts': result.get('difficulty_counts')})
        return result
    except Exception as exc:
        log_audit(db, action='question_bank.bank_version.generate.preview', status='failed', error_type=AuditErrorType.VALIDATION_ERROR, message=str(exc), user=user, target_type='bank_version', target_id=bank_version_id)
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post('/bank-versions/{bank_version_id}/generate', response_model=BankGenerateOut)
async def generate_questions_from_bank_version(bank_version_id: str, payload: BankGenerateRequest, db: Session = Depends(get_db), user: UserContext = Depends(require_permission('generate_questions'))):
    _require_bank_version(db, user, 'question.generate', bank_version_id)
    try:
        result = await VersionedQuestionBankService(db).generate_from_bank_version(
            bank_version_id=bank_version_id,
            question_count=payload.question_count,
            target_question_count=payload.target_question_count,
            difficulty_easy=payload.difficulty_easy,
            difficulty_medium=payload.difficulty_medium,
            difficulty_hard=payload.difficulty_hard,
            material_version_ids=payload.material_version_ids,
            provider=payload.provider,
            actor=user.user_id,
            approve_after_generate=payload.approve_after_generate,
        )
        log_audit(
            db,
            action='question_bank.bank_version.generate',
            status='success' if result.get('created_questions') else 'failed',
            error_type=None if result.get('created_questions') else AuditErrorType.EXTERNAL_SERVICE_ERROR,
            message=result.get('message', ''),
            user=user,
            target_type='bank_version',
            target_id=bank_version_id,
            metadata={'requested_questions': payload.question_count, 'created_questions': result.get('created_questions'), 'errors': result.get('errors')},
        )
        return result
    except Exception as exc:
        log_audit(db, action='question_bank.bank_version.generate', status='failed', error_type=AuditErrorType.EXTERNAL_SERVICE_ERROR, message=str(exc), user=user, target_type='bank_version', target_id=bank_version_id)
        raise HTTPException(status_code=502, detail=str(exc)) from exc


def _preview_text(value: str | None, *, limit: int = 500) -> str:
    text = str(value or '').strip()
    if len(text) <= limit:
        return text
    return text[:limit].rstrip() + '…'


def _question_list_item(row) -> dict:
    return {
        'id': row.id,
        'bank_version_id': row.bank_version_id,
        'subject_id': row.subject_id,
        'subject_chapter_id': row.subject_chapter_id,
        'difficulty': row.difficulty,
        'status': row.status,
        'question_text_preview': _preview_text(row.question_text_preview, limit=500),
        'option_a_preview': _preview_text(row.option_a_preview, limit=240),
        'option_b_preview': _preview_text(row.option_b_preview, limit=240),
        'option_c_preview': _preview_text(row.option_c_preview, limit=240),
        'option_d_preview': _preview_text(row.option_d_preview, limit=240),
        'correct_answer': row.correct_answer,
        'concept_title': row.concept_title,
        'question_family_id': row.question_family_id,
        'variant_no': row.variant_no,
        'quality_score': row.quality_score,
        'draft_error_reason': row.draft_error_reason,
        'is_duplicate': row.is_duplicate,
        'is_retired': row.is_retired,
        'previous_question_id': row.previous_question_id,
        'lineage_root_question_id': row.lineage_root_question_id,
        'question_revision_no': row.question_revision_no,
        'is_carry_over': row.is_carry_over,
        'created_at': row.created_at,
    }


@router.get('/bank-versions/{bank_version_id}/questions', response_model=CursorPaginatedOut[BankQuestionListItemOut])
def list_bank_version_questions(
    bank_version_id: str,
    status_filter: str | None = None,
    difficulty: str | None = None,
    search: str | None = None,
    cursor_created_at: datetime | None = None,
    cursor_id: str | None = None,
    limit: int = Query(50, ge=1, le=100),
    include_total: bool = False,
    db: Session = Depends(get_db),
    user: UserContext = Depends(require_permission('view_questions')),
):
    _require_bank_version(db, user, 'bank.view', bank_version_id)
    safe_limit = max(1, min(int(limit or 50), 100))
    base_filters = [Question.bank_version_id == bank_version_id]
    if status_filter:
        base_filters.append(Question.status == status_filter)
    if difficulty:
        base_filters.append(Question.difficulty == difficulty)
    if search and search.strip():
        pattern = f"%{search.strip()}%"
        base_filters.append(or_(Question.question_text.ilike(pattern), Question.concept_title.ilike(pattern), Question.question_family_id.ilike(pattern)))
    total = int(db.query(func.count(Question.id)).filter(*base_filters).scalar() or 0) if include_total else None
    if cursor_created_at and cursor_created_at.tzinfo is not None:
        cursor_created_at = cursor_created_at.astimezone(timezone.utc).replace(tzinfo=None)
    if cursor_created_at and cursor_id:
        base_filters.append(or_(Question.created_at < cursor_created_at, and_(Question.created_at == cursor_created_at, Question.id < cursor_id)))
    query = db.query(
        Question.id,
        Question.bank_version_id,
        Question.subject_id,
        Question.subject_chapter_id,
        Question.difficulty,
        Question.status,
        func.substr(Question.question_text, 1, 520).label('question_text_preview'),
        func.substr(Question.option_a, 1, 260).label('option_a_preview'),
        func.substr(Question.option_b, 1, 260).label('option_b_preview'),
        func.substr(Question.option_c, 1, 260).label('option_c_preview'),
        func.substr(Question.option_d, 1, 260).label('option_d_preview'),
        Question.correct_answer,
        Question.concept_title,
        Question.question_family_id,
        Question.variant_no,
        Question.quality_score,
        Question.draft_error_reason,
        Question.is_duplicate,
        Question.is_retired,
        Question.previous_question_id,
        Question.lineage_root_question_id,
        Question.question_revision_no,
        Question.is_carry_over,
        Question.created_at,
    ).filter(*base_filters)
    rows = query.order_by(Question.created_at.desc(), Question.id.desc()).limit(safe_limit + 1).all()
    has_next = len(rows) > safe_limit
    page_rows = rows[:safe_limit]
    items = [_question_list_item(row) for row in page_rows]
    next_cursor = None
    if has_next and page_rows:
        last = page_rows[-1]
        next_cursor = {'created_at': last.created_at.isoformat() if last.created_at else None, 'id': last.id}
    return {'items': items, 'limit': safe_limit, 'has_next': has_next, 'next_cursor': next_cursor, 'total': total}


@router.get('/bank-versions/{bank_version_id}/questions/{question_id}', response_model=BankQuestionDetailOut)
def get_bank_version_question_detail(
    bank_version_id: str,
    question_id: str,
    db: Session = Depends(get_db),
    user: UserContext = Depends(require_permission('view_questions')),
):
    _require_bank_version(db, user, 'bank.view', bank_version_id)
    question = db.query(Question).filter(Question.bank_version_id == bank_version_id, Question.id == question_id).first()
    if not question:
        raise HTTPException(status_code=404, detail='Không tìm thấy câu hỏi trong bank version này.')
    return question


@router.post('/bank-versions/{bank_version_id}/diff/preview', response_model=BankVersionDiffPreviewOut)
def preview_bank_version_diff(bank_version_id: str, payload: BankVersionDiffPreviewRequest, db: Session = Depends(get_db), user: UserContext = Depends(require_permission('view_questions'))):
    _require_bank_version(db, user, 'bank.view', bank_version_id)
    try:
        base_id = payload.base_bank_version_id
        if not base_id:
            target = db.get(QuestionBankVersion, bank_version_id)
            if not target or not target.based_on_version_id:
                raise ValueError('Hãy truyền base_bank_version_id hoặc tạo Bank Version mới với based_on_version_id.')
            base_id = target.based_on_version_id
        result = VersionedQuestionBankService(db).preview_bank_version_diff(
            from_bank_version_id=base_id,
            to_bank_version_id=bank_version_id,
            actor=user.user_id,
            persist=payload.persist,
        )
        log_audit(db, action='question_bank.version.diff.preview', status='success', message=result.get('message', ''), user=user, target_type='bank_version', target_id=bank_version_id, metadata={'diff_id': result.get('diff_id'), 'summary': result.get('summary')})
        return result
    except Exception as exc:
        log_audit(db, action='question_bank.version.diff.preview', status='failed', error_type=AuditErrorType.VALIDATION_ERROR, message=str(exc), user=user, target_type='bank_version', target_id=bank_version_id)
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post('/bank-versions/{bank_version_id}/carry-over', response_model=BankCarryOverOut)
def carry_over_bank_questions(bank_version_id: str, payload: BankCarryOverRequest, db: Session = Depends(get_db), user: UserContext = Depends(require_permission('edit_questions'))):
    _require_bank_version(db, user, 'question.edit', bank_version_id)
    _require_bank_version(db, user, 'bank.view', payload.base_bank_version_id)
    try:
        result = VersionedQuestionBankService(db).carry_over_questions(
            from_bank_version_id=payload.base_bank_version_id,
            to_bank_version_id=bank_version_id,
            question_ids=payload.question_ids,
            require_review=payload.require_review,
            actor=user.user_id,
            diff_id=payload.diff_id,
        )
        log_audit(db, action='question_bank.version.carry_over', status='success', message=result.get('message', ''), user=user, target_type='bank_version', target_id=bank_version_id, metadata={'created_count': result.get('created_count'), 'skipped_count': result.get('skipped_count')})
        return result
    except Exception as exc:
        log_audit(db, action='question_bank.version.carry_over', status='failed', error_type=AuditErrorType.VALIDATION_ERROR, message=str(exc), user=user, target_type='bank_version', target_id=bank_version_id)
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post('/bank-versions/{bank_version_id}/questions/retire', response_model=BankRetireQuestionsOut)
def retire_bank_questions(bank_version_id: str, payload: BankRetireQuestionsRequest, db: Session = Depends(get_db), user: UserContext = Depends(require_permission('review_questions'))):
    _require_bank_version(db, user, 'question.reject', bank_version_id)
    try:
        result = VersionedQuestionBankService(db).retire_questions(
            bank_version_id=bank_version_id,
            question_ids=payload.question_ids,
            reason=payload.reason,
            actor=user.user_id,
        )
        log_audit(db, action='question_bank.version.questions.retire', status='success', message=result.get('message', ''), user=user, target_type='bank_version', target_id=bank_version_id, metadata={'retired_count': result.get('retired_count')})
        return result
    except Exception as exc:
        log_audit(db, action='question_bank.version.questions.retire', status='failed', error_type=AuditErrorType.VALIDATION_ERROR, message=str(exc), user=user, target_type='bank_version', target_id=bank_version_id)
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.patch('/bank-versions/{bank_version_id}/questions/{question_id}', response_model=BankVersionQuestionOut)
def update_bank_question(bank_version_id: str, question_id: str, payload: BankQuestionUpdateRequest, db: Session = Depends(get_db), user: UserContext = Depends(require_permission('review_questions'))):
    _require_bank_version(db, user, 'question.edit', bank_version_id)
    try:
        question = VersionedQuestionBankService(db).update_bank_question(
            bank_version_id=bank_version_id,
            question_id=question_id,
            payload=payload,
            actor=user.user_id,
        )
        log_audit(db, action='question_bank.version.question.update', status='success', message='Đã sửa câu hỏi trong ngân hàng đề', user=user, target_type='question', target_id=question_id, metadata={'bank_version_id': bank_version_id, 'new_status': question.status})
        return question
    except Exception as exc:
        log_audit(db, action='question_bank.version.question.update', status='failed', error_type=AuditErrorType.VALIDATION_ERROR, message=str(exc), user=user, target_type='question', target_id=question_id)
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post('/bank-versions/{bank_version_id}/questions/{question_id}/review', response_model=BankQuestionReviewOut)
def review_bank_question(bank_version_id: str, question_id: str, payload: BankQuestionReviewRequest, db: Session = Depends(get_db), user: UserContext = Depends(require_permission('review_questions'))):
    _require_bank_version(db, user, 'question.approve' if payload.action != 'reject' else 'question.reject', bank_version_id)
    try:
        result = VersionedQuestionBankService(db).review_bank_question(
            bank_version_id=bank_version_id,
            question_id=question_id,
            action=payload.action,
            note=payload.note,
            actor=user.user_id,
        )
        log_audit(db, action='question_bank.version.question.review', status='success', message=result.get('message', ''), user=user, target_type='question', target_id=question_id, metadata={'bank_version_id': bank_version_id, 'new_status': result.get('new_status')})
        return result
    except Exception as exc:
        log_audit(db, action='question_bank.version.question.review', status='failed', error_type=AuditErrorType.VALIDATION_ERROR, message=str(exc), user=user, target_type='question', target_id=question_id)
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post('/bank-versions/{bank_version_id}/questions/bulk-review', response_model=BankQuestionBulkReviewOut)
def bulk_review_bank_questions(bank_version_id: str, payload: BankQuestionBulkReviewRequest, db: Session = Depends(get_db), user: UserContext = Depends(require_permission('review_questions'))):
    _require_bank_version(db, user, 'question.approve' if payload.action != 'reject' else 'question.reject', bank_version_id)
    try:
        result = VersionedQuestionBankService(db).bulk_review_bank_questions(
            bank_version_id=bank_version_id,
            action=payload.action,
            question_ids=payload.question_ids,
            approve_all_pending=payload.approve_all_pending,
            note=payload.note,
            actor=user.user_id,
        )
        log_audit(db, action='question_bank.version.question.bulk_review', status='success', message=result.get('message', ''), user=user, target_type='bank_version', target_id=bank_version_id, metadata={'changed_count': result.get('changed_count'), 'action': payload.action})
        return result
    except Exception as exc:
        log_audit(db, action='question_bank.version.question.bulk_review', status='failed', error_type=AuditErrorType.VALIDATION_ERROR, message=str(exc), user=user, target_type='bank_version', target_id=bank_version_id)
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post('/bank-versions/{bank_version_id}/diff/mark-resolved', response_model=BankDocumentDiffResolveOut)
def mark_bank_diff_resolved(bank_version_id: str, payload: BankDocumentDiffResolveRequest, db: Session = Depends(get_db), user: UserContext = Depends(require_permission('review_questions'))):
    _require_bank_version(db, user, 'question.approve', bank_version_id)
    try:
        result = VersionedQuestionBankService(db).mark_document_diff_resolved(bank_version_id=bank_version_id, note=payload.note, actor=user.user_id)
        log_audit(db, action='question_bank.version.diff.mark_resolved', status='success', message=result.get('message', ''), user=user, target_type='bank_version', target_id=bank_version_id)
        return result
    except Exception as exc:
        log_audit(db, action='question_bank.version.diff.mark_resolved', status='failed', error_type=AuditErrorType.VALIDATION_ERROR, message=str(exc), user=user, target_type='bank_version', target_id=bank_version_id)
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get('/bank-versions/{bank_version_id}/release/readiness', response_model=BankReleaseReadinessOut)
def bank_release_readiness(bank_version_id: str, db: Session = Depends(get_db), user: UserContext = Depends(require_permission('view_questions'))):
    _require_bank_version(db, user, 'bank.view', bank_version_id)
    return VersionedQuestionBankService(db).release_readiness(bank_version_id=bank_version_id)


@router.get('/releases', response_model=PaginatedOut[BankReleaseOut])
def list_releases(bank_version_id: str | None = None, chapter_id: str | None = None, page: int = Query(1, ge=1), page_size: int = Query(50, ge=1, le=100), db: Session = Depends(get_db), user: UserContext = Depends(require_permission('view_questions'))):
    query = db.query(QuestionBankRelease)
    subject_ids = _biz(db).accessible_subject_ids(user)
    if subject_ids is not None:
        if not subject_ids:
            return _empty_page(page, page_size, max_page_size=100)
        query = query.filter(QuestionBankRelease.subject_id.in_(subject_ids))
    if bank_version_id:
        _require_bank_version(db, user, 'bank.view', bank_version_id)
        query = query.filter(QuestionBankRelease.bank_version_id == bank_version_id)
    if chapter_id:
        _require_business(db, user, 'bank.view', 'CHAPTER', chapter_id)
        query = query.filter(QuestionBankRelease.chapter_id == chapter_id)
    return _paginate(query.order_by(QuestionBankRelease.created_at.desc(), QuestionBankRelease.id.desc()), page=page, page_size=page_size, max_page_size=100)


@router.post('/releases', response_model=BankReleaseOut)
def create_release(payload: BankReleaseCreate, db: Session = Depends(get_db), user: UserContext = Depends(require_permission('publish_questions'))):
    _require_bank_version(db, user, 'bank.release.create', payload.bank_version_id)
    try:
        item = VersionedQuestionBankService(db).create_release(**payload.model_dump(), actor=user.user_id)
        log_audit(db, action='question_bank.release.create', status='success', message='Tạo Bank Release thành công; 1 release = 1 Open edX Library', user=user, target_type='bank_release', target_id=item.id, metadata={'openedx_library_key': item.openedx_library_key})
        return item
    except Exception as exc:
        log_audit(db, action='question_bank.release.create', status='failed', error_type=AuditErrorType.VALIDATION_ERROR, message=str(exc), user=user, target_type='bank_release')
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.delete('/releases/{release_id}', response_model=EntityDeleteOut)
def cancel_failed_release(release_id: str, db: Session = Depends(get_db), user: UserContext = Depends(require_permission('publish_questions'))):
    _require_release(db, user, 'bank.release.publish', release_id)
    try:
        result = VersionedQuestionBankService(db).cancel_failed_release(release_id=release_id, actor=user.user_id)
        log_audit(db, action='question_bank.release.cancel_failed', status='success', message=result.get('message', ''), user=user, target_type='bank_release', target_id=release_id, metadata=result)
        return result
    except Exception as exc:
        log_audit(db, action='question_bank.release.cancel_failed', status='failed', error_type=AuditErrorType.VALIDATION_ERROR, message=str(exc), user=user, target_type='bank_release', target_id=release_id)
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post('/releases/{release_id}/publish-openedx', response_model=BankReleasePublishOut)
async def publish_release_to_openedx(release_id: str, payload: BankReleasePublishRequest, db: Session = Depends(get_db), user: UserContext = Depends(require_permission('publish_questions'))):
    _require_release(db, user, 'bank.release.publish', release_id)
    try:
        result = await VersionedQuestionBankService(db).publish_release_to_openedx(
            release_id=release_id,
            actor=user.user_id,
            course_id_for_org=payload.openedx_course_id_for_org,
            force_reimport=payload.force_reimport,
        )
        log_audit(db, action='question_bank.release.publish_openedx', status='success', message='Publish Bank Release sang Open edX Library thành công', user=user, target_type='bank_release', target_id=release_id, metadata={'openedx_library_key': result.get('openedx_library_key'), 'question_count': result.get('question_count')})
        return result
    except Exception as exc:
        log_audit(db, action='question_bank.release.publish_openedx', status='failed', error_type=AuditErrorType.EXTERNAL_SERVICE_ERROR, message=str(exc), user=user, target_type='bank_release', target_id=release_id)
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@router.post('/releases/{release_id}/quiz/preview', response_model=BankReleaseQuizPlanOut)
def preview_quiz_from_release(release_id: str, payload: BankReleaseQuizPreviewRequest, db: Session = Depends(get_db), user: UserContext = Depends(require_permission('publish_questions'))):
    _require_release(db, user, 'quiz.preview', release_id)
    try:
        result = VersionedQuestionBankService(db).preview_quiz_from_release(
            bank_release_id=release_id,
            total_questions=payload.total_questions,
            difficulty_easy=payload.difficulty_easy,
            difficulty_medium=payload.difficulty_medium,
            difficulty_hard=payload.difficulty_hard,
            max_families_per_bank=payload.max_families_per_bank,
        )
        log_audit(db, action='question_bank.release.quiz.preview', status='success', message=result.get('message', ''), user=user, target_type='bank_release', target_id=release_id, metadata={'slot_count': result.get('total_questions'), 'warnings': result.get('warnings')})
        return result
    except Exception as exc:
        log_audit(db, action='question_bank.release.quiz.preview', status='failed', error_type=AuditErrorType.VALIDATION_ERROR, message=str(exc), user=user, target_type='bank_release', target_id=release_id)
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post('/releases/{release_id}/quiz/create', response_model=BankReleaseQuizCreateOut)
async def create_quiz_from_release(release_id: str, payload: BankReleaseQuizCreateRequest, db: Session = Depends(get_db), user: UserContext = Depends(require_permission('publish_questions'))):
    _require_release(db, user, 'quiz.create_openedx', release_id)
    try:
        result = await VersionedQuestionBankService(db).create_quiz_from_release(
            course_chapter_mapping_id=payload.course_chapter_mapping_id,
            quiz_title=payload.quiz_title,
            unit_title=payload.unit_title,
            total_questions=payload.total_questions,
            difficulty_easy=payload.difficulty_easy,
            difficulty_medium=payload.difficulty_medium,
            difficulty_hard=payload.difficulty_hard,
            max_families_per_bank=payload.max_families_per_bank,
            custom_timer_enabled=payload.custom_timer_enabled,
            time_limit_minutes=payload.time_limit_minutes,
            retake_cooldown_minutes=payload.retake_cooldown_minutes,
            auto_submit_on_timeout=payload.auto_submit_on_timeout,
            lock_after_timeout=payload.lock_after_timeout,
            native_timed_exam=payload.native_timed_exam,
            actor=user.user_id,
            expected_bank_release_id=release_id,
        )
        log_audit(db, action='question_bank.release.quiz.create', status='success', message='Tạo Quiz từ Bank Release thành công', user=user, course_id=result.get('openedx_course_id'), target_type='course_quiz_instance', target_id=result.get('course_quiz_instance_id'), metadata={'bank_release_id': release_id, 'openedx_unit_node_id': result.get('openedx_unit_node_id')})
        return result
    except ValueError as exc:
        log_audit(db, action='question_bank.release.quiz.create', status='failed', error_type=AuditErrorType.VALIDATION_ERROR, message=str(exc), user=user, target_type='bank_release', target_id=release_id)
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        log_audit(db, action='question_bank.release.quiz.create', status='failed', error_type=AuditErrorType.EXTERNAL_SERVICE_ERROR, message=str(exc), user=user, target_type='bank_release', target_id=release_id)
        raise HTTPException(status_code=502, detail=str(exc)) from exc




@router.post('/quiz/auto-map/preview', response_model=QuizAutoMapOut)
async def preview_quiz_auto_map(payload: QuizAutoMapRequest, db: Session = Depends(get_db), user: UserContext = Depends(require_permission('publish_questions'))):
    if payload.selected_subject_offering_id:
        _require_business(db, user, 'quiz.preview', 'SUBJECT_VERSION', payload.selected_subject_offering_id)
    try:
        result = await VersionedQuestionBankService(db).preview_quiz_auto_map(openedx_course_id=payload.openedx_course_id, selected_subject_offering_id=payload.selected_subject_offering_id)
        log_audit(db, action='question_bank.quiz.auto_map.preview', status='success' if result.get('ok') else 'failed', error_type=None if result.get('ok') else AuditErrorType.VALIDATION_ERROR, message=result.get('message', ''), user=user, course_id=payload.openedx_course_id, target_type='quiz_auto_map', metadata={'summary': result.get('summary'), 'blocking_errors': result.get('blocking_errors')})
        return result
    except Exception as exc:
        log_audit(db, action='question_bank.quiz.auto_map.preview', status='failed', error_type=AuditErrorType.EXTERNAL_SERVICE_ERROR, message=str(exc), user=user, course_id=payload.openedx_course_id, target_type='quiz_auto_map')
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@router.post('/quiz/auto-map/apply', response_model=QuizAutoMapOut)
async def apply_quiz_auto_map(payload: QuizAutoMapRequest, db: Session = Depends(get_db), user: UserContext = Depends(require_permission('publish_questions'))):
    if payload.selected_subject_offering_id:
        _require_business(db, user, 'quiz.create_openedx', 'SUBJECT_VERSION', payload.selected_subject_offering_id)
    try:
        result = await VersionedQuestionBankService(db).apply_quiz_auto_map(openedx_course_id=payload.openedx_course_id, selected_subject_offering_id=payload.selected_subject_offering_id, actor=user.user_id)
        log_audit(db, action='question_bank.quiz.auto_map.apply', status='success', message=result.get('message', ''), user=user, course_id=payload.openedx_course_id, target_type='quiz_auto_map', metadata={'summary': result.get('summary'), 'mapping_count': len(result.get('mappings') or [])})
        return result
    except ValueError as exc:
        log_audit(db, action='question_bank.quiz.auto_map.apply', status='failed', error_type=AuditErrorType.VALIDATION_ERROR, message=str(exc), user=user, course_id=payload.openedx_course_id, target_type='quiz_auto_map')
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        log_audit(db, action='question_bank.quiz.auto_map.apply', status='failed', error_type=AuditErrorType.EXTERNAL_SERVICE_ERROR, message=str(exc), user=user, course_id=payload.openedx_course_id, target_type='quiz_auto_map')
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@router.get('/course-mappings', response_model=PaginatedOut[CourseMappingOut])
def list_course_mappings(subject_id: str | None = None, page: int = Query(1, ge=1), page_size: int = Query(50, ge=1, le=100), db: Session = Depends(get_db), user: UserContext = Depends(require_permission('view_questions'))):
    query = db.query(EdxCourseMapping)
    subject_ids = _biz(db).accessible_subject_ids(user)
    if subject_ids is not None:
        if not subject_ids:
            return _empty_page(page, page_size, max_page_size=100)
        query = query.filter(EdxCourseMapping.subject_id.in_(subject_ids))
    if subject_id:
        _require_business(db, user, 'bank.view', 'SUBJECT', subject_id)
        query = query.filter(EdxCourseMapping.subject_id == subject_id)
    return _paginate(query.order_by(EdxCourseMapping.created_at.desc(), EdxCourseMapping.id.desc()), page=page, page_size=page_size, max_page_size=100)


@router.post('/course-mappings/validate', response_model=MappingValidationOut)
def validate_course_mapping(payload: CourseMappingValidateRequest, db: Session = Depends(get_db), user: UserContext = Depends(require_permission('publish_questions'))):
    _require_business(db, user, 'quiz.preview', 'SUBJECT', payload.subject_id)
    result = VersionedQuestionBankService(db).validate_course_mapping(**payload.model_dump())
    log_audit(db, action='question_bank.course_mapping.validate', status='success' if result.get('ok') else 'failed', error_type=None if result.get('ok') else AuditErrorType.VALIDATION_ERROR, message=result.get('message', ''), user=user, course_id=payload.openedx_course_id, target_type='course_mapping', metadata=result)
    return result


@router.post('/course-mappings', response_model=CourseMappingOut)
def create_course_mapping(payload: CourseMappingCreate, db: Session = Depends(get_db), user: UserContext = Depends(require_permission('publish_questions'))):
    _require_business(db, user, 'quiz.create_openedx', 'SUBJECT', payload.subject_id)
    try:
        item = VersionedQuestionBankService(db).create_course_mapping(**payload.model_dump(), actor=user.user_id)
        log_audit(db, action='question_bank.course_mapping.create', status='success', message='Map khóa học Open edX vào môn học thành công', user=user, course_id=item.openedx_course_id, target_type='course_mapping', target_id=item.id)
        return item
    except Exception as exc:
        log_audit(db, action='question_bank.course_mapping.create', status='failed', error_type=AuditErrorType.VALIDATION_ERROR, message=str(exc), user=user, target_type='course_mapping')
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get('/course-chapter-mappings', response_model=PaginatedOut[CourseChapterMappingOut])
def list_course_chapter_mappings(course_mapping_id: str | None = None, page: int = Query(1, ge=1), page_size: int = Query(50, ge=1, le=100), db: Session = Depends(get_db), user: UserContext = Depends(require_permission('view_questions'))):
    query = db.query(EdxCourseChapterMapping)
    if course_mapping_id:
        mapping = db.get(EdxCourseMapping, course_mapping_id)
        if not mapping:
            return _empty_page(page, page_size, max_page_size=100)
        _require_business(db, user, 'bank.view', 'SUBJECT', mapping.subject_id)
        query = query.filter(EdxCourseChapterMapping.course_mapping_id == course_mapping_id)
    else:
        subject_ids = _biz(db).accessible_subject_ids(user)
        if subject_ids is not None:
            if not subject_ids:
                return _empty_page(page, page_size, max_page_size=100)
            query = query.join(EdxCourseMapping, EdxCourseMapping.id == EdxCourseChapterMapping.course_mapping_id).filter(EdxCourseMapping.subject_id.in_(subject_ids))
    return _paginate(query.order_by(EdxCourseChapterMapping.created_at.desc(), EdxCourseChapterMapping.id.desc()), page=page, page_size=page_size, max_page_size=100)


@router.post('/course-chapter-mappings/validate', response_model=MappingValidationOut)
def validate_course_chapter_mapping(payload: CourseChapterMappingValidateRequest, db: Session = Depends(get_db), user: UserContext = Depends(require_permission('publish_questions'))):
    _require_release(db, user, 'quiz.preview', payload.bank_release_id)
    result = VersionedQuestionBankService(db).validate_course_chapter_mapping(**payload.model_dump())
    log_audit(db, action='question_bank.course_chapter_mapping.validate', status='success' if result.get('ok') else 'failed', error_type=None if result.get('ok') else AuditErrorType.VALIDATION_ERROR, message=result.get('message', ''), user=user, target_type='course_chapter_mapping', metadata=result)
    return result


@router.post('/course-chapter-mappings', response_model=CourseChapterMappingOut)
def create_course_chapter_mapping(payload: CourseChapterMappingCreate, db: Session = Depends(get_db), user: UserContext = Depends(require_permission('publish_questions'))):
    if payload.bank_release_id:
        _require_release(db, user, 'quiz.create_openedx', payload.bank_release_id)
    else:
        _require_business(db, user, 'quiz.create_openedx', 'CHAPTER', payload.subject_chapter_id)
    try:
        item = VersionedQuestionBankService(db).create_course_chapter_mapping(**payload.model_dump())
        log_audit(db, action='question_bank.course_chapter_mapping.create', status='success', message='Map chapter Open edX vào Bank Release thành công', user=user, target_type='course_chapter_mapping', target_id=item.id)
        return item
    except Exception as exc:
        log_audit(db, action='question_bank.course_chapter_mapping.create', status='failed', error_type=AuditErrorType.VALIDATION_ERROR, message=str(exc), user=user, target_type='course_chapter_mapping')
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get('/course-quiz-instances', response_model=PaginatedOut[CourseQuizInstanceOut])
def list_course_quiz_instances(openedx_course_id: str | None = None, bank_release_id: str | None = None, page: int = Query(1, ge=1), page_size: int = Query(50, ge=1, le=100), limit: int | None = None, db: Session = Depends(get_db), user: UserContext = Depends(require_permission('view_questions'))):
    # limit is kept for frontend/backward query compatibility; page_size is the real contract.
    if limit is not None:
        page_size = limit
    query = db.query(CourseQuizInstance)
    subject_ids = _biz(db).accessible_subject_ids(user)
    if subject_ids is not None:
        if not subject_ids:
            return _empty_page(page, page_size, max_page_size=100)
        query = query.filter(CourseQuizInstance.subject_id.in_(subject_ids))
    if openedx_course_id:
        query = query.filter(CourseQuizInstance.openedx_course_id == openedx_course_id)
    if bank_release_id:
        _require_release(db, user, 'bank.view', bank_release_id)
        query = query.filter(CourseQuizInstance.bank_release_id == bank_release_id)
    return _paginate(query.order_by(CourseQuizInstance.created_at.desc(), CourseQuizInstance.id.desc()), page=page, page_size=page_size, max_page_size=100)


@router.post('/course-quiz-instances/{instance_id}/rollback', response_model=CourseQuizRollbackOut)
async def rollback_course_quiz_instance(instance_id: str, payload: CourseQuizRollbackRequest, db: Session = Depends(get_db), user: UserContext = Depends(require_permission('publish_questions'))):
    quiz_instance = db.get(CourseQuizInstance, instance_id)
    if not quiz_instance:
        raise HTTPException(status_code=404, detail='Không tìm thấy CourseQuizInstance')
    _require_release(db, user, 'quiz.create_openedx', quiz_instance.bank_release_id)
    try:
        result = await VersionedQuestionBankService(db).rollback_course_quiz_instance(instance_id=instance_id, mode=payload.mode, note=payload.note, actor=user.user_id)
        log_audit(db, action='question_bank.course_quiz.rollback', status='success', message=result.get('message', ''), user=user, target_type='course_quiz_instance', target_id=instance_id, metadata=result)
        return result
    except Exception as exc:
        log_audit(db, action='question_bank.course_quiz.rollback', status='failed', error_type=AuditErrorType.EXTERNAL_SERVICE_ERROR, message=str(exc), user=user, target_type='course_quiz_instance', target_id=instance_id)
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get('/quiz-blueprints', response_model=PaginatedOut[QuizBlueprintOut])
def list_quiz_blueprints(chapter_id: str | None = None, page: int = Query(1, ge=1), page_size: int = Query(50, ge=1, le=100), db: Session = Depends(get_db), user: UserContext = Depends(require_permission('view_questions'))):
    query = db.query(QuizBlueprint)
    subject_ids = _biz(db).accessible_subject_ids(user)
    if subject_ids is not None:
        if not subject_ids:
            return _empty_page(page, page_size, max_page_size=100)
        query = query.filter(QuizBlueprint.subject_id.in_(subject_ids))
    if chapter_id:
        _require_business(db, user, 'bank.view', 'CHAPTER', chapter_id)
        query = query.filter(QuizBlueprint.chapter_id == chapter_id)
    return _paginate(query.order_by(QuizBlueprint.created_at.desc(), QuizBlueprint.id.desc()), page=page, page_size=page_size, max_page_size=100)


@router.post('/quiz-blueprints', response_model=QuizBlueprintOut)
def create_quiz_blueprint(payload: QuizBlueprintCreate, db: Session = Depends(get_db), user: UserContext = Depends(require_permission('publish_questions'))):
    _require_business(db, user, 'quiz.create_openedx', 'CHAPTER', payload.chapter_id)
    try:
        item = VersionedQuestionBankService(db).create_quiz_blueprint(**payload.model_dump())
        log_audit(db, action='question_bank.quiz_blueprint.create', status='success', message='Tạo blueprint quiz thành công', user=user, target_type='quiz_blueprint', target_id=item.id)
        return item
    except Exception as exc:
        log_audit(db, action='question_bank.quiz_blueprint.create', status='failed', error_type=AuditErrorType.VALIDATION_ERROR, message=str(exc), user=user, target_type='quiz_blueprint')
        raise HTTPException(status_code=400, detail=str(exc)) from exc
