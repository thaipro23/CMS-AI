from datetime import datetime, timezone, timedelta
from math import ceil
from pathlib import Path
import uuid


from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, status
from fastapi.responses import Response
from sqlalchemy import and_, case, func, or_
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.errors import public_http_exception
from app.core.openedx_ids import openedx_course_id_candidates
from app.core.rbac import UserContext, get_user_context, require_permission
from app.core.config import settings
from app.db.session import get_db
from app.models.question import Question, QuestionMedia
from app.models.question_bank import (
    Department,
    EdxCourseChapterMapping,
    EdxCourseMapping,
    LearningMaterialVersion,
    MaterialChunk,
    QuestionBankRelease,
    BankReleaseQuestion,
    QuestionBankVersion,
    QuizBlueprint,
    CourseQuizInstance,
    Subject,
    SubjectOffering,
    SubjectChapter,
    BankOperationJob,
    BankChapterStats,
)
from app.schemas.question_bank import (
    BankReleaseCreate,
    BankReleaseOut,
    BankReleasePreviewOut,
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
    BankVersionDiffCreateRequest,
    BankVersionDiffPreviewRequest,
    BankVersionDiffPreviewOut,
    BankCarryOverRequest,
    BankCarryOverOut,
    BankRetireQuestionsRequest,
    BankRetireQuestionsOut,
    BankQuestionReviewRequest,
    BankQuestionCreateRequest,
    BankQuestionUpdateRequest,
    BankQuestionMediaOut,
    BankQuestionMediaAltUpdateRequest,
    BankQuestionMediaDeleteOut,
    BankQuestionReviewOut,
    BankQuestionBulkReviewRequest,
    BankQuestionBulkReviewOut,
    BankQuestionImportConfirmRequest,
    BankQuestionImportPreviewOut,
    LegacyQuizCmsOldImportConfirmRequest,
    LegacyQuizCmsOldImportPreviewOut,
    BankOpenEdxImportRequest,
    BankOpenEdxImportPreviewOut,
    BankOpenEdxImportOut,
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
    BankOperationJobOut,
    BankOperationJobQueuedOut,
)
from app.services.audit_log import AuditErrorType, log_audit
from app.services.question_bank_service import VersionedQuestionBankService
from app.services.question_bank.helpers import safe_upload_filename
from app.services.question_bank.import_export import (
    build_import_error_workbook, build_import_template, export_questions_csv, parse_import_workbook, persist_preview,
    preview_openedx_problem_import, import_openedx_problem_questions,
)
from app.services.question_bank.legacy_quiz_import import (
    LEGACY_PREVIEW_TTL_HOURS,
    MAX_TOTAL_ASSET_BYTES,
    MAX_WORKBOOKS,
    build_legacy_quiz_preview,
    legacy_preview_reference,
    load_legacy_quiz_preview,
    persist_legacy_quiz_preview,
    public_legacy_quiz_preview,
)
from app.services.business_rbac import BusinessRBACService
from app.services.bank_dashboard_stats import BankDashboardStatsService
from app.services.dashboard_analytics import DashboardAnalyticsService
from app.services.bank_cost_analytics import BankCostAnalyticsService
from app.services.bank_search import BankSearchService
from app.services.bank_operation_jobs import BankOperationJobService, serialize_job
from app.services.content_extractor import ContentExtractor
from app.services.object_storage import StorageError, get_object_storage
from app.services.question_media import QuestionMediaService, MAX_QUESTION_IMAGE_BYTES
from app.services.question_content import canonical_question_content, normalize_question_type
from app.worker import (
    bank_generate_questions_task,
    bank_legacy_quiz_import_task,
    bank_material_extract_task,
    bank_question_import_task,
    bank_quiz_create_task,
    bank_release_publish_task,
)

router = APIRouter()


_BANK_UPLOAD_MAX_BYTES = int(settings.max_upload_bytes or 50 * 1024 * 1024)
_BULK_REVIEW_AUDIT_ACTION = 'question_bank.version.question.bulk_review'




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


def _bank_material_upload_extension(filename: str, content_type: str = '') -> str:
    name = (filename or '').lower().split('?', 1)[0].split('#', 1)[0]
    if '.' in name:
        return name.rsplit('.', 1)[-1].strip()
    mime = (content_type or '').lower()
    if 'pdf' in mime:
        return 'pdf'
    if 'wordprocessingml' in mime:
        return 'docx'
    if 'spreadsheetml' in mime:
        return 'xlsx'
    if 'presentationml' in mime or 'powerpoint' in mime:
        return 'pptx'
    if 'csv' in mime:
        return 'csv'
    if 'html' in mime:
        return 'html'
    if 'json' in mime:
        return 'json'
    if 'xml' in mime:
        return 'xml'
    if mime.startswith('text/'):
        return 'txt'
    return ''


def _raise_unsupported_bank_material(filename: str, content_type: str = '') -> None:
    ext = _bank_material_upload_extension(filename, content_type)
    legacy = {'doc', 'xls', 'ppt'}
    supported = {'pdf', 'docx', 'pptx', 'xlsx', 'xlsm', 'csv', 'tsv', 'txt', 'md', 'markdown', 'html', 'htm', 'xml', 'json', 'srt', 'vtt'}
    if ext in legacy:
        raise HTTPException(
            status_code=400,
            detail=f'Định dạng file .{ext} là Office cũ, hệ thống không hỗ trợ tách nội dung ổn định. Vui lòng chuyển sang DOCX/XLSX/PPTX hoặc PDF rồi upload lại.',
        )
    if ext and ext not in supported:
        raise HTTPException(
            status_code=400,
            detail=f'Định dạng file .{ext} chưa được hỗ trợ. Hệ thống hiện hỗ trợ: PDF, DOCX, PPTX, XLSX, CSV/TSV, TXT/MD, HTML, JSON/XML, SRT/VTT.',
        )
    if not ext and not (content_type or '').lower().startswith('text/'):
        raise HTTPException(
            status_code=400,
            detail='Không xác định được định dạng file. Vui lòng upload tài liệu có đuôi file rõ ràng như PDF, DOCX, PPTX, XLSX, CSV hoặc TXT.',
        )


def _preflight_bank_material_upload(*, raw: bytes, filename: str, content_type: str) -> dict:
    """Fail fast if an uploaded material cannot be extracted.

    Teachers must see invalid-file errors in the upload popup, not only later in
    audit logs after the async worker fails. The worker still performs the real
    extract/chunk/index step; this preflight only validates readability and gives
    a user-facing message early.
    """
    _raise_unsupported_bank_material(filename, content_type)
    if not settings.material_upload_preflight_enabled:
        return {'skipped': True, 'reason': 'material_upload_preflight_disabled'}
    try:
        items = ContentExtractor().extract_asset({
            'asset_id': 'bank-material-preflight',
            'filename': filename or 'uploaded-file',
            'display_name': filename or 'uploaded-file',
            'mime_type': content_type or '',
            'bytes': raw,
            'strict': True,
        })
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=f'Không thể đọc tài liệu ngay lúc upload: {exc}') from exc
    except Exception as exc:
        raise public_http_exception(
            status_code=400,
            code='BANK_MATERIAL_PREFLIGHT_FAILED',
            message='Không thể đọc tài liệu ngay lúc upload.',
            logger_name=__name__,
        ) from exc

    total_chars = sum(len(item.content or '') for item in items)
    if not items or total_chars < 30:
        raise HTTPException(
            status_code=400,
            detail=(
                f'File {filename or "upload"} không tách được đủ text ngay lúc upload. '
                'Nếu tài liệu là scan/ảnh, hãy bật OCR cho đúng loại file, tăng giới hạn OCR nếu tài liệu dài, '
                'hoặc upload bản DOCX/PDF có text.'
            ),
        )
    return {
        'skipped': False,
        'page_or_item_count': len(items),
        'extracted_chars': total_chars,
        'source_types': sorted({item.source_type for item in items if item.source_type}),
    }


def _biz(db: Session) -> BusinessRBACService:
    return BusinessRBACService(db)


def _require_business(db: Session, user: UserContext, permission: str, scope_type: str = 'SYSTEM', scope_id: str | None = '*') -> None:
    _biz(db).require_permission(user, permission, scope_type, scope_id)


def _require_bank_version(db: Session, user: UserContext, permission: str, bank_version_id: str) -> None:
    _require_business(db, user, permission, 'BANK_VERSION', bank_version_id)


def _require_release(db: Session, user: UserContext, permission: str, release_id: str) -> None:
    _require_business(db, user, permission, 'RELEASE', release_id)


def _require_visible(db: Session, user: UserContext, scope_type: str, scope_id: str | None = '*') -> None:
    _biz(db).require_visible_scope(user, scope_type, scope_id)



def _job_out(job: BankOperationJob) -> dict:
    return serialize_job(job)


def _enqueue_task(task, job_id: str, *, retry_token: str | None = None) -> dict:
    """Enqueue a Celery task and return broker metadata.

    Older code used ``task.delay`` and did not store the Celery task id. When Redis
    or the worker was misconfigured, the UI could show ``queued`` forever with no
    way to prove whether the task reached the broker. This helper makes enqueue
    observable and uses a unique task id so retrying a stuck bank-operation job is
    safe.
    """
    task_name = getattr(task, 'name', None) or getattr(task, '__name__', 'unknown_task')
    token = retry_token or str(uuid.uuid4())
    celery_task_id = f'{task_name}:{job_id}:{token}'
    if settings.task_always_eager:
        result = task.apply(args=[job_id], task_id=celery_task_id)
    else:
        result = task.apply_async(args=[job_id], task_id=celery_task_id)
    return {
        'task_name': task_name,
        'celery_task_id': getattr(result, 'id', celery_task_id),
        'enqueued_at': datetime.utcnow().isoformat(),
        'retry_token': token,
    }


def _persist_enqueue_metadata(db: Session, job: BankOperationJob, meta: dict, *, label: str | None = None) -> BankOperationJob:
    result_json = dict(job.result_json or {})
    enqueue_history = list(result_json.get('enqueue_history') or [])
    enqueue_history.append(meta)
    result_json['enqueue'] = meta
    result_json['enqueue_history'] = enqueue_history[-10:]
    job.result_json = result_json
    if label:
        job.progress_label = label
    job.updated_at = datetime.utcnow()
    db.add(job)
    db.commit()
    db.refresh(job)
    return job


def _enqueue_bank_job_or_fail(db: Session, job: BankOperationJob, task, *, label: str | None = None) -> BankOperationJob:
    try:
        meta = _enqueue_task(task, job.id)
    except Exception as exc:
        BankOperationJobService(db).fail(
            job,
            error=f'Không đưa job vào hàng đợi Celery/Redis: {exc}',
            result={'enqueue_error': str(exc), 'operation_type': job.operation_type},
        )
        raise HTTPException(status_code=503, detail='Không đưa job vào hàng đợi Celery/Redis. Kiểm tra Redis/worker rồi thử lại.') from exc
    return _persist_enqueue_metadata(db, job, meta, label=label)


def _queued_response(job: BankOperationJob, message: str) -> dict:
    return {'ok': True, 'job': _job_out(job), 'message': message}



def _scoped_dashboard_overview(db: Session, user: UserContext) -> dict:
    biz = _biz(db)
    if biz.is_system_admin(user):
        return VersionedQuestionBankService(db).dashboard_overview()
    chapter_ids = biz.accessible_chapter_ids(user)
    if chapter_ids is None:
        return VersionedQuestionBankService(db).dashboard_overview()
    stats_service = BankDashboardStatsService(db)
    all_stats = stats_service.chapter_stats_map()
    chapter_stats = {cid: data for cid, data in all_stats.items() if cid in chapter_ids}
    offering_stats = stats_service.offering_summary_map(chapter_stats)
    subject_stats = stats_service.subject_summary_map(offering_stats)
    department_stats = stats_service.department_summary_map(subject_stats)
    visible_offerings = biz.accessible_subject_offering_ids(user) or set()
    visible_subjects = biz.accessible_subject_ids(user) or set()
    visible_departments = biz.accessible_department_ids(user) or set()
    offering_stats = {key: value for key, value in offering_stats.items() if key in visible_offerings}
    subject_stats = {key: value for key, value in subject_stats.items() if key in visible_subjects}
    department_stats = {key: value for key, value in department_stats.items() if key in visible_departments}
    chapters_needing_work = [row for row in chapter_stats.values() if int(row.get('unresolved_count') or 0) > 0]
    chapters_ready = [row for row in chapter_stats.values() if row.get('ready_to_release')]
    departments_with_work = len([row for row in department_stats.values() if int(row.get('unresolved_count') or 0) > 0])
    subjects_with_work = len([row for row in subject_stats.values() if int(row.get('unresolved_count') or 0) > 0])
    versions_with_work = len([row for row in offering_stats.values() if int(row.get('unresolved_count') or 0) > 0])
    return {
        'ok': True,
        'summary_source': 'ai_bank_chapter_stats:scope_filtered',
        'cache_ttl_seconds': 0,
        'departments_total': len(department_stats),
        'departments_done': max(0, len(department_stats) - departments_with_work),
        'departments_not_done': departments_with_work,
        'subjects_total': len(subject_stats),
        'subjects_done': max(0, len(subject_stats) - subjects_with_work),
        'subjects_not_done': subjects_with_work,
        'subject_versions_total': len(offering_stats),
        'subject_versions_done': max(0, len(offering_stats) - versions_with_work),
        'subject_versions_not_done': versions_with_work,
        'chapters_total': len(chapter_stats),
        'chapters_needing_review': len(chapters_needing_work),
        'chapters_ready_to_release': len(chapters_ready),
        'total_questions': sum(int(row.get('total_questions') or 0) for row in chapter_stats.values()),
        'approved_count': sum(int(row.get('approved_count') or 0) for row in chapter_stats.values()),
        'pending_review_count': sum(int(row.get('pending_review_count') or 0) for row in chapter_stats.values()),
        'draft_error_count': sum(int(row.get('draft_error_count') or 0) for row in chapter_stats.values()),
        'next_actions': stats_service.build_dashboard_next_actions(chapter_stats),
    }



def _scoped_summary_maps(db: Session, user: UserContext) -> dict[str, dict]:
    biz = _biz(db)
    stats_service = BankDashboardStatsService(db)
    if biz.is_system_admin(user):
        chapter_stats = stats_service.chapter_stats_map()
        offering_stats = stats_service.offering_summary_map(chapter_stats)
        subject_stats = stats_service.subject_summary_map(offering_stats)
        department_stats = stats_service.department_summary_map(subject_stats)
        return {'chapters': chapter_stats, 'offerings': offering_stats, 'subjects': subject_stats, 'departments': department_stats}
    chapter_ids = biz.accessible_chapter_ids(user) or set()
    visible_offerings = biz.accessible_subject_offering_ids(user) or set()
    visible_subjects = biz.accessible_subject_ids(user) or set()
    visible_departments = biz.accessible_department_ids(user) or set()
    all_chapter_stats = stats_service.chapter_stats_map()
    chapter_stats = {cid: data for cid, data in all_chapter_stats.items() if cid in chapter_ids}
    offering_stats = stats_service.offering_summary_map(chapter_stats)
    subject_stats = stats_service.subject_summary_map(offering_stats)
    department_stats = stats_service.department_summary_map(subject_stats)
    return {
        'chapters': {key: value for key, value in chapter_stats.items() if key in chapter_ids},
        'offerings': {key: value for key, value in offering_stats.items() if key in visible_offerings},
        'subjects': {key: value for key, value in subject_stats.items() if key in visible_subjects},
        'departments': {key: value for key, value in department_stats.items() if key in visible_departments},
    }


def _scoped_bank_summary(db: Session, user: UserContext) -> dict:
    biz = _biz(db)
    if biz.is_system_admin(user):
        return VersionedQuestionBankService(db).summary()
    department_ids = biz.accessible_department_ids(user) or set()
    subject_ids = biz.accessible_subject_ids(user) or set()
    offering_ids = biz.accessible_subject_offering_ids(user) or set()
    chapter_ids = biz.accessible_chapter_ids(user) or set()
    bank_query = biz.apply_hierarchy_filter(db.query(QuestionBankVersion), QuestionBankVersion, user)
    release_query = biz.apply_hierarchy_filter(db.query(QuestionBankRelease), QuestionBankRelease, user)
    material_query = biz.apply_hierarchy_filter(db.query(LearningMaterialVersion), LearningMaterialVersion, user)
    chunk_query = biz.apply_hierarchy_filter(db.query(MaterialChunk), MaterialChunk, user)
    if chapter_ids:
        stat_row = db.query(
            func.coalesce(func.sum(BankChapterStats.total_questions), 0),
            func.coalesce(func.sum(BankChapterStats.retired_count), 0),
            func.coalesce(func.sum(BankChapterStats.carry_over_count), 0),
        ).filter(BankChapterStats.chapter_id.in_(chapter_ids)).one()
        bank_questions = int(stat_row[0] or 0)
        retired_questions = int(stat_row[1] or 0)
        carry_over_questions = int(stat_row[2] or 0)
    else:
        bank_questions = 0
        retired_questions = 0
        carry_over_questions = 0
    mapping_query = biz.apply_hierarchy_filter(db.query(EdxCourseMapping), EdxCourseMapping, user)
    quiz_query = biz.apply_hierarchy_filter(db.query(QuizBlueprint), QuizBlueprint, user)
    return {
        'departments': len(department_ids),
        'subjects': len(subject_ids),
        'subject_offerings': len(offering_ids),
        'chapters': len(chapter_ids),
        'bank_versions': bank_query.count(),
        'releases': release_query.count(),
        'published_releases': release_query.filter(QuestionBankRelease.status == 'published').count(),
        'course_mappings': mapping_query.count(),
        'quiz_blueprints': quiz_query.count(),
        'material_versions': material_query.count(),
        'material_chunks': chunk_query.count(),
        'bank_questions': bank_questions,
        'bank_diffs': 0,
        'carry_over_questions': carry_over_questions,
        'retired_questions': retired_questions,
    }


def _create_bank_operation_job(
    db: Session,
    *,
    operation_type: str,
    target_type: str,
    target_id: str | None,
    user: UserContext,
    bank_version_id: str | None = None,
    release_id: str | None = None,
    course_id: str | None = None,
    request_json: dict | None = None,
    progress_total: int = 1,
    progress_label: str = 'Đang chờ xử lý',
) -> BankOperationJob:
    return BankOperationJobService(db).create_job(
        operation_type=operation_type,
        target_type=target_type,
        target_id=target_id,
        requested_by=user.user_id,
        bank_version_id=bank_version_id,
        release_id=release_id,
        course_id=course_id,
        request_json=request_json or {},
        progress_total=progress_total,
        progress_label=progress_label,
        commit=True,
    )



@router.get('/operation-jobs', response_model=PaginatedOut[BankOperationJobOut])
def list_bank_operation_jobs(
    operation_type: str | None = None,
    target_type: str | None = None,
    target_id: str | None = None,
    status_filter: str | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=100),
    db: Session = Depends(get_db),
    user: UserContext = Depends(require_permission('view_jobs')),
):
    query = db.query(BankOperationJob)
    if not _biz(db).is_system_admin(user):
        query = query.filter(BankOperationJob.requested_by == user.user_id)
    if operation_type:
        query = query.filter(BankOperationJob.operation_type == operation_type)
    if target_type:
        query = query.filter(BankOperationJob.target_type == target_type)
    if target_id:
        query = query.filter(BankOperationJob.target_id == target_id)
    if status_filter == 'active':
        query = query.filter(BankOperationJob.status.in_(['queued', 'running']))
    elif status_filter:
        query = query.filter(BankOperationJob.status == status_filter)
    page_data = _paginate(query.order_by(BankOperationJob.created_at.desc(), BankOperationJob.id.desc()), page=page, page_size=page_size, max_page_size=100)
    page_data['items'] = [_job_out(item) for item in page_data['items']]
    return page_data


@router.get('/operation-jobs/{job_id}', response_model=BankOperationJobOut)
def get_bank_operation_job(job_id: str, db: Session = Depends(get_db), user: UserContext = Depends(require_permission('view_jobs'))):
    job = db.get(BankOperationJob, job_id)
    if not job:
        raise HTTPException(status_code=404, detail='Không tìm thấy operation job')
    if not _biz(db).is_system_admin(user) and job.requested_by != user.user_id:
        raise HTTPException(status_code=403, detail='Bạn không có quyền xem job này')
    return _job_out(job)


@router.post('/operation-jobs/{job_id}/cancel', response_model=BankOperationJobOut)
def cancel_bank_operation_job(job_id: str, db: Session = Depends(get_db), user: UserContext = Depends(require_permission('view_jobs'))):
    job = db.get(BankOperationJob, job_id)
    if not job:
        raise HTTPException(status_code=404, detail='Không tìm thấy operation job')
    if not _biz(db).is_system_admin(user) and job.requested_by != user.user_id:
        raise HTTPException(status_code=403, detail='Bạn không có quyền hủy job này')
    return _job_out(BankOperationJobService(db).cancel(job, reason='Người dùng yêu cầu hủy. Nếu worker đã chạy tới bước Open edX thì thao tác có thể vẫn hoàn tất.'))


def _task_for_bank_operation(operation_type: str):
    mapping = {
        'material_extract': bank_material_extract_task,
        'bank_generate': bank_generate_questions_task,
        'release_publish': bank_release_publish_task,
        'quiz_create': bank_quiz_create_task,
        'question_import': bank_question_import_task,
        'legacy_quiz_import': bank_legacy_quiz_import_task,
    }
    return mapping.get(operation_type)


@router.post('/operation-jobs/{job_id}/retry', response_model=BankOperationJobOut)
def retry_bank_operation_job(job_id: str, db: Session = Depends(get_db), user: UserContext = Depends(require_permission('view_jobs'))):
    """Requeue a stuck/failed BankOperationJob.

    This is especially useful for Quiz creation jobs that remain ``queued`` when
    the Celery worker was down or not consuming Redis during deployment. The
    original request_json is reused; no duplicate BankOperationJob row is created.
    """
    job = db.get(BankOperationJob, job_id)
    if not job:
        raise HTTPException(status_code=404, detail='Không tìm thấy operation job')
    if not _biz(db).is_system_admin(user) and job.requested_by != user.user_id:
        raise HTTPException(status_code=403, detail='Bạn không có quyền chạy lại job này')
    if job.status == 'running':
        raise HTTPException(status_code=409, detail='Job đang chạy, không thể retry để tránh chạy trùng trên Open edX.')
    task = _task_for_bank_operation(job.operation_type)
    if task is None:
        raise HTTPException(status_code=400, detail=f'Loại job {job.operation_type} chưa hỗ trợ retry')

    result_json = dict(job.result_json or {})
    retry_count = int(result_json.get('retry_count') or 0) + 1
    result_json['retry_count'] = retry_count
    result_json['last_retry_requested_at'] = datetime.utcnow().isoformat()
    result_json['last_retry_requested_by'] = user.user_id
    job.status = 'queued'
    job.error_message = None
    job.started_at = None
    job.finished_at = None
    job.progress_current = 0
    job.progress_label = 'Đã đưa lại vào hàng đợi xử lý'
    job.result_json = result_json
    job.updated_at = datetime.utcnow()
    db.add(job)
    db.commit()
    db.refresh(job)

    if job.operation_type == 'material_extract' and bool(getattr(settings, 'bank_material_extract_inline_enabled', True)):
        _persist_enqueue_metadata(db, job, {
            'task_name': 'bank_material_extract_task',
            'celery_task_id': None,
            'enqueued_at': datetime.utcnow().isoformat(),
            'retry_token': f'inline-retry-{retry_count}',
            'mode': 'inline_backend',
        }, label='Đang chạy lại tách tài liệu trên backend')
        task.apply(args=[job.id])
        db.expire_all()
        job = db.get(BankOperationJob, job.id) or job
        log_audit(db, action='question_bank.operation_job.retry', status='success', message='Đã chạy lại job tách tài liệu trực tiếp', user=user, target_type='bank_operation_job', target_id=job.id, metadata={'operation_type': job.operation_type, 'retry_count': retry_count, 'mode': 'inline_backend'})
        return _job_out(job)

    job = _enqueue_bank_job_or_fail(db, job, task, label='Đã đưa lại job vào hàng đợi Celery')
    log_audit(db, action='question_bank.operation_job.retry', status='success', message='Đã đưa lại job vào hàng đợi', user=user, target_type='bank_operation_job', target_id=job.id, metadata={'operation_type': job.operation_type, 'retry_count': retry_count, 'enqueue': (job.result_json or {}).get('enqueue')})
    return _job_out(job)


@router.get('/summary', response_model=BankSummaryOut)
def summary(db: Session = Depends(get_db), user: UserContext = Depends(require_permission('view_questions'))):
    return _scoped_bank_summary(db, user)




@router.get('/dashboard/cost-analytics')
def dashboard_cost_analytics(
    date_range: str = Query('30d'),
    from_date: str | None = Query(None),
    to_date: str | None = Query(None),
    q: str = Query(''),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=10, le=100),
    sort_by: str = Query('cost_vnd'),
    sort_dir: str = Query('desc'),
    db: Session = Depends(get_db),
    user: UserContext = Depends(require_permission('view_questions')),
):
    try:
        return BankCostAnalyticsService(db).get_analytics(
            user,
            date_range=date_range,
            from_date=from_date,
            to_date=to_date,
            q=q,
            page=page,
            page_size=page_size,
            sort_by=sort_by,
            sort_dir=sort_dir,
        )
    except ValueError as exc:
        raise public_http_exception(
            status_code=422,
            code='BANK_COST_ANALYTICS_INVALID',
            message='Bộ lọc analytics chi phí không hợp lệ.',
            logger_name=__name__,
        ) from exc


@router.get('/dashboard/analytics')
def dashboard_analytics(
    date_range: str = Query('30d'),
    from_date: str | None = Query(None),
    to_date: str | None = Query(None),
    db: Session = Depends(get_db),
    user: UserContext = Depends(require_permission('view_questions')),
):
    return DashboardAnalyticsService(db).get_analytics(user, date_range=date_range, from_date=from_date, to_date=to_date)


@router.get('/dashboard/alerts')
def dashboard_alerts(
    date_range: str = Query('30d'),
    from_date: str | None = Query(None),
    to_date: str | None = Query(None),
    limit: int = Query(12, ge=1, le=50),
    db: Session = Depends(get_db),
    user: UserContext = Depends(require_permission('view_questions')),
):
    service = DashboardAnalyticsService(db)
    filters = service._filters(date_range, from_date, to_date)
    return {'items': service.get_alerts(user, filters, limit=limit), 'limit': limit}


@router.get('/dashboard/activity-feed')
def dashboard_activity_feed(
    limit: int = Query(10, ge=1, le=30),
    db: Session = Depends(get_db),
    user: UserContext = Depends(require_permission('view_questions')),
):
    return DashboardAnalyticsService(db).get_activity_feed(user, limit=limit)


@router.get('/dashboard/drilldown')
def dashboard_drilldown(
    entity: str = Query('questions'),
    q: str = Query('', min_length=0),
    status_filter: str | None = Query(None, alias='status'),
    difficulty: str | None = Query(None),
    question_type: str | None = Query(None),
    created_from: str | None = Query(None),
    created_to: str | None = Query(None),
    question_id: str | None = Query(None),
    chapter_id: str | None = Query(None),
    subject_id: str | None = Query(None),
    limit: int = Query(500, ge=1, le=500),
    db: Session = Depends(get_db),
    user: UserContext = Depends(require_permission('view_questions')),
):
    if entity and entity != 'questions':
        # Hierarchy drill-down is represented by concrete routes already; only
        # question lists need this scope-safe filtered result endpoint.
        return {'entity': entity, 'filters': {'q': q}, 'limit': limit, 'total': 0, 'items': []}
    return BankSearchService(db).drilldown_questions(
        user=user,
        q=q,
        status=status_filter,
        difficulty=difficulty,
        question_type=question_type,
        created_from=created_from,
        created_to=created_to,
        question_id=question_id,
        chapter_id=chapter_id,
        subject_id=subject_id,
        limit=limit,
    )


@router.get('/dashboard/overview')
def dashboard_overview(db: Session = Depends(get_db), user: UserContext = Depends(require_permission('view_questions'))):
    return _scoped_dashboard_overview(db, user)


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
        log_audit(db, action='question_bank.stats.rebuild', status='failed', error_type=AuditErrorType.VALIDATION_ERROR, message='Không thể hoàn tất thao tác ngân hàng câu hỏi.', user=user, target_type='chapter' if chapter_id else 'bank_dashboard_stats', target_id=chapter_id)
        raise public_http_exception(status_code=400, code='BANK_OPERATION_FAILED', message='Không thể hoàn tất thao tác ngân hàng câu hỏi.', logger_name=__name__) from exc


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
        log_audit(db, action='question_bank.search.rebuild', status='failed', error_type=AuditErrorType.VALIDATION_ERROR, message='Không thể hoàn tất thao tác ngân hàng câu hỏi.', user=user, target_type='bank_search_index', target_id=bank_version_id or chapter_id)
        raise public_http_exception(status_code=400, code='BANK_OPERATION_FAILED', message='Không thể hoàn tất thao tác ngân hàng câu hỏi.', logger_name=__name__) from exc


@router.get('/admin/material-cleanup/health')
def bank_material_cleanup_health(db: Session = Depends(get_db), user: UserContext = Depends(require_permission('manage_settings'))):
    _biz(db).require_system_admin(user)
    return VersionedQuestionBankService(db).bank_material_cleanup_health()


@router.post('/admin/material-cleanup/purge')
def purge_deleted_bank_materials(
    retention_days: int | None = Query(None, description='Số ngày giữ tombstone. 0 = purge ngay các bản đủ điều kiện.'),
    dry_run: bool = Query(True),
    limit: int | None = Query(None, ge=1, le=5000),
    bank_version_id: str | None = Query(None),
    chapter_id: str | None = Query(None),
    db: Session = Depends(get_db),
    user: UserContext = Depends(require_permission('manage_settings')),
):
    _biz(db).require_system_admin(user)
    try:
        result = VersionedQuestionBankService(db).purge_deleted_materials(retention_days=retention_days, dry_run=dry_run, limit=limit, bank_version_id=bank_version_id, chapter_id=chapter_id)
        log_audit(db, action='question_bank.material.cleanup.purge', status='success', message=result.get('message', 'Purge tài liệu đã xóa mềm'), user=user, target_type='bank_material_cleanup', target_id=bank_version_id or chapter_id, metadata={k: v for k, v in result.items() if k not in {'purgable', 'blocked'}})
        return result
    except Exception as exc:
        log_audit(db, action='question_bank.material.cleanup.purge', status='failed', error_type=AuditErrorType.VALIDATION_ERROR, message='Không thể hoàn tất thao tác ngân hàng câu hỏi.', user=user, target_type='bank_material_cleanup', target_id=bank_version_id or chapter_id)
        raise public_http_exception(status_code=400, code='BANK_OPERATION_FAILED', message='Không thể hoàn tất thao tác ngân hàng câu hỏi.', logger_name=__name__) from exc


@router.get('/departments/summary')
def department_summaries(db: Session = Depends(get_db), user: UserContext = Depends(require_permission('view_questions'))):
    if _biz(db).is_system_admin(user):
        return VersionedQuestionBankService(db).department_summaries()
    ids = _biz(db).accessible_department_ids(user) or set()
    if not ids:
        return []
    maps = _scoped_summary_maps(db, user)
    departments = db.query(Department).filter(Department.id.in_(ids)).order_by(Department.code.asc()).all()
    return [{'department': VersionedQuestionBankService(db)._summary_entity(item), 'stats': maps['departments'].get(item.id, {})} for item in departments]


@router.get('/departments/{department_id}/subjects/summary')
def subject_summaries(department_id: str, db: Session = Depends(get_db), user: UserContext = Depends(require_permission('view_questions'))):
    _require_visible(db, user, 'DEPARTMENT', department_id)
    if _biz(db).is_system_admin(user):
        return VersionedQuestionBankService(db).subject_summaries(department_id=department_id)
    ids = _biz(db).accessible_subject_ids(user) or set()
    if not ids:
        return []
    maps = _scoped_summary_maps(db, user)
    subjects = db.query(Subject).filter(Subject.department_id == department_id, Subject.id.in_(ids)).order_by(Subject.code.asc()).all()
    return [{'subject': VersionedQuestionBankService(db)._summary_entity(item), 'stats': maps['subjects'].get(item.id, {})} for item in subjects]


@router.get('/subjects/{subject_id}/versions/summary')
def subject_version_summaries(subject_id: str, db: Session = Depends(get_db), user: UserContext = Depends(require_permission('view_questions'))):
    _require_visible(db, user, 'SUBJECT', subject_id)
    if _biz(db).is_system_admin(user):
        return VersionedQuestionBankService(db).subject_version_summaries(subject_id=subject_id)
    ids = _biz(db).accessible_subject_offering_ids(user) or set()
    if not ids:
        return []
    maps = _scoped_summary_maps(db, user)
    offerings = db.query(SubjectOffering).filter(SubjectOffering.subject_id == subject_id, SubjectOffering.id.in_(ids)).order_by(SubjectOffering.code.asc()).all()
    return [{'subject_version': VersionedQuestionBankService(db)._summary_entity(item), 'stats': maps['offerings'].get(item.id, {})} for item in offerings]


@router.get('/subject-versions/{subject_offering_id}/chapters/summary')
def chapter_summaries(subject_offering_id: str, db: Session = Depends(get_db), user: UserContext = Depends(require_permission('view_questions'))):
    _require_visible(db, user, 'SUBJECT_VERSION', subject_offering_id)
    if _biz(db).is_system_admin(user):
        return VersionedQuestionBankService(db).chapter_summaries(subject_offering_id=subject_offering_id)
    ids = _biz(db).accessible_chapter_ids(user) or set()
    if not ids:
        return []
    maps = _scoped_summary_maps(db, user)
    chapters = db.query(SubjectChapter).filter(SubjectChapter.subject_offering_id == subject_offering_id, SubjectChapter.id.in_(ids)).order_by(SubjectChapter.sort_order.asc(), SubjectChapter.chapter_no.asc()).all()
    return [{'chapter': VersionedQuestionBankService(db)._summary_entity(item), 'stats': maps['chapters'].get(item.id, {})} for item in chapters]


@router.get('/departments', response_model=PaginatedOut[DepartmentOut])
def list_departments(q: str | None = Query(None, max_length=120), page: int = Query(1, ge=1), page_size: int = Query(50, ge=1, le=50), db: Session = Depends(get_db), user: UserContext = Depends(require_permission('view_questions'))):
    query = _biz(db).apply_department_filter(db.query(Department), user)
    if q and q.strip():
        needle = f'%{q.strip()}%'
        query = query.filter(or_(Department.code.ilike(needle), Department.name.ilike(needle)))
    return _paginate(query.order_by(Department.code.asc()), page=page, page_size=page_size, max_page_size=50)


@router.get('/departments/{department_id}', response_model=DepartmentOut)
def get_department(department_id: str, db: Session = Depends(get_db), user: UserContext = Depends(require_permission('view_questions'))):
    _require_visible(db, user, 'DEPARTMENT', department_id)
    item = db.get(Department, department_id)
    if not item:
        raise HTTPException(status_code=404, detail='Không tìm thấy bộ môn')
    return item


@router.post('/departments', response_model=DepartmentOut)
def create_department(payload: DepartmentCreate, db: Session = Depends(get_db), user: UserContext = Depends(require_permission('manage_settings'))):
    _require_business(db, user, 'department.manage_all')
    try:
        item = VersionedQuestionBankService(db).create_department(**payload.model_dump())
        log_audit(db, action='question_bank.department.create', status='success', message='Tạo bộ môn thành công', user=user, target_type='department', target_id=item.id)
        return item
    except Exception as exc:
        log_audit(db, action='question_bank.department.create', status='failed', error_type=AuditErrorType.VALIDATION_ERROR, message='Không thể hoàn tất thao tác ngân hàng câu hỏi.', user=user, target_type='department')
        raise public_http_exception(status_code=400, code='BANK_OPERATION_FAILED', message='Không thể hoàn tất thao tác ngân hàng câu hỏi.', logger_name=__name__) from exc


@router.patch('/departments/{department_id}', response_model=DepartmentOut)
def update_department(department_id: str, payload: DepartmentUpdate, db: Session = Depends(get_db), user: UserContext = Depends(require_permission('manage_department'))):
    _require_business(db, user, 'department.update', 'DEPARTMENT', department_id)
    try:
        item = VersionedQuestionBankService(db).update_department(department_id, **payload.model_dump(exclude_unset=True))
        log_audit(db, action='question_bank.department.update', status='success', message='Sửa bộ môn thành công', user=user, target_type='department', target_id=item.id)
        return item
    except Exception as exc:
        log_audit(db, action='question_bank.department.update', status='failed', error_type=AuditErrorType.VALIDATION_ERROR, message='Không thể hoàn tất thao tác ngân hàng câu hỏi.', user=user, target_type='department', target_id=department_id)
        raise public_http_exception(status_code=400, code='BANK_OPERATION_FAILED', message='Không thể hoàn tất thao tác ngân hàng câu hỏi.', logger_name=__name__) from exc


@router.delete('/departments/{department_id}', response_model=EntityDeleteOut)
def delete_department(department_id: str, db: Session = Depends(get_db), user: UserContext = Depends(require_permission('manage_department'))):
    _require_business(db, user, 'department.update', 'DEPARTMENT', department_id)
    try:
        result = VersionedQuestionBankService(db).delete_department(department_id)
        log_audit(db, action='question_bank.department.delete', status='success', message=result.get('message', 'Đã xóa bộ môn'), user=user, target_type='department', target_id=department_id)
        return result
    except Exception as exc:
        log_audit(db, action='question_bank.department.delete', status='failed', error_type=AuditErrorType.VALIDATION_ERROR, message='Không thể hoàn tất thao tác ngân hàng câu hỏi.', user=user, target_type='department', target_id=department_id)
        raise public_http_exception(status_code=400, code='BANK_OPERATION_FAILED', message='Không thể hoàn tất thao tác ngân hàng câu hỏi.', logger_name=__name__) from exc


@router.get('/subjects', response_model=PaginatedOut[SubjectOut])
def list_subjects(department_id: str | None = None, q: str | None = Query(None, max_length=120), page: int = Query(1, ge=1), page_size: int = Query(50, ge=1, le=100), db: Session = Depends(get_db), user: UserContext = Depends(require_permission('view_questions'))):
    query = _biz(db).apply_subject_filter(db.query(Subject), user)
    if q and q.strip():
        needle = f'%{q.strip()}%'
        query = query.filter(or_(Subject.code.ilike(needle), Subject.name.ilike(needle)))
    if department_id:
        _require_visible(db, user, 'DEPARTMENT', department_id)
        query = query.filter(Subject.department_id == department_id)
    return _paginate(query.order_by(Subject.code.asc()), page=page, page_size=page_size, max_page_size=100)


@router.get('/subjects/{subject_id}', response_model=SubjectOut)
def get_subject(subject_id: str, db: Session = Depends(get_db), user: UserContext = Depends(require_permission('view_questions'))):
    _require_visible(db, user, 'SUBJECT', subject_id)
    item = db.get(Subject, subject_id)
    if not item:
        raise HTTPException(status_code=404, detail='Không tìm thấy môn học')
    return item


@router.post('/subjects', response_model=SubjectOut)
def create_subject(payload: SubjectCreate, db: Session = Depends(get_db), user: UserContext = Depends(get_user_context)):
    _require_business(db, user, 'subject.create', 'DEPARTMENT', payload.department_id)
    try:
        item = VersionedQuestionBankService(db).create_subject(**payload.model_dump())
        log_audit(db, action='question_bank.subject.create', status='success', message='Tạo môn học thành công', user=user, target_type='subject', target_id=item.id)
        return item
    except Exception as exc:
        log_audit(db, action='question_bank.subject.create', status='failed', error_type=AuditErrorType.VALIDATION_ERROR, message='Không thể hoàn tất thao tác ngân hàng câu hỏi.', user=user, target_type='subject')
        raise public_http_exception(status_code=400, code='BANK_OPERATION_FAILED', message='Không thể hoàn tất thao tác ngân hàng câu hỏi.', logger_name=__name__) from exc


@router.patch('/subjects/{subject_id}', response_model=SubjectOut)
def update_subject(subject_id: str, payload: SubjectUpdate, db: Session = Depends(get_db), user: UserContext = Depends(get_user_context)):
    _require_business(db, user, 'subject.update', 'SUBJECT', subject_id)
    try:
        item = VersionedQuestionBankService(db).update_subject(subject_id, **payload.model_dump(exclude_unset=True))
        log_audit(db, action='question_bank.subject.update', status='success', message='Sửa môn thành công', user=user, target_type='subject', target_id=item.id)
        return item
    except Exception as exc:
        log_audit(db, action='question_bank.subject.update', status='failed', error_type=AuditErrorType.VALIDATION_ERROR, message='Không thể hoàn tất thao tác ngân hàng câu hỏi.', user=user, target_type='subject', target_id=subject_id)
        raise public_http_exception(status_code=400, code='BANK_OPERATION_FAILED', message='Không thể hoàn tất thao tác ngân hàng câu hỏi.', logger_name=__name__) from exc


@router.delete('/subjects/{subject_id}', response_model=EntityDeleteOut)
def delete_subject(subject_id: str, db: Session = Depends(get_db), user: UserContext = Depends(get_user_context)):
    _require_business(db, user, 'subject.update', 'SUBJECT', subject_id)
    try:
        result = VersionedQuestionBankService(db).delete_subject(subject_id)
        log_audit(db, action='question_bank.subject.delete', status='success', message=result.get('message', 'Đã xóa môn'), user=user, target_type='subject', target_id=subject_id)
        return result
    except Exception as exc:
        log_audit(db, action='question_bank.subject.delete', status='failed', error_type=AuditErrorType.VALIDATION_ERROR, message='Không thể hoàn tất thao tác ngân hàng câu hỏi.', user=user, target_type='subject', target_id=subject_id)
        raise public_http_exception(status_code=400, code='BANK_OPERATION_FAILED', message='Không thể hoàn tất thao tác ngân hàng câu hỏi.', logger_name=__name__) from exc


@router.get('/subject-offerings', response_model=PaginatedOut[SubjectOfferingOut])
@router.get('/subject-versions', response_model=PaginatedOut[SubjectOfferingOut])
def list_subject_offerings(subject_id: str | None = None, q: str | None = Query(None, max_length=120), page: int = Query(1, ge=1), page_size: int = Query(50, ge=1, le=100), db: Session = Depends(get_db), user: UserContext = Depends(require_permission('view_questions'))):
    query = _biz(db).apply_subject_offering_filter(db.query(SubjectOffering), user)
    if q and q.strip():
        needle = f'%{q.strip()}%'
        query = query.filter(or_(SubjectOffering.code.ilike(needle), SubjectOffering.name.ilike(needle), SubjectOffering.term.ilike(needle), SubjectOffering.version_code.ilike(needle)))
    if subject_id:
        _require_visible(db, user, 'SUBJECT', subject_id)
        query = query.filter(SubjectOffering.subject_id == subject_id)
    return _paginate(query.order_by(SubjectOffering.code.asc()), page=page, page_size=page_size, max_page_size=100)


@router.get('/subject-offerings/{subject_offering_id}', response_model=SubjectOfferingOut)
@router.get('/subject-versions/{subject_offering_id}', response_model=SubjectOfferingOut)
def get_subject_offering(subject_offering_id: str, db: Session = Depends(get_db), user: UserContext = Depends(require_permission('view_questions'))):
    _require_visible(db, user, 'SUBJECT_VERSION', subject_offering_id)
    item = db.get(SubjectOffering, subject_offering_id)
    if not item:
        raise HTTPException(status_code=404, detail='Không tìm thấy phiên bản môn')
    return item


@router.post('/subject-offerings', response_model=SubjectOfferingOut)
@router.post('/subject-versions', response_model=SubjectOfferingOut)
def create_subject_offering(payload: SubjectOfferingCreate, db: Session = Depends(get_db), user: UserContext = Depends(get_user_context)):
    _require_business(db, user, 'subject.update', 'SUBJECT', payload.subject_id)
    try:
        item = VersionedQuestionBankService(db).create_subject_offering(**payload.model_dump(), actor=user.user_id)
        log_audit(db, action='question_bank.subject_offering.create', status='success', message='Tạo phiên bản môn thành công', user=user, target_type='subject_offering', target_id=item.id)
        return item
    except Exception as exc:
        log_audit(db, action='question_bank.subject_offering.create', status='failed', error_type=AuditErrorType.VALIDATION_ERROR, message='Không thể hoàn tất thao tác ngân hàng câu hỏi.', user=user, target_type='subject_offering')
        raise public_http_exception(status_code=400, code='BANK_OPERATION_FAILED', message='Không thể hoàn tất thao tác ngân hàng câu hỏi.', logger_name=__name__) from exc


@router.patch('/subject-offerings/{subject_offering_id}', response_model=SubjectOfferingOut)
@router.patch('/subject-versions/{subject_offering_id}', response_model=SubjectOfferingOut)
def update_subject_offering(subject_offering_id: str, payload: SubjectOfferingUpdate, db: Session = Depends(get_db), user: UserContext = Depends(get_user_context)):
    _require_business(db, user, 'subject.update', 'SUBJECT_VERSION', subject_offering_id)
    try:
        item = VersionedQuestionBankService(db).update_subject_offering(subject_offering_id, **payload.model_dump(exclude_unset=True))
        log_audit(db, action='question_bank.subject_offering.update', status='success', message='Sửa phiên bản môn thành công', user=user, target_type='subject_offering', target_id=item.id)
        return item
    except Exception as exc:
        log_audit(db, action='question_bank.subject_offering.update', status='failed', error_type=AuditErrorType.VALIDATION_ERROR, message='Không thể hoàn tất thao tác ngân hàng câu hỏi.', user=user, target_type='subject_offering', target_id=subject_offering_id)
        raise public_http_exception(status_code=400, code='BANK_OPERATION_FAILED', message='Không thể hoàn tất thao tác ngân hàng câu hỏi.', logger_name=__name__) from exc


@router.delete('/subject-offerings/{subject_offering_id}', response_model=EntityDeleteOut)
@router.delete('/subject-versions/{subject_offering_id}', response_model=EntityDeleteOut)
def delete_subject_offering(subject_offering_id: str, db: Session = Depends(get_db), user: UserContext = Depends(get_user_context)):
    _require_business(db, user, 'subject.update', 'SUBJECT_VERSION', subject_offering_id)
    try:
        result = VersionedQuestionBankService(db).delete_subject_offering(subject_offering_id)
        log_audit(db, action='question_bank.subject_offering.delete', status='success', message=result.get('message', 'Đã xóa phiên bản môn'), user=user, target_type='subject_offering', target_id=subject_offering_id)
        return result
    except Exception as exc:
        log_audit(db, action='question_bank.subject_offering.delete', status='failed', error_type=AuditErrorType.VALIDATION_ERROR, message='Không thể hoàn tất thao tác ngân hàng câu hỏi.', user=user, target_type='subject_offering', target_id=subject_offering_id)
        raise public_http_exception(status_code=400, code='BANK_OPERATION_FAILED', message='Không thể hoàn tất thao tác ngân hàng câu hỏi.', logger_name=__name__) from exc


@router.get('/chapters', response_model=PaginatedOut[ChapterOut])
def list_chapters(subject_id: str | None = None, subject_offering_id: str | None = None, q: str | None = Query(None, max_length=120), page: int = Query(1, ge=1), page_size: int = Query(50, ge=1, le=100), db: Session = Depends(get_db), user: UserContext = Depends(require_permission('view_questions'))):
    query = _biz(db).apply_chapter_filter(db.query(SubjectChapter), user)
    if q and q.strip():
        needle = f'%{q.strip()}%'
        query = query.filter(or_(SubjectChapter.title.ilike(needle), SubjectChapter.description.ilike(needle)))
    if subject_id:
        _require_visible(db, user, 'SUBJECT', subject_id)
        query = query.filter(SubjectChapter.subject_id == subject_id)
    if subject_offering_id:
        _require_visible(db, user, 'SUBJECT_VERSION', subject_offering_id)
        query = query.filter(SubjectChapter.subject_offering_id == subject_offering_id)
    return _paginate(query.order_by(SubjectChapter.sort_order.asc(), SubjectChapter.chapter_no.asc(), SubjectChapter.id.asc()), page=page, page_size=page_size, max_page_size=100)


@router.get('/chapters/{chapter_id}', response_model=ChapterOut)
def get_chapter(chapter_id: str, db: Session = Depends(get_db), user: UserContext = Depends(require_permission('view_questions'))):
    _require_visible(db, user, 'CHAPTER', chapter_id)
    item = db.get(SubjectChapter, chapter_id)
    if not item:
        raise HTTPException(status_code=404, detail='Không tìm thấy bài/chapter')
    return item


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
        log_audit(db, action='question_bank.chapter.create', status='failed', error_type=AuditErrorType.VALIDATION_ERROR, message='Không thể hoàn tất thao tác ngân hàng câu hỏi.', user=user, target_type='chapter')
        raise public_http_exception(status_code=400, code='BANK_OPERATION_FAILED', message='Không thể hoàn tất thao tác ngân hàng câu hỏi.', logger_name=__name__) from exc


@router.patch('/chapters/{chapter_id}', response_model=ChapterOut)
def update_chapter(chapter_id: str, payload: ChapterUpdate, db: Session = Depends(get_db), user: UserContext = Depends(get_user_context)):
    _require_business(db, user, 'subject.update', 'CHAPTER', chapter_id)
    try:
        item = VersionedQuestionBankService(db).update_chapter(chapter_id, **payload.model_dump(exclude_unset=True))
        log_audit(db, action='question_bank.chapter.update', status='success', message='Sửa bài/chapter thành công', user=user, target_type='chapter', target_id=item.id)
        return item
    except Exception as exc:
        log_audit(db, action='question_bank.chapter.update', status='failed', error_type=AuditErrorType.VALIDATION_ERROR, message='Không thể hoàn tất thao tác ngân hàng câu hỏi.', user=user, target_type='chapter', target_id=chapter_id)
        raise public_http_exception(status_code=400, code='BANK_OPERATION_FAILED', message='Không thể hoàn tất thao tác ngân hàng câu hỏi.', logger_name=__name__) from exc


@router.delete('/chapters/{chapter_id}', response_model=EntityDeleteOut)
def delete_chapter(chapter_id: str, db: Session = Depends(get_db), user: UserContext = Depends(get_user_context)):
    _require_business(db, user, 'subject.update', 'CHAPTER', chapter_id)
    try:
        result = VersionedQuestionBankService(db).delete_chapter(chapter_id)
        log_audit(db, action='question_bank.chapter.delete', status='success', message=result.get('message', 'Đã xóa bài/chapter'), user=user, target_type='chapter', target_id=chapter_id)
        return result
    except Exception as exc:
        log_audit(db, action='question_bank.chapter.delete', status='failed', error_type=AuditErrorType.VALIDATION_ERROR, message='Không thể hoàn tất thao tác ngân hàng câu hỏi.', user=user, target_type='chapter', target_id=chapter_id)
        raise public_http_exception(status_code=400, code='BANK_OPERATION_FAILED', message='Không thể hoàn tất thao tác ngân hàng câu hỏi.', logger_name=__name__) from exc


@router.get('/bank-versions', response_model=PaginatedOut[BankVersionOut])
def list_bank_versions(chapter_id: str | None = None, subject_id: str | None = None, subject_offering_id: str | None = None, page: int = Query(1, ge=1), page_size: int = Query(50, ge=1, le=100), db: Session = Depends(get_db), user: UserContext = Depends(require_permission('view_questions'))):
    query = _biz(db).apply_hierarchy_filter(db.query(QuestionBankVersion), QuestionBankVersion, user)
    if chapter_id:
        _require_visible(db, user, 'CHAPTER', chapter_id)
        query = query.filter(QuestionBankVersion.chapter_id == chapter_id)
    if subject_id:
        _require_visible(db, user, 'SUBJECT', subject_id)
        query = query.filter(QuestionBankVersion.subject_id == subject_id)
    if subject_offering_id:
        _require_visible(db, user, 'SUBJECT_VERSION', subject_offering_id)
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
        log_audit(db, action='question_bank.version.create', status='failed', error_type=AuditErrorType.VALIDATION_ERROR, message='Không thể hoàn tất thao tác ngân hàng câu hỏi.', user=user, target_type='bank_version')
        raise public_http_exception(status_code=400, code='BANK_OPERATION_FAILED', message='Không thể hoàn tất thao tác ngân hàng câu hỏi.', logger_name=__name__) from exc


@router.get('/material-versions', response_model=PaginatedOut[MaterialVersionOut])
def list_material_versions(bank_version_id: str | None = None, include_deleted: bool = Query(False), page: int = Query(1, ge=1), page_size: int = Query(50, ge=1, le=100), db: Session = Depends(get_db), user: UserContext = Depends(require_permission('view_questions'))):
    query = _biz(db).apply_hierarchy_filter(db.query(LearningMaterialVersion), LearningMaterialVersion, user)
    if not include_deleted:
        query = query.filter(LearningMaterialVersion.status != 'deleted')
    if bank_version_id:
        _require_bank_version(db, user, 'bank.view', bank_version_id)
        query = query.filter(LearningMaterialVersion.bank_version_id == bank_version_id)
    return _paginate(query.order_by(LearningMaterialVersion.created_at.desc(), LearningMaterialVersion.id.desc()), page=page, page_size=page_size, max_page_size=100)


@router.post('/material-versions', response_model=MaterialVersionOut)
def create_material_version(payload: MaterialVersionCreate, db: Session = Depends(get_db), user: UserContext = Depends(require_permission('edit_questions'))):
    _require_bank_version(db, user, 'document.manage', payload.bank_version_id)
    try:
        item = VersionedQuestionBankService(db).create_material_version(**payload.model_dump(), actor=user.user_id)
        log_audit(db, action='question_bank.material_version.create', status='success', message='Tạo phiên bản tài liệu thành công', user=user, target_type='material_version', target_id=item.id)
        return item
    except Exception as exc:
        log_audit(db, action='question_bank.material_version.create', status='failed', error_type=AuditErrorType.VALIDATION_ERROR, message='Không thể hoàn tất thao tác ngân hàng câu hỏi.', user=user, target_type='material_version')
        raise public_http_exception(status_code=400, code='BANK_OPERATION_FAILED', message='Không thể hoàn tất thao tác ngân hàng câu hỏi.', logger_name=__name__) from exc






@router.delete('/material-versions/{material_version_id}', response_model=MaterialDeleteOut)
def delete_material_version(material_version_id: str, force_hard: bool = Query(False), db: Session = Depends(get_db), user: UserContext = Depends(require_permission('edit_questions'))):
    material = db.get(LearningMaterialVersion, material_version_id)
    if not material:
        raise HTTPException(status_code=404, detail='Không tìm thấy tài liệu')
    _require_bank_version(db, user, 'document.manage', material.bank_version_id)
    try:
        result = VersionedQuestionBankService(db).delete_material_version(material_version_id=material_version_id, actor=user.user_id, force_hard=force_hard)
        log_audit(db, action='question_bank.material.delete', status='success', message=result.get('message', ''), user=user, target_type='material_version', target_id=material_version_id, metadata=result)
        return result
    except Exception as exc:
        log_audit(db, action='question_bank.material.delete', status='failed', error_type=AuditErrorType.VALIDATION_ERROR, message='Không thể hoàn tất thao tác ngân hàng câu hỏi.', user=user, target_type='material_version', target_id=material_version_id)
        raise public_http_exception(status_code=400, code='BANK_OPERATION_FAILED', message='Không thể hoàn tất thao tác ngân hàng câu hỏi.', logger_name=__name__) from exc


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
        log_audit(db, action='question_bank.material.upload', status='failed', error_type=AuditErrorType.VALIDATION_ERROR, message='Không thể hoàn tất thao tác ngân hàng câu hỏi.', user=user, target_type='bank_version', target_id=bank_version_id)
        raise public_http_exception(status_code=400, code='BANK_OPERATION_FAILED', message='Không thể hoàn tất thao tác ngân hàng câu hỏi.', logger_name=__name__) from exc



@router.post('/bank-versions/{bank_version_id}/materials/upload-job', response_model=BankOperationJobQueuedOut)
async def upload_material_to_bank_version_job(
    bank_version_id: str,
    file: UploadFile = File(...),
    title: str = Form(''),
    change_type: str = Form('initial'),
    replace_existing: bool = Form(False),
    db: Session = Depends(get_db),
    user: UserContext = Depends(require_permission('edit_questions')),
):
    _require_bank_version(db, user, 'document.manage', bank_version_id)
    raw = await _read_bank_upload_limited(file)
    preflight = _preflight_bank_material_upload(
        raw=raw,
        filename=file.filename or 'uploaded-file',
        content_type=file.content_type or '',
    )
    safe_name = safe_upload_filename(file.filename or 'uploaded-file')
    pending_name = f'{uuid.uuid4()}-{safe_name}'
    storage = get_object_storage()
    try:
        pending_reference = storage.put_bytes(
            f'question-bank/_pending-operation-files/{pending_name}',
            raw,
            content_type=file.content_type or None,
        )
    except StorageError as exc:
        raise HTTPException(status_code=503, detail='Kho lưu trữ tài liệu tạm thời chưa sẵn sàng. Vui lòng thử lại.') from exc
    request_json = {
        'bank_version_id': bank_version_id,
        'pending_file_ref': pending_reference,
        'filename': file.filename or 'uploaded-file',
        'content_type': file.content_type or '',
        'title': title or file.filename or 'uploaded-file',
        'change_type': change_type or 'initial',
        'replace_existing': bool(replace_existing),
        'file_size': len(raw),
        'preflight': preflight,
    }
    try:
        job = _create_bank_operation_job(
            db,
            operation_type='material_extract',
            target_type='bank_version',
            target_id=bank_version_id,
            user=user,
            bank_version_id=bank_version_id,
            request_json=request_json,
            progress_total=5,
            progress_label='Đã nhận file, đang chờ worker tách nội dung',
        )
    except Exception:
        try:
            storage.delete(pending_reference, missing_ok=True)
        except Exception:
            pass
        raise
    if bool(getattr(settings, 'bank_material_extract_inline_enabled', True)):
        # Restore the pre-async UX for material upload: extraction runs immediately
        # inside the backend process so documents do not sit forever in queued
        # state when the Celery worker is not consuming Redis. The operation job is
        # still recorded and progresses through running/completed/failed for audit.
        _persist_enqueue_metadata(db, job, {
            'task_name': 'bank_material_extract_task',
            'celery_task_id': None,
            'enqueued_at': datetime.utcnow().isoformat(),
            'retry_token': 'inline',
            'mode': 'inline_backend',
        }, label='Đang tách tài liệu trên backend')
        bank_material_extract_task.apply(args=[job.id])
        db.expire_all()
        refreshed = db.get(BankOperationJob, job.id) or job
        status_message = (refreshed.result_json or {}).get('user_message') if isinstance(refreshed.result_json, dict) else None
        if refreshed.status == 'failed':
            status_message = status_message or refreshed.error_message or 'Tách tài liệu thất bại.'
        else:
            status_message = status_message or 'Hệ thống đã ghi nhận tài liệu và đồng bộ danh sách bên dưới.'
        log_audit(db, action='question_bank.material.upload.job', status='success', message='Đã kiểm tra file và tách tài liệu trực tiếp', user=user, target_type='bank_operation_job', target_id=refreshed.id, metadata={'bank_version_id': bank_version_id, 'file_name': file.filename, 'file_size': len(raw), 'preflight': preflight, 'mode': 'inline_backend'})
        return _queued_response(refreshed, status_message)

    job = _enqueue_bank_job_or_fail(db, job, bank_material_extract_task, label='Đã đưa job tách tài liệu vào hàng đợi')
    log_audit(db, action='question_bank.material.upload.job', status='success', message='Đã kiểm tra file và tạo job tách tài liệu', user=user, target_type='bank_operation_job', target_id=job.id, metadata={'bank_version_id': bank_version_id, 'file_name': file.filename, 'file_size': len(raw), 'preflight': preflight, 'mode': 'celery_queue'})
    return _queued_response(job, 'File đọc được. Đã đưa tài liệu vào hàng đợi tách nội dung.')


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
            question_type_single_select=payload.question_type_single_select,
            question_type_multi_select=payload.question_type_multi_select,
            material_version_ids=payload.material_version_ids,
        )
        log_audit(db, action='question_bank.bank_version.generate.preview', status='success', message='Đã tính chi phí dự kiến trước khi tạo câu hỏi', user=user, target_type='bank_version', target_id=bank_version_id, metadata={'question_count': payload.question_count, 'estimated_cost_usd': result.get('estimated_cost_usd'), 'difficulty_counts': result.get('difficulty_counts'), 'question_type_counts': result.get('question_type_counts')})
        return result
    except Exception as exc:
        log_audit(db, action='question_bank.bank_version.generate.preview', status='failed', error_type=AuditErrorType.VALIDATION_ERROR, message='Không thể hoàn tất thao tác ngân hàng câu hỏi.', user=user, target_type='bank_version', target_id=bank_version_id)
        raise public_http_exception(status_code=400, code='BANK_OPERATION_FAILED', message='Không thể hoàn tất thao tác ngân hàng câu hỏi.', logger_name=__name__) from exc



@router.post('/bank-versions/{bank_version_id}/generate-job', response_model=BankOperationJobQueuedOut)
def generate_questions_from_bank_version_job(bank_version_id: str, payload: BankGenerateRequest, db: Session = Depends(get_db), user: UserContext = Depends(require_permission('generate_questions'))):
    _require_bank_version(db, user, 'question.generate', bank_version_id)
    request_json = payload.model_dump()
    request_json['bank_version_id'] = bank_version_id
    job = _create_bank_operation_job(
        db,
        operation_type='bank_generate',
        target_type='bank_version',
        target_id=bank_version_id,
        user=user,
        bank_version_id=bank_version_id,
        request_json=request_json,
        progress_total=max(3, int(payload.question_count or 1) + 2),
        progress_label='Đã đưa yêu cầu tạo câu hỏi vào hàng đợi',
    )
    job = _enqueue_bank_job_or_fail(db, job, bank_generate_questions_task, label='Đã đưa job generate câu hỏi vào hàng đợi')
    log_audit(db, action='question_bank.bank_version.generate.job', status='success', message='Đã tạo job generate câu hỏi', user=user, target_type='bank_operation_job', target_id=job.id, metadata={'bank_version_id': bank_version_id, 'question_count': payload.question_count})
    return _queued_response(job, 'Đã đưa yêu cầu tạo câu hỏi vào hàng đợi.')


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
            question_type_single_select=payload.question_type_single_select,
            question_type_multi_select=payload.question_type_multi_select,
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
        log_audit(db, action='question_bank.bank_version.generate', status='failed', error_type=AuditErrorType.EXTERNAL_SERVICE_ERROR, message='Không thể hoàn tất thao tác ngân hàng câu hỏi.', user=user, target_type='bank_version', target_id=bank_version_id)
        raise public_http_exception(status_code=502, code='BANK_OPERATION_FAILED', message='Không thể hoàn tất thao tác ngân hàng câu hỏi.', logger_name=__name__) from exc


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
        'question_type': normalize_question_type(row.question_type),
        'authoring_mode': row.authoring_mode,
        'question_schema_version': row.question_schema_version,
        'media_count': int(row.media_count or 0),
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




def _bank_question_filters(
    bank_version_id: str,
    *,
    status_filter: str | None = None,
    difficulty: str | None = None,
    search: str | None = None,
):
    filters = [Question.bank_version_id == bank_version_id]
    if status_filter and status_filter not in {'all', 'needs_action'}:
        filters.append(Question.status == status_filter)
    elif status_filter == 'needs_action':
        filters.append(Question.status.in_(['pending_review', 'needs_review', 'draft_error']))
    if difficulty and difficulty != 'all':
        filters.append(Question.difficulty == difficulty)
    if search and search.strip():
        pattern = f"%{search.strip()}%"
        filters.append(or_(Question.question_text.ilike(pattern), Question.concept_title.ilike(pattern), Question.question_family_id.ilike(pattern)))
    return filters


def _bank_question_order(sort: str | None):
    key = (sort or 'needs_review').strip().lower()
    if key == 'difficulty':
        return (Question.difficulty.asc(), Question.created_at.desc(), Question.id.desc())
    if key == 'quality_low':
        return (Question.quality_score.asc(), Question.created_at.desc(), Question.id.desc())
    if key == 'quality_high':
        return (Question.quality_score.desc(), Question.created_at.desc(), Question.id.desc())
    if key == 'oldest':
        return (Question.created_at.asc(), Question.id.asc())
    if key == 'newest':
        return (Question.created_at.desc(), Question.id.desc())
    status_rank = case(
        (Question.status == 'draft_error', 0),
        (Question.status.in_(['pending_review', 'needs_review']), 1),
        (Question.status == 'rejected', 2),
        (Question.status == 'approved', 3),
        (Question.status == 'published', 4),
        else_=5,
    )
    return (status_rank.asc(), Question.quality_score.asc(), Question.created_at.desc(), Question.id.desc())


@router.get('/bank-versions/{bank_version_id}/questions/page', response_model=PaginatedOut[BankQuestionListItemOut])
def page_bank_version_questions(
    bank_version_id: str,
    status_filter: str | None = None,
    difficulty: str | None = None,
    search: str | None = None,
    sort: str = Query('needs_review'),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    user: UserContext = Depends(require_permission('view_questions')),
):
    _require_bank_version(db, user, 'bank.view', bank_version_id)
    filters = _bank_question_filters(bank_version_id, status_filter=status_filter, difficulty=difficulty, search=search)
    query = db.query(
        Question.id,
        Question.bank_version_id,
        Question.subject_id,
        Question.subject_chapter_id,
        Question.difficulty,
        Question.status,
        Question.question_type,
        Question.authoring_mode,
        Question.question_schema_version,
        db.query(func.count(QuestionMedia.id)).filter(QuestionMedia.question_id == Question.id).correlate(Question).scalar_subquery().label('media_count'),
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
    ).filter(*filters).order_by(*_bank_question_order(sort))
    page_data = _paginate(query, page=page, page_size=page_size, max_page_size=100)
    page_data['items'] = [_question_list_item(row) for row in page_data['items']]
    return page_data


@router.get('/bank-versions/{bank_version_id}/questions/export.csv')
def export_bank_version_questions(
    bank_version_id: str,
    status_filter: str | None = None,
    difficulty: str | None = None,
    search: str | None = None,
    question_ids: str | None = None,
    db: Session = Depends(get_db),
    user: UserContext = Depends(require_permission('view_questions')),
):
    _require_bank_version(db, user, 'bank.view', bank_version_id)
    filters = _bank_question_filters(bank_version_id, status_filter=status_filter, difficulty=difficulty, search=search)
    ids = [item.strip() for item in (question_ids or '').split(',') if item.strip()]
    if ids:
        filters.append(Question.id.in_(ids[:5000]))
    rows = db.query(Question).filter(*filters).order_by(Question.created_at.desc(), Question.id.desc()).limit(50000).all()
    raw = export_questions_csv(rows)
    return Response(
        content=raw,
        media_type='text/csv; charset=utf-8',
        headers={'Content-Disposition': f'attachment; filename="bank-questions-{bank_version_id}.csv"'},
    )


def _load_owned_question_import_preview(*, bank_version_id: str, preview_token: str, user: UserContext) -> tuple[str, dict]:
    if not preview_token or len(preview_token) != 32 or any(char not in '0123456789abcdef' for char in preview_token.lower()):
        raise HTTPException(status_code=400, detail='Mã preview import không hợp lệ.')
    storage = get_object_storage()
    preview_reference = storage.reference_for_key(
        f'question-bank/_pending-operation-files/question-import-{preview_token}.json'
    )
    try:
        preview = storage.read_json(preview_reference)
    except StorageError as exc:
        raise HTTPException(status_code=404, detail='Preview import đã hết hạn hoặc không tồn tại. Hãy upload lại file.') from exc
    try:
        created_at = datetime.fromisoformat(str(preview.get('preview_created_at') or '').replace('Z', '+00:00'))
        if created_at.tzinfo is None:
            created_at = created_at.replace(tzinfo=timezone.utc)
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=400, detail={
            'code': 'BANK_IMPORT_PREVIEW_INVALID',
            'message': 'Preview import không hợp lệ. Hãy upload lại file.',
        }) from exc
    if datetime.now(timezone.utc) - created_at.astimezone(timezone.utc) > timedelta(hours=2):
        try:
            storage.delete(preview_reference, missing_ok=True)
        except Exception:
            pass
        raise HTTPException(status_code=410, detail='Preview import đã hết hạn sau 2 giờ. Hãy upload lại file.')
    if str(preview.get('bank_version_id')) != bank_version_id or str(preview.get('requested_by')) != str(user.user_id):
        raise HTTPException(status_code=403, detail='Preview import không thuộc người dùng hiện tại.')
    return preview_reference, preview


def _load_owned_legacy_quiz_preview(
    *,
    preview_token: str,
    user: UserContext,
) -> tuple[str, dict]:
    storage = get_object_storage()
    try:
        preview = load_legacy_quiz_preview(preview_token, storage=storage)
    except ValueError as exc:
        raise HTTPException(
            status_code=404,
            detail='Preview import đã hết hạn hoặc không tồn tại. Hãy tải file lên lại.',
        ) from exc
    try:
        created_at = datetime.fromisoformat(str(preview.get('created_at') or '').replace('Z', '+00:00'))
        if created_at.tzinfo is None:
            created_at = created_at.replace(tzinfo=timezone.utc)
    except (TypeError, ValueError) as exc:
        raise HTTPException(
            status_code=400,
            detail={
                'code': 'LEGACY_QUIZ_PREVIEW_INVALID',
                'message': 'Preview import không hợp lệ. Hãy tải file lên lại.',
            },
        ) from exc
    if datetime.now(timezone.utc) - created_at.astimezone(timezone.utc) > timedelta(
        hours=LEGACY_PREVIEW_TTL_HOURS
    ):
        try:
            storage.delete(legacy_preview_reference(preview_token, storage), missing_ok=True)
        except StorageError:
            pass
        raise HTTPException(
            status_code=410,
            detail=(
                f'Preview import đã hết hạn sau {LEGACY_PREVIEW_TTL_HOURS} giờ. '
                'Hãy tải file lên lại.'
            ),
        )
    if str(preview.get('requested_by') or '') != str(user.user_id or ''):
        raise HTTPException(status_code=403, detail='Preview import không thuộc người dùng hiện tại.')
    return legacy_preview_reference(preview_token, storage), preview


@router.post('/import-quiz-cms-old/preview', response_model=LegacyQuizCmsOldImportPreviewOut)
async def preview_legacy_quiz_cms_old_import(
    workbooks: list[UploadFile] = File(...),
    assets: list[UploadFile] | None = File(None),
    db: Session = Depends(get_db),
    user: UserContext = Depends(require_permission('edit_questions')),
):
    if not workbooks:
        raise HTTPException(status_code=400, detail='Cần chọn ít nhất 1 file Excel.')
    if len(workbooks) > MAX_WORKBOOKS:
        raise HTTPException(status_code=400, detail=f'Mỗi lần import tối đa {MAX_WORKBOOKS} file Excel.')

    workbook_payloads: list[dict] = []
    workbook_total = 0
    for upload in workbooks:
        filename = safe_upload_filename(upload.filename or 'legacy-quiz.xlsx')
        if Path(filename).suffix.lower() != '.xlsx':
            raise HTTPException(status_code=400, detail=f'{filename}: chỉ hỗ trợ file Excel .xlsx.')
        raw = await upload.read(15 * 1024 * 1024 + 1)
        if len(raw) > 15 * 1024 * 1024:
            raise HTTPException(status_code=413, detail=f'{filename}: file Excel vượt giới hạn 15 MB.')
        workbook_total += len(raw)
        if workbook_total > MAX_TOTAL_ASSET_BYTES:
            raise HTTPException(status_code=413, detail='Tổng dung lượng file Excel vượt 100 MB.')
        workbook_payloads.append({'filename': filename, 'raw': raw})

    asset_payloads: list[dict] = []
    asset_total = 0
    for upload in list(assets or []):
        filename = safe_upload_filename(upload.filename or 'asset')
        if Path(filename).suffix.lower() not in {'.png', '.jpg', '.jpeg', '.webp', '.zip'}:
            raise HTTPException(
                status_code=400,
                detail=f'{filename}: chỉ hỗ trợ PNG/JPEG/WebP hoặc ZIP.',
            )
        remaining = MAX_TOTAL_ASSET_BYTES - asset_total
        raw = await upload.read(max(0, remaining) + 1)
        asset_total += len(raw)
        if asset_total > MAX_TOTAL_ASSET_BYTES:
            raise HTTPException(status_code=413, detail='Tổng dung lượng ảnh/ZIP vượt 100 MB.')
        asset_payloads.append({'filename': filename, 'raw': raw})

    try:
        visible_subject_ids = _biz(db).accessible_subject_ids(user)
        preview = build_legacy_quiz_preview(
            db,
            workbooks=workbook_payloads,
            assets=asset_payloads,
            visible_subject_ids=visible_subject_ids,
            actor=user.user_id,
        )
        token, _reference = persist_legacy_quiz_preview(preview)
        preview['preview_token'] = token
        response = public_legacy_quiz_preview(preview)
        log_audit(
            db,
            action='question_bank.legacy_quiz_import.preview',
            status='success',
            message='Đã kiểm tra file quiz CMS cũ',
            user=user,
            target_type='legacy_quiz_import_preview',
            target_id=token,
            metadata={
                'target_term': response['target_term'],
                'workbook_count': response['workbook_count'],
                'sheet_count': response['sheet_count'],
                'question_count': response['question_count'],
                'error_count': len(response['errors']),
                'warning_count': len(response['warnings']),
            },
        )
        return response
    except (ValueError, StorageError) as exc:
        db.rollback()
        raise public_http_exception(
            status_code=400,
            code='LEGACY_QUIZ_IMPORT_PREVIEW_FAILED',
            message=str(exc),
            logger_name=__name__,
        ) from exc


@router.post(
    '/import-quiz-cms-old/jobs',
    response_model=BankOperationJobQueuedOut,
    status_code=status.HTTP_202_ACCEPTED,
)
def enqueue_legacy_quiz_cms_old_import(
    payload: LegacyQuizCmsOldImportConfirmRequest,
    db: Session = Depends(get_db),
    user: UserContext = Depends(require_permission('edit_questions')),
):
    preview_reference, preview = _load_owned_legacy_quiz_preview(
        preview_token=payload.preview_token,
        user=user,
    )
    if not preview.get('can_commit') or preview.get('errors') or int(preview.get('question_count') or 0) <= 0:
        raise HTTPException(
            status_code=400,
            detail='Chỉ có thể import khi preview có câu hỏi và không còn lỗi chặn.',
        )

    existing = (
        db.query(BankOperationJob)
        .filter(
            BankOperationJob.operation_type == 'legacy_quiz_import',
            BankOperationJob.target_type == 'legacy_quiz_import_preview',
            BankOperationJob.target_id == payload.preview_token,
            BankOperationJob.requested_by == user.user_id,
        )
        .order_by(BankOperationJob.created_at.desc())
        .first()
    )
    if existing:
        return _queued_response(existing, 'Tác vụ import cho preview này đã được tạo trước đó.')

    subject_ids = sorted({
        str(workbook.get('subject_id') or '')
        for workbook in preview.get('workbooks') or []
        if workbook.get('subject_id')
    })
    for subject_id in subject_ids:
        _require_business(db, user, 'subject.update', 'SUBJECT', subject_id)
        _require_business(db, user, 'document.manage', 'SUBJECT', subject_id)
        _require_business(db, user, 'question.edit', 'SUBJECT', subject_id)

    job = BankOperationJobService(db).create_job(
        operation_type='legacy_quiz_import',
        target_type='legacy_quiz_import_preview',
        target_id=payload.preview_token,
        requested_by=user.user_id,
        request_json={
            'preview_token': payload.preview_token,
            'preview_reference': preview_reference,
            'target_term': preview.get('target_term'),
            'workbook_count': preview.get('workbook_count'),
            'sheet_count': preview.get('sheet_count'),
            'question_count': preview.get('question_count'),
            'subject_ids': subject_ids,
        },
        progress_total=max(1, int(preview.get('sheet_count') or 1)),
        progress_label='Đang chờ import quiz CMS cũ vào SU26',
    )
    job = _enqueue_bank_job_or_fail(
        db,
        job,
        bank_legacy_quiz_import_task,
        label='Đã đưa import quiz CMS cũ vào hàng đợi',
    )
    log_audit(
        db,
        action='question_bank.legacy_quiz_import.enqueue',
        status='success',
        message='Đã tạo job import quiz CMS cũ vào SU26',
        user=user,
        target_type='bank_operation_job',
        target_id=job.id,
        metadata={
            'preview_token': payload.preview_token,
            'question_count': preview.get('question_count'),
            'subject_ids': subject_ids,
        },
    )
    return _queued_response(
        job,
        'Đã tạo tác vụ nền. Mọi câu hỏi được import sẽ ở trạng thái Chờ duyệt.',
    )


@router.post('/bank-versions/{bank_version_id}/questions/import-openedx/preview', response_model=BankOpenEdxImportPreviewOut)
def preview_bank_openedx_import(bank_version_id: str, payload: BankOpenEdxImportRequest, db: Session = Depends(get_db), user: UserContext = Depends(require_permission('edit_questions'))):
    _require_bank_version(db, user, 'question.edit', bank_version_id)
    try:
        return preview_openedx_problem_import(payload.olx)
    except ValueError as exc:
        raise public_http_exception(
            status_code=400,
            code='BANK_OPENEDX_IMPORT_PREVIEW_FAILED',
            message=str(exc),
            logger_name=__name__,
        ) from exc


@router.post('/bank-versions/{bank_version_id}/questions/import-openedx', response_model=BankOpenEdxImportOut)
def commit_bank_openedx_import(bank_version_id: str, payload: BankOpenEdxImportRequest, db: Session = Depends(get_db), user: UserContext = Depends(require_permission('edit_questions'))):
    _require_bank_version(db, user, 'question.edit', bank_version_id)
    try:
        result=import_openedx_problem_questions(db, bank_version_id=bank_version_id, problem_olx=payload.olx, source_ref=payload.source_ref, actor=user.user_id)
        log_audit(db, action='question_bank.question.import.openedx', status='success', message=result.get('message') or 'Đã import Open edX OLX', user=user, target_type='bank_version', target_id=bank_version_id, metadata={'created_count':result.get('created_count'),'skipped_count':result.get('skipped_count')})
        return result
    except ValueError as exc:
        db.rollback()
        raise public_http_exception(status_code=400, code='BANK_OPENEDX_IMPORT_FAILED', message=str(exc), logger_name=__name__) from exc


@router.get('/bank-versions/{bank_version_id}/questions/import-template.xlsx')
def download_bank_question_import_template(
    bank_version_id: str,
    db: Session = Depends(get_db),
    user: UserContext = Depends(require_permission('view_questions')),
):
    _require_bank_version(db, user, 'bank.view', bank_version_id)
    return Response(
        content=build_import_template(),
        media_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        headers={'Content-Disposition': 'attachment; filename="bank-question-import-template.xlsx"'},
    )


@router.post('/bank-versions/{bank_version_id}/questions/import-preview', response_model=BankQuestionImportPreviewOut)
async def preview_bank_question_import(
    bank_version_id: str,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    user: UserContext = Depends(require_permission('edit_questions')),
):
    _require_bank_version(db, user, 'question.edit', bank_version_id)
    filename = safe_upload_filename(file.filename or 'questions.xlsx')
    if not filename.lower().endswith('.xlsx'):
        raise HTTPException(status_code=400, detail='Chỉ hỗ trợ file .xlsx theo mẫu import câu hỏi.')
    raw = await file.read()
    if len(raw) > min(_BANK_UPLOAD_MAX_BYTES, 10 * 1024 * 1024):
        raise HTTPException(status_code=413, detail='File import vượt giới hạn 10 MB.')
    try:
        parsed = parse_import_workbook(raw, max_rows=2000)
        token, path = persist_preview({**parsed, 'bank_version_id': bank_version_id, 'requested_by': user.user_id, 'filename': filename})
        log_audit(db, action='question_bank.question.import.preview', status='success', message='Đã kiểm tra file import câu hỏi', user=user, target_type='bank_version', target_id=bank_version_id, metadata={'valid_count': parsed['valid_count'], 'error_count': parsed['error_count'], 'filename': filename})
        return {
            'ok': True,
            'preview_token': token,
            'total_rows': parsed['total_rows'],
            'valid_count': parsed['valid_count'],
            'error_count': parsed['error_count'],
            'preview_rows': parsed['rows'][:20],
            'errors': parsed['errors'][:100],
            'can_commit': parsed['valid_count'] > 0 and parsed['error_count'] == 0,
            'message': 'File hợp lệ, có thể xác nhận import.' if parsed['error_count'] == 0 else 'File còn lỗi. Hãy sửa các dòng lỗi rồi upload lại.',
        }
    except ValueError as exc:
        raise public_http_exception(status_code=400, code='BANK_OPERATION_FAILED', message='Không thể hoàn tất thao tác ngân hàng câu hỏi.', logger_name=__name__) from exc


@router.get('/bank-versions/{bank_version_id}/questions/import-errors/{preview_token}.xlsx')
def download_bank_question_import_errors(
    bank_version_id: str,
    preview_token: str,
    db: Session = Depends(get_db),
    user: UserContext = Depends(require_permission('edit_questions')),
):
    _require_bank_version(db, user, 'question.edit', bank_version_id)
    _preview_path, preview = _load_owned_question_import_preview(bank_version_id=bank_version_id, preview_token=preview_token, user=user)
    raw = build_import_error_workbook(preview)
    return Response(
        content=raw,
        media_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        headers={'Content-Disposition': 'attachment; filename="bank-question-import-errors.xlsx"'},
    )


@router.post('/bank-versions/{bank_version_id}/questions/import-job', response_model=BankOperationJobQueuedOut)
def enqueue_bank_question_import(
    bank_version_id: str,
    payload: BankQuestionImportConfirmRequest,
    db: Session = Depends(get_db),
    user: UserContext = Depends(require_permission('edit_questions')),
):
    _require_bank_version(db, user, 'question.edit', bank_version_id)
    preview_path, preview = _load_owned_question_import_preview(
        bank_version_id=bank_version_id,
        preview_token=payload.preview_token,
        user=user,
    )
    if int(preview.get('error_count') or 0) > 0 or int(preview.get('valid_count') or 0) <= 0:
        raise HTTPException(status_code=400, detail='Chỉ có thể import khi file không còn dòng lỗi.')
    job = BankOperationJobService(db).create_job(
        operation_type='question_import',
        target_type='bank_version',
        target_id=bank_version_id,
        requested_by=user.user_id,
        bank_version_id=bank_version_id,
        request_json={'preview_path': str(preview_path), 'preview_token': payload.preview_token, 'valid_count': preview.get('valid_count'), 'filename': preview.get('filename')},
        progress_total=max(2, int(preview.get('valid_count') or 1) + 1),
        progress_label='Đang chờ import câu hỏi',
    )
    job = _enqueue_bank_job_or_fail(db, job, bank_question_import_task, label='Đã đưa import câu hỏi vào hàng đợi')
    log_audit(db, action='question_bank.question.import.enqueue', status='success', message='Đã tạo job import câu hỏi', user=user, target_type='bank_operation_job', target_id=job.id, metadata={'bank_version_id': bank_version_id, 'valid_count': preview.get('valid_count')})
    return _queued_response(job, 'Đã tạo tác vụ nền import câu hỏi. Các câu mới sẽ ở trạng thái Chờ duyệt.')


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
        Question.question_type,
        Question.authoring_mode,
        Question.question_schema_version,
        db.query(func.count(QuestionMedia.id)).filter(QuestionMedia.question_id == Question.id).correlate(Question).scalar_subquery().label('media_count'),
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
    media = QuestionMediaService(db).list_media(bank_version_id, question_id)
    data = BankVersionQuestionOut.model_validate(question).model_dump()
    data['question_type'] = normalize_question_type(question.question_type)
    data['question_content_json'] = canonical_question_content(question)
    data['media'] = [BankQuestionMediaOut.model_validate(item).model_dump() for item in media]
    return data


@router.post('/bank-versions/{bank_version_id}/questions', response_model=BankVersionQuestionOut, status_code=201)
def create_manual_bank_question(bank_version_id: str, payload: BankQuestionCreateRequest, db: Session = Depends(get_db), user: UserContext = Depends(require_permission('edit_questions'))):
    _require_bank_version(db, user, 'question.edit', bank_version_id)
    try:
        question = VersionedQuestionBankService(db).create_manual_bank_question(bank_version_id=bank_version_id, payload=payload, actor=user.user_id)
        data = BankVersionQuestionOut.model_validate(question).model_dump()
        data['question_type'] = normalize_question_type(question.question_type)
        data['question_content_json'] = canonical_question_content(question)
        data['media'] = []
        log_audit(db, action='question_bank.version.question.create_manual', status='success', message='Đã tạo câu hỏi thủ công ở trạng thái Chờ duyệt', user=user, target_type='question', target_id=question.id, metadata={'bank_version_id': bank_version_id, 'question_type': data['question_type']})
        return data
    except ValueError as exc:
        db.rollback()
        raise public_http_exception(status_code=400, code='BANK_QUESTION_INVALID', message=str(exc), logger_name=__name__) from exc


@router.get('/bank-versions/{bank_version_id}/questions/{question_id}/media', response_model=list[BankQuestionMediaOut])
def list_bank_question_media(bank_version_id: str, question_id: str, db: Session = Depends(get_db), user: UserContext = Depends(require_permission('view_questions'))):
    _require_bank_version(db, user, 'bank.view', bank_version_id)
    return QuestionMediaService(db).list_media(bank_version_id, question_id)


@router.post('/bank-versions/{bank_version_id}/questions/{question_id}/media', response_model=BankQuestionMediaOut, status_code=201)
async def upload_bank_question_media(bank_version_id: str, question_id: str, file: UploadFile = File(...), alt_text: str = Form(...), db: Session = Depends(get_db), user: UserContext = Depends(require_permission('edit_questions'))):
    _require_bank_version(db, user, 'question.edit', bank_version_id)
    raw = await file.read(MAX_QUESTION_IMAGE_BYTES + 1)
    try:
        media = QuestionMediaService(db).add_image(bank_version_id=bank_version_id, question_id=question_id, filename=file.filename or 'image', raw=raw, content_type=file.content_type or '', alt_text=alt_text, actor=user.user_id)
        log_audit(db, action='question_bank.version.question.media.add', status='success', message='Đã thêm ảnh vào câu hỏi', user=user, target_type='question_media', target_id=media.id, metadata={'question_id': question_id, 'bank_version_id': bank_version_id, 'mime_type': media.mime_type, 'size_bytes': media.size_bytes})
        return media
    except (ValueError, StorageError) as exc:
        db.rollback()
        raise public_http_exception(status_code=400, code='BANK_QUESTION_MEDIA_INVALID', message=str(exc), logger_name=__name__) from exc


@router.get('/bank-versions/{bank_version_id}/questions/{question_id}/media/{media_id}/content')
def get_bank_question_media_content(bank_version_id: str, question_id: str, media_id: str, db: Session = Depends(get_db), user: UserContext = Depends(require_permission('view_questions'))):
    _require_bank_version(db, user, 'bank.view', bank_version_id)
    media = db.query(QuestionMedia).filter(QuestionMedia.id == media_id, QuestionMedia.question_id == question_id, QuestionMedia.bank_version_id == bank_version_id).first()
    if not media:
        raise HTTPException(status_code=404, detail='Không tìm thấy ảnh câu hỏi.')
    try:
        raw = get_object_storage().read_bytes(media.storage_reference)
    except StorageError as exc:
        raise public_http_exception(
            status_code=404,
            code='BANK_QUESTION_MEDIA_MISSING',
            message='Ảnh câu hỏi không còn tồn tại trong storage.',
            logger_name=__name__,
        ) from exc
    return Response(content=raw, media_type=media.mime_type, headers={'Cache-Control':'private, max-age=300','X-Content-Type-Options':'nosniff'})


@router.patch('/bank-versions/{bank_version_id}/questions/{question_id}/media/{media_id}', response_model=BankQuestionMediaOut)
def update_bank_question_media(bank_version_id: str, question_id: str, media_id: str, payload: BankQuestionMediaAltUpdateRequest, db: Session = Depends(get_db), user: UserContext = Depends(require_permission('edit_questions'))):
    _require_bank_version(db, user, 'question.edit', bank_version_id)
    try:
        return QuestionMediaService(db).update_alt(
            bank_version_id=bank_version_id,
            question_id=question_id,
            media_id=media_id,
            alt_text=payload.alt_text,
            sort_order=payload.sort_order,
        )
    except ValueError as exc:
        raise public_http_exception(
            status_code=400,
            code='BANK_QUESTION_MEDIA_INVALID',
            message=str(exc),
            logger_name=__name__,
        ) from exc


@router.delete('/bank-versions/{bank_version_id}/questions/{question_id}/media/{media_id}', response_model=BankQuestionMediaDeleteOut)
def delete_bank_question_media(bank_version_id: str, question_id: str, media_id: str, db: Session = Depends(get_db), user: UserContext = Depends(require_permission('edit_questions'))):
    _require_bank_version(db, user, 'question.edit', bank_version_id)
    try:
        return QuestionMediaService(db).delete(
            bank_version_id=bank_version_id,
            question_id=question_id,
            media_id=media_id,
        )
    except ValueError as exc:
        raise public_http_exception(
            status_code=400,
            code='BANK_QUESTION_MEDIA_INVALID',
            message=str(exc),
            logger_name=__name__,
        ) from exc


@router.post('/bank-versions/{bank_version_id}/materials/recheck-carry-over')
def recheck_carry_over_after_material_change(bank_version_id: str, db: Session = Depends(get_db), user: UserContext = Depends(require_permission('review_questions'))):
    """Manually rerun the automatic material recheck for cloned questions."""
    _require_bank_version(db, user, 'question.reject', bank_version_id)
    try:
        result = VersionedQuestionBankService(db).auto_retire_carry_over_questions_for_changed_materials(
            bank_version_id=bank_version_id,
            actor=user.user_id,
            reason='manual_material_recheck',
            commit=True,
        )
        log_audit(db, action='question_bank.material.recheck_carry_over', status='success', message=result.get('message', ''), user=user, target_type='bank_version', target_id=bank_version_id, metadata={k: v for k, v in result.items() if k not in {'kept_question_ids', 'retired_question_ids', 'safe_skipped_question_ids'}})
        return result
    except Exception as exc:
        log_audit(db, action='question_bank.material.recheck_carry_over', status='failed', error_type=AuditErrorType.VALIDATION_ERROR, message='Không thể hoàn tất thao tác ngân hàng câu hỏi.', user=user, target_type='bank_version', target_id=bank_version_id)
        raise public_http_exception(status_code=400, code='BANK_OPERATION_FAILED', message='Không thể hoàn tất thao tác ngân hàng câu hỏi.', logger_name=__name__) from exc


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
            persist=False,
        )
        log_audit(db, action='question_bank.version.diff.preview', status='success', message=result.get('message', ''), user=user, target_type='bank_version', target_id=bank_version_id, metadata={'diff_id': result.get('diff_id'), 'summary': result.get('summary')})
        return result
    except Exception as exc:
        log_audit(db, action='question_bank.version.diff.preview', status='failed', error_type=AuditErrorType.VALIDATION_ERROR, message='Không thể xem trước so sánh phiên bản.', user=user, target_type='bank_version', target_id=bank_version_id)
        raise public_http_exception(
            status_code=400,
            code='BANK_VERSION_DIFF_PREVIEW_FAILED',
            message='Không thể xem trước thay đổi giữa các phiên bản bộ đề.',
            logger_name=__name__,
        ) from exc


@router.post('/bank-versions/{bank_version_id}/diffs', response_model=BankVersionDiffPreviewOut)
def create_bank_version_diff(bank_version_id: str, payload: BankVersionDiffCreateRequest, db: Session = Depends(get_db), user: UserContext = Depends(require_permission('edit_questions'))):
    _require_bank_version(db, user, 'question.edit', bank_version_id)
    try:
        base_id = payload.base_bank_version_id
        if not base_id:
            target = db.get(QuestionBankVersion, bank_version_id)
            if not target or not target.based_on_version_id:
                raise ValueError('Hãy truyền base_bank_version_id hoặc tạo Bank Version mới với based_on_version_id.')
            base_id = target.based_on_version_id
        _require_bank_version(db, user, 'bank.view', base_id)
        result = VersionedQuestionBankService(db).create_bank_version_diff(
            from_bank_version_id=base_id,
            to_bank_version_id=bank_version_id,
            actor=user.user_id,
        )
        log_audit(db, action='question_bank.version.diff.create', status='success', message=result.get('message', ''), user=user, target_type='bank_version', target_id=bank_version_id, metadata={'diff_id': result.get('diff_id'), 'summary': result.get('summary')})
        return result
    except Exception as exc:
        log_audit(db, action='question_bank.version.diff.create', status='failed', error_type=AuditErrorType.VALIDATION_ERROR, message='Không thể lưu bản so sánh phiên bản.', user=user, target_type='bank_version', target_id=bank_version_id)
        raise public_http_exception(
            status_code=400,
            code='BANK_VERSION_DIFF_CREATE_FAILED',
            message='Không thể lưu bản so sánh phiên bản bộ đề.',
            logger_name=__name__,
        ) from exc


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
        log_audit(db, action='question_bank.version.carry_over', status='failed', error_type=AuditErrorType.VALIDATION_ERROR, message='Không thể hoàn tất thao tác ngân hàng câu hỏi.', user=user, target_type='bank_version', target_id=bank_version_id)
        raise public_http_exception(status_code=400, code='BANK_OPERATION_FAILED', message='Không thể hoàn tất thao tác ngân hàng câu hỏi.', logger_name=__name__) from exc


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
        log_audit(db, action='question_bank.version.questions.retire', status='failed', error_type=AuditErrorType.VALIDATION_ERROR, message='Không thể hoàn tất thao tác ngân hàng câu hỏi.', user=user, target_type='bank_version', target_id=bank_version_id)
        raise public_http_exception(status_code=400, code='BANK_OPERATION_FAILED', message='Không thể hoàn tất thao tác ngân hàng câu hỏi.', logger_name=__name__) from exc


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
        data = BankVersionQuestionOut.model_validate(question).model_dump()
        data['question_type'] = normalize_question_type(question.question_type)
        data['question_content_json'] = canonical_question_content(question)
        data['media'] = [BankQuestionMediaOut.model_validate(item).model_dump() for item in QuestionMediaService(db).list_media(bank_version_id, question_id)]
        return data
    except Exception as exc:
        log_audit(db, action='question_bank.version.question.update', status='failed', error_type=AuditErrorType.VALIDATION_ERROR, message='Không thể hoàn tất thao tác ngân hàng câu hỏi.', user=user, target_type='question', target_id=question_id)
        raise public_http_exception(status_code=400, code='BANK_OPERATION_FAILED', message='Không thể hoàn tất thao tác ngân hàng câu hỏi.', logger_name=__name__) from exc


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
        log_audit(db, action='question_bank.version.question.review', status='failed', error_type=AuditErrorType.VALIDATION_ERROR, message='Không thể hoàn tất thao tác ngân hàng câu hỏi.', user=user, target_type='question', target_id=question_id)
        raise public_http_exception(status_code=400, code='BANK_OPERATION_FAILED', message='Không thể hoàn tất thao tác ngân hàng câu hỏi.', logger_name=__name__) from exc


@router.post('/bank-versions/{bank_version_id}/questions/bulk-review', response_model=BankQuestionBulkReviewOut)
def bulk_review_bank_questions(bank_version_id: str, payload: BankQuestionBulkReviewRequest, db: Session = Depends(get_db), user: UserContext = Depends(require_permission('review_questions'))):
    try:
        _require_bank_version(db, user, 'question.approve' if payload.action != 'reject' else 'question.reject', bank_version_id)
        result = VersionedQuestionBankService(db).bulk_review_bank_questions(
            bank_version_id=bank_version_id,
            action=payload.action,
            question_ids=payload.question_ids,
            approve_all_pending=payload.approve_all_pending,
            apply_to_filtered=payload.apply_to_filtered,
            status_filter=payload.status_filter,
            difficulty=payload.difficulty,
            search=payload.search,
            note=payload.note,
            actor=user.user_id,
        )
        log_audit(db, action=_BULK_REVIEW_AUDIT_ACTION, status='success', message=result.get('message', ''), user=user, target_type='bank_version', target_id=bank_version_id, metadata={'changed_count': result.get('changed_count'), 'skipped_count': result.get('skipped_count'), 'action': payload.action})
        return result
    except HTTPException:
        # Preserve explicit RBAC / request errors. Do not turn a legitimate 403
        # into an opaque 400/500 while trying to sanitize the endpoint.
        raise
    except SQLAlchemyError as exc:
        db.rollback()
        log_audit(
            db,
            action=_BULK_REVIEW_AUDIT_ACTION,
            status='failed',
            error_type=AuditErrorType.SYSTEM_ERROR,
            message='Bulk review gặp lỗi database/schema. Kiểm tra migration và dữ liệu legacy.',
            user=user,
            target_type='bank_version',
            target_id=bank_version_id,
            metadata={'action': payload.action, 'error_class': exc.__class__.__name__},
        )
        raise public_http_exception(
            status_code=503,
            code='BANK_DATABASE_NOT_READY',
            message='Database chưa sẵn sàng cho thao tác duyệt. Hãy kiểm tra migration/schema và thử lại.',
            logger_name=__name__,
        ) from exc
    except ValueError as exc:
        db.rollback()
        log_audit(db, action=_BULK_REVIEW_AUDIT_ACTION, status='failed', error_type=AuditErrorType.VALIDATION_ERROR, message=str(exc)[:1000], user=user, target_type='bank_version', target_id=bank_version_id, metadata={'action': payload.action})
        raise public_http_exception(status_code=400, code='BANK_OPERATION_FAILED', message=str(exc) or 'Không thể hoàn tất thao tác ngân hàng câu hỏi.', logger_name=__name__) from exc
    except Exception as exc:
        db.rollback()
        log_audit(db, action=_BULK_REVIEW_AUDIT_ACTION, status='failed', error_type=AuditErrorType.SYSTEM_ERROR, message='Không thể hoàn tất thao tác ngân hàng câu hỏi.', user=user, target_type='bank_version', target_id=bank_version_id, metadata={'action': payload.action, 'error_class': exc.__class__.__name__})
        raise public_http_exception(status_code=500, code='BANK_OPERATION_INTERNAL_ERROR', message='Không thể hoàn tất thao tác ngân hàng câu hỏi.', logger_name=__name__) from exc


@router.post('/bank-versions/{bank_version_id}/diff/mark-resolved', response_model=BankDocumentDiffResolveOut)
def mark_bank_diff_resolved(bank_version_id: str, payload: BankDocumentDiffResolveRequest, db: Session = Depends(get_db), user: UserContext = Depends(require_permission('review_questions'))):
    _require_bank_version(db, user, 'question.approve', bank_version_id)
    try:
        result = VersionedQuestionBankService(db).mark_document_diff_resolved(bank_version_id=bank_version_id, note=payload.note, actor=user.user_id)
        log_audit(db, action='question_bank.version.diff.mark_resolved', status='success', message=result.get('message', ''), user=user, target_type='bank_version', target_id=bank_version_id)
        return result
    except Exception as exc:
        log_audit(db, action='question_bank.version.diff.mark_resolved', status='failed', error_type=AuditErrorType.VALIDATION_ERROR, message='Không thể hoàn tất thao tác ngân hàng câu hỏi.', user=user, target_type='bank_version', target_id=bank_version_id)
        raise public_http_exception(status_code=400, code='BANK_OPERATION_FAILED', message='Không thể hoàn tất thao tác ngân hàng câu hỏi.', logger_name=__name__) from exc


@router.get('/bank-versions/{bank_version_id}/release/readiness', response_model=BankReleaseReadinessOut)
def bank_release_readiness(bank_version_id: str, db: Session = Depends(get_db), user: UserContext = Depends(require_permission('view_questions'))):
    _require_bank_version(db, user, 'bank.view', bank_version_id)
    return VersionedQuestionBankService(db).release_readiness(bank_version_id=bank_version_id)


@router.get('/releases', response_model=PaginatedOut[BankReleaseOut])
def list_releases(bank_version_id: str | None = None, chapter_id: str | None = None, page: int = Query(1, ge=1), page_size: int = Query(50, ge=1, le=100), db: Session = Depends(get_db), user: UserContext = Depends(require_permission('view_questions'))):
    query = _biz(db).apply_hierarchy_filter(db.query(QuestionBankRelease), QuestionBankRelease, user)
    if bank_version_id:
        _require_bank_version(db, user, 'bank.view', bank_version_id)
        query = query.filter(QuestionBankRelease.bank_version_id == bank_version_id)
    if chapter_id:
        _require_visible(db, user, 'CHAPTER', chapter_id)
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
        log_audit(db, action='question_bank.release.create', status='failed', error_type=AuditErrorType.VALIDATION_ERROR, message='Không thể hoàn tất thao tác ngân hàng câu hỏi.', user=user, target_type='bank_release')
        raise public_http_exception(status_code=400, code='BANK_OPERATION_FAILED', message='Không thể hoàn tất thao tác ngân hàng câu hỏi.', logger_name=__name__) from exc


@router.delete('/releases/{release_id}', response_model=EntityDeleteOut)
def cancel_failed_release(release_id: str, db: Session = Depends(get_db), user: UserContext = Depends(require_permission('publish_questions'))):
    _require_release(db, user, 'bank.release.publish', release_id)
    try:
        result = VersionedQuestionBankService(db).cancel_failed_release(release_id=release_id, actor=user.user_id)
        log_audit(db, action='question_bank.release.cancel_failed', status='success', message=result.get('message', ''), user=user, target_type='bank_release', target_id=release_id, metadata=result)
        return result
    except Exception as exc:
        log_audit(db, action='question_bank.release.cancel_failed', status='failed', error_type=AuditErrorType.VALIDATION_ERROR, message='Không thể hoàn tất thao tác ngân hàng câu hỏi.', user=user, target_type='bank_release', target_id=release_id)
        raise public_http_exception(status_code=400, code='BANK_OPERATION_FAILED', message='Không thể hoàn tất thao tác ngân hàng câu hỏi.', logger_name=__name__) from exc




@router.get('/releases/{release_id}/preview', response_model=BankReleasePreviewOut)
def preview_bank_release_snapshot(
    release_id: str,
    db: Session = Depends(get_db),
    user: UserContext = Depends(require_permission('view_questions')),
):
    release = db.get(QuestionBankRelease, release_id)
    if not release:
        raise HTTPException(status_code=404, detail='Không tìm thấy Release')
    _require_bank_version(db, user, 'bank.view', release.bank_version_id)
    rows = db.query(BankReleaseQuestion, Question).join(Question, Question.id == BankReleaseQuestion.question_id).filter(
        BankReleaseQuestion.bank_release_id == release.id,
    ).order_by(BankReleaseQuestion.included_at.asc(), BankReleaseQuestion.id.asc()).all()
    question_ids = [question.id for _, question in rows]
    media_rows = (
        db.query(QuestionMedia)
        .filter(QuestionMedia.question_id.in_(question_ids))
        .order_by(QuestionMedia.question_id.asc(), QuestionMedia.sort_order.asc(), QuestionMedia.created_at.asc(), QuestionMedia.id.asc())
        .all()
        if question_ids else []
    )
    media_by_question: dict[str, list[QuestionMedia]] = {}
    for media in media_rows:
        media_by_question.setdefault(media.question_id, []).append(media)
    questions = [{
        'release_question_id': snapshot.id,
        'question_id': question.id,
        'question_text': question.question_text,
        'question_type': normalize_question_type(question.question_type),
        'question_content_json': canonical_question_content(question),
        'media': [BankQuestionMediaOut.model_validate(media).model_dump() for media in media_by_question.get(question.id, [])],
        'option_a': question.option_a,
        'option_b': question.option_b,
        'option_c': question.option_c,
        'option_d': question.option_d,
        'correct_answer': question.correct_answer,
        'difficulty': snapshot.difficulty or question.difficulty,
        'concept_title': question.concept_title,
        'question_family_id': snapshot.question_family_id or question.question_family_id,
        'included_at': snapshot.included_at,
    } for snapshot, question in rows]
    return {
        'release': release,
        'frozen_snapshot': True,
        'total_questions': len(questions),
        'counts': {
            'easy': sum(1 for item in questions if item['difficulty'] == 'easy'),
            'medium': sum(1 for item in questions if item['difficulty'] == 'medium'),
            'hard': sum(1 for item in questions if item['difficulty'] == 'hard'),
        },
        'questions': questions,
    }


@router.get('/releases/{release_id}/publish-audit')
def release_publish_audit(release_id: str, db: Session = Depends(get_db), user: UserContext = Depends(require_permission('view_questions'))):
    _require_release(db, user, 'bank.view', release_id)
    # Read-only QA endpoint: do not write audit rows, enqueue jobs, call Open edX,
    # or mutate Release state. Operators can export the response as UAT evidence.
    return VersionedQuestionBankService(db).release_publish_audit(release_id=release_id)


def _enqueue_release_publish_job(
    release_id: str,
    payload: BankReleasePublishRequest,
    db: Session,
    user: UserContext,
) -> tuple[BankOperationJob, bool]:
    # Serialize enqueue decisions per Release. Two browser clicks or two tabs
    # cannot create two active Celery publish messages for the same snapshot.
    release = (
        db.query(QuestionBankRelease)
        .filter(QuestionBankRelease.id == release_id)
        .with_for_update()
        .one_or_none()
    )
    if not release:
        raise HTTPException(status_code=404, detail='Không tìm thấy Bank Release')

    existing = (
        db.query(BankOperationJob)
        .filter(
            BankOperationJob.operation_type == 'release_publish',
            BankOperationJob.release_id == release_id,
            BankOperationJob.status.in_(['queued', 'running']),
        )
        .order_by(BankOperationJob.created_at.desc(), BankOperationJob.id.desc())
        .first()
    )
    if existing:
        return existing, False

    request_json = payload.model_dump()
    request_json.update({'release_id': release_id, 'bank_version_id': release.bank_version_id})
    job = _create_bank_operation_job(
        db,
        operation_type='release_publish',
        target_type='bank_release',
        target_id=release_id,
        user=user,
        bank_version_id=release.bank_version_id,
        release_id=release_id,
        request_json=request_json,
        progress_total=100,
        progress_label='Đang chờ worker đưa bộ đề lên CMS',
    )
    job = _enqueue_bank_job_or_fail(db, job, bank_release_publish_task, label='Đã đưa job publish Release vào hàng đợi')
    return job, True


@router.post('/releases/{release_id}/publish-openedx-job', response_model=BankOperationJobQueuedOut)
def publish_release_to_openedx_job(release_id: str, payload: BankReleasePublishRequest, db: Session = Depends(get_db), user: UserContext = Depends(require_permission('publish_questions'))):
    _require_release(db, user, 'bank.release.publish', release_id)
    job, created = _enqueue_release_publish_job(release_id, payload, db, user)
    message = 'Đã đưa Release vào hàng đợi publish sang Open edX.' if created else 'Release này đã có job publish đang chờ/chạy; không tạo job trùng.'
    log_audit(db, action='question_bank.release.publish_openedx.job', status='success', message=message, user=user, target_type='bank_operation_job', target_id=job.id, metadata={'release_id': release_id, 'created': created})
    return _queued_response(job, message)


@router.post('/releases/{release_id}/publish-openedx', response_model=BankOperationJobQueuedOut, status_code=202)
def publish_release_to_openedx(release_id: str, payload: BankReleasePublishRequest, db: Session = Depends(get_db), user: UserContext = Depends(require_permission('publish_questions'))):
    """Compatibility endpoint: publish is worker-only and never blocks Uvicorn."""
    _require_release(db, user, 'bank.release.publish', release_id)
    job, created = _enqueue_release_publish_job(release_id, payload, db, user)
    message = 'Đã đưa bộ đề vào hàng đợi CMS.' if created else 'Bộ đề đã có job publish đang chờ/chạy.'
    log_audit(db, action='question_bank.release.publish_openedx', status='success', message=message, user=user, target_type='bank_operation_job', target_id=job.id, metadata={'release_id': release_id, 'created': created, 'worker_only': True})
    return _queued_response(job, message)


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
            single_select_count=payload.single_select_count,
            multi_select_count=payload.multi_select_count,
            text_input_count=payload.text_input_count,
            numerical_input_count=payload.numerical_input_count,
            quiz_blueprint_id=payload.quiz_blueprint_id,
        )
        log_audit(db, action='question_bank.release.quiz.preview', status='success', message=result.get('message', ''), user=user, target_type='bank_release', target_id=release_id, metadata={'slot_count': result.get('total_questions'), 'warnings': result.get('warnings')})
        return result
    except Exception as exc:
        log_audit(db, action='question_bank.release.quiz.preview', status='failed', error_type=AuditErrorType.VALIDATION_ERROR, message='Không thể hoàn tất thao tác ngân hàng câu hỏi.', user=user, target_type='bank_release', target_id=release_id)
        raise public_http_exception(status_code=400, code='BANK_OPERATION_FAILED', message='Không thể hoàn tất thao tác ngân hàng câu hỏi.', logger_name=__name__) from exc



@router.post('/releases/{release_id}/quiz/create-job', response_model=BankOperationJobQueuedOut)
def create_quiz_from_release_job(release_id: str, payload: BankReleaseQuizCreateRequest, db: Session = Depends(get_db), user: UserContext = Depends(require_permission('publish_questions'))):
    _require_release(db, user, 'quiz.create_openedx', release_id)
    request_json = payload.model_dump()
    request_json['release_id'] = release_id

    # Do not create duplicate Quiz-create jobs for the same release + mapping.
    # If a queued job exists from a previous worker outage, requeue that exact job
    # and return it instead of creating another row that will also sit at 0%.
    active_jobs = (
        db.query(BankOperationJob)
        .filter(
            BankOperationJob.operation_type == 'quiz_create',
            BankOperationJob.target_type == 'bank_release',
            BankOperationJob.target_id == release_id,
            BankOperationJob.status.in_(['queued', 'running']),
        )
        .order_by(BankOperationJob.created_at.desc(), BankOperationJob.id.desc())
        .limit(20)
        .all()
    )
    for existing in active_jobs:
        existing_request = existing.request_json or {}
        if str(existing_request.get('course_chapter_mapping_id') or '') == str(payload.course_chapter_mapping_id):
            if existing.status == 'queued':
                existing = _enqueue_bank_job_or_fail(db, existing, bank_quiz_create_task, label='Đã đưa lại Quiz vào hàng đợi tạo trên Open edX')
                message = 'Đã có job tạo Quiz đang chờ; hệ thống đã đưa lại job đó vào hàng đợi Celery thay vì tạo job trùng.'
            else:
                message = 'Đã có job tạo Quiz đang chạy cho Release/mapping này; không tạo job trùng.'
            return _queued_response(existing, message)

    job = _create_bank_operation_job(
        db,
        operation_type='quiz_create',
        target_type='bank_release',
        target_id=release_id,
        user=user,
        release_id=release_id,
        request_json=request_json,
        progress_total=7,
        progress_label='Đã đưa Quiz vào hàng đợi tạo trên Open edX',
    )
    job = _enqueue_bank_job_or_fail(db, job, bank_quiz_create_task, label='Đã đưa Quiz vào hàng đợi tạo trên Open edX')
    log_audit(db, action='question_bank.release.quiz.create.job', status='success', message='Đã tạo job tạo Quiz Open edX', user=user, target_type='bank_operation_job', target_id=job.id, metadata={'release_id': release_id, 'course_chapter_mapping_id': payload.course_chapter_mapping_id})
    return _queued_response(job, 'Đã đưa Quiz vào hàng đợi tạo trên Open edX.')


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
            single_select_count=payload.single_select_count,
            multi_select_count=payload.multi_select_count,
            text_input_count=payload.text_input_count,
            numerical_input_count=payload.numerical_input_count,
            quiz_blueprint_id=payload.quiz_blueprint_id,
            custom_timer_enabled=payload.custom_timer_enabled,
            time_limit_minutes=payload.time_limit_minutes,
            retake_cooldown_minutes=payload.retake_cooldown_minutes,
            auto_submit_on_timeout=payload.auto_submit_on_timeout,
            lock_after_timeout=payload.lock_after_timeout,
            native_timed_exam=payload.native_timed_exam,
            assessment_type=payload.assessment_type,
            actor=user.user_id,
            expected_bank_release_id=release_id,
        )
        log_audit(db, action='question_bank.release.quiz.create', status='success', message='Tạo Quiz từ Bank Release thành công', user=user, course_id=result.get('openedx_course_id'), target_type='course_quiz_instance', target_id=result.get('course_quiz_instance_id'), metadata={'bank_release_id': release_id, 'openedx_unit_node_id': result.get('openedx_unit_node_id')})
        return result
    except ValueError as exc:
        log_audit(db, action='question_bank.release.quiz.create', status='failed', error_type=AuditErrorType.VALIDATION_ERROR, message='Không thể hoàn tất thao tác ngân hàng câu hỏi.', user=user, target_type='bank_release', target_id=release_id)
        raise public_http_exception(status_code=400, code='BANK_OPERATION_FAILED', message='Không thể hoàn tất thao tác ngân hàng câu hỏi.', logger_name=__name__) from exc
    except Exception as exc:
        log_audit(db, action='question_bank.release.quiz.create', status='failed', error_type=AuditErrorType.EXTERNAL_SERVICE_ERROR, message='Không thể hoàn tất thao tác ngân hàng câu hỏi.', user=user, target_type='bank_release', target_id=release_id)
        raise public_http_exception(status_code=502, code='BANK_OPERATION_FAILED', message='Không thể hoàn tất thao tác ngân hàng câu hỏi.', logger_name=__name__) from exc




@router.post('/quiz/auto-map/preview', response_model=QuizAutoMapOut)
async def preview_quiz_auto_map(payload: QuizAutoMapRequest, db: Session = Depends(get_db), user: UserContext = Depends(require_permission('publish_questions'))):
    if payload.selected_subject_offering_id:
        _require_business(db, user, 'quiz.preview', 'SUBJECT_VERSION', payload.selected_subject_offering_id)
    try:
        result = await VersionedQuestionBankService(db).preview_quiz_auto_map(openedx_course_id=payload.openedx_course_id, selected_subject_offering_id=payload.selected_subject_offering_id, chapter_plan=[item.model_dump() for item in payload.chapter_plan])
        log_audit(db, action='question_bank.quiz.auto_map.preview', status='success' if result.get('ok') else 'failed', error_type=None if result.get('ok') else AuditErrorType.VALIDATION_ERROR, message=result.get('message', ''), user=user, course_id=payload.openedx_course_id, target_type='quiz_auto_map', metadata={'summary': result.get('summary'), 'blocking_errors': result.get('blocking_errors')})
        return result
    except Exception as exc:
        log_audit(db, action='question_bank.quiz.auto_map.preview', status='failed', error_type=AuditErrorType.EXTERNAL_SERVICE_ERROR, message='Không thể hoàn tất thao tác ngân hàng câu hỏi.', user=user, course_id=payload.openedx_course_id, target_type='quiz_auto_map')
        raise public_http_exception(status_code=502, code='BANK_OPERATION_FAILED', message='Không thể hoàn tất thao tác ngân hàng câu hỏi.', logger_name=__name__) from exc


@router.post('/quiz/auto-map/apply', response_model=QuizAutoMapOut)
async def apply_quiz_auto_map(payload: QuizAutoMapRequest, db: Session = Depends(get_db), user: UserContext = Depends(require_permission('publish_questions'))):
    if payload.selected_subject_offering_id:
        _require_business(db, user, 'quiz.create_openedx', 'SUBJECT_VERSION', payload.selected_subject_offering_id)
    try:
        result = await VersionedQuestionBankService(db).apply_quiz_auto_map(openedx_course_id=payload.openedx_course_id, selected_subject_offering_id=payload.selected_subject_offering_id, chapter_plan=[item.model_dump() for item in payload.chapter_plan], actor=user.user_id)
        log_audit(db, action='question_bank.quiz.auto_map.apply', status='success', message=result.get('message', ''), user=user, course_id=payload.openedx_course_id, target_type='quiz_auto_map', metadata={'summary': result.get('summary'), 'mapping_count': len(result.get('mappings') or [])})
        return result
    except ValueError as exc:
        log_audit(db, action='question_bank.quiz.auto_map.apply', status='failed', error_type=AuditErrorType.VALIDATION_ERROR, message='Không thể hoàn tất thao tác ngân hàng câu hỏi.', user=user, course_id=payload.openedx_course_id, target_type='quiz_auto_map')
        raise public_http_exception(status_code=400, code='BANK_OPERATION_FAILED', message='Không thể hoàn tất thao tác ngân hàng câu hỏi.', logger_name=__name__) from exc
    except Exception as exc:
        log_audit(db, action='question_bank.quiz.auto_map.apply', status='failed', error_type=AuditErrorType.EXTERNAL_SERVICE_ERROR, message='Không thể hoàn tất thao tác ngân hàng câu hỏi.', user=user, course_id=payload.openedx_course_id, target_type='quiz_auto_map')
        raise public_http_exception(status_code=502, code='BANK_OPERATION_FAILED', message='Không thể hoàn tất thao tác ngân hàng câu hỏi.', logger_name=__name__) from exc


@router.get('/course-mappings', response_model=PaginatedOut[CourseMappingOut])
def list_course_mappings(subject_id: str | None = None, page: int = Query(1, ge=1), page_size: int = Query(50, ge=1, le=100), db: Session = Depends(get_db), user: UserContext = Depends(require_permission('view_questions'))):
    query = _biz(db).apply_hierarchy_filter(db.query(EdxCourseMapping), EdxCourseMapping, user)
    if subject_id:
        _require_visible(db, user, 'SUBJECT', subject_id)
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
        log_audit(db, action='question_bank.course_mapping.create', status='failed', error_type=AuditErrorType.VALIDATION_ERROR, message='Không thể hoàn tất thao tác ngân hàng câu hỏi.', user=user, target_type='course_mapping')
        raise public_http_exception(status_code=400, code='BANK_OPERATION_FAILED', message='Không thể hoàn tất thao tác ngân hàng câu hỏi.', logger_name=__name__) from exc


@router.get('/course-chapter-mappings', response_model=PaginatedOut[CourseChapterMappingOut])
def list_course_chapter_mappings(course_mapping_id: str | None = None, page: int = Query(1, ge=1), page_size: int = Query(50, ge=1, le=100), db: Session = Depends(get_db), user: UserContext = Depends(require_permission('view_questions'))):
    query = db.query(EdxCourseChapterMapping)
    if course_mapping_id:
        mapping = db.get(EdxCourseMapping, course_mapping_id)
        if not mapping:
            return _empty_page(page, page_size, max_page_size=100)
        _require_visible(db, user, 'SUBJECT', mapping.subject_id)
        query = query.filter(EdxCourseChapterMapping.course_mapping_id == course_mapping_id)
        chapter_ids = _biz(db).accessible_chapter_ids(user)
        if chapter_ids is not None:
            if not chapter_ids:
                return _empty_page(page, page_size, max_page_size=100)
            query = query.filter(EdxCourseChapterMapping.subject_chapter_id.in_(chapter_ids))
    else:
        chapter_ids = _biz(db).accessible_chapter_ids(user)
        if chapter_ids is not None:
            if not chapter_ids:
                return _empty_page(page, page_size, max_page_size=100)
            query = query.filter(EdxCourseChapterMapping.subject_chapter_id.in_(chapter_ids))
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
        log_audit(db, action='question_bank.course_chapter_mapping.create', status='failed', error_type=AuditErrorType.VALIDATION_ERROR, message='Không thể hoàn tất thao tác ngân hàng câu hỏi.', user=user, target_type='course_chapter_mapping')
        raise public_http_exception(status_code=400, code='BANK_OPERATION_FAILED', message='Không thể hoàn tất thao tác ngân hàng câu hỏi.', logger_name=__name__) from exc


@router.get('/course-quiz-instances', response_model=PaginatedOut[CourseQuizInstanceOut])
def list_course_quiz_instances(openedx_course_id: str | None = None, bank_release_id: str | None = None, page: int = Query(1, ge=1), page_size: int = Query(50, ge=1, le=100), limit: int | None = None, db: Session = Depends(get_db), user: UserContext = Depends(require_permission('view_questions'))):
    # limit is kept for frontend/backward query compatibility; page_size is the real contract.
    if limit is not None:
        page_size = limit
    query = _biz(db).apply_hierarchy_filter(db.query(CourseQuizInstance), CourseQuizInstance, user)
    if openedx_course_id:
        course_id_candidates = openedx_course_id_candidates(openedx_course_id)
        if not course_id_candidates:
            raise HTTPException(status_code=422, detail='Course ID phải có dạng course-v1:ORG+COURSE+RUN.')
        query = query.filter(CourseQuizInstance.openedx_course_id.in_(course_id_candidates))
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
        log_audit(db, action='question_bank.course_quiz.rollback', status='failed', error_type=AuditErrorType.EXTERNAL_SERVICE_ERROR, message='Không thể hoàn tất thao tác ngân hàng câu hỏi.', user=user, target_type='course_quiz_instance', target_id=instance_id)
        raise public_http_exception(status_code=400, code='BANK_OPERATION_FAILED', message='Không thể hoàn tất thao tác ngân hàng câu hỏi.', logger_name=__name__) from exc


@router.get('/quiz-blueprints', response_model=PaginatedOut[QuizBlueprintOut])
def list_quiz_blueprints(chapter_id: str | None = None, page: int = Query(1, ge=1), page_size: int = Query(50, ge=1, le=100), db: Session = Depends(get_db), user: UserContext = Depends(require_permission('view_questions'))):
    query = _biz(db).apply_hierarchy_filter(db.query(QuizBlueprint), QuizBlueprint, user)
    if chapter_id:
        _require_visible(db, user, 'CHAPTER', chapter_id)
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
        log_audit(db, action='question_bank.quiz_blueprint.create', status='failed', error_type=AuditErrorType.VALIDATION_ERROR, message='Không thể hoàn tất thao tác ngân hàng câu hỏi.', user=user, target_type='quiz_blueprint')
        raise public_http_exception(status_code=400, code='BANK_OPERATION_FAILED', message='Không thể hoàn tất thao tác ngân hàng câu hỏi.', logger_name=__name__) from exc
