from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from sqlalchemy.orm import Session

from app.core.rbac import UserContext, require_permission
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
    ChapterOut,
    CourseChapterMappingCreate,
    CourseChapterMappingOut,
    CourseChapterMappingValidateRequest,
    CourseMappingCreate,
    CourseMappingOut,
    CourseMappingValidateRequest,
    MappingValidationOut,
    DepartmentCreate,
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
    SubjectCreate,
    SubjectOut,
    SubjectOfferingCreate,
    SubjectOfferingOut,
)
from app.services.audit_log import AuditErrorType, log_audit
from app.services.question_bank_service import VersionedQuestionBankService

router = APIRouter()


_BANK_UPLOAD_MAX_BYTES = 50 * 1024 * 1024


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


@router.get('/summary', response_model=BankSummaryOut)
def summary(db: Session = Depends(get_db), user: UserContext = Depends(require_permission('view_questions'))):
    return VersionedQuestionBankService(db).summary()


@router.get('/dashboard/overview')
def dashboard_overview(db: Session = Depends(get_db), user: UserContext = Depends(require_permission('view_questions'))):
    return VersionedQuestionBankService(db).dashboard_overview()


@router.get('/dashboard/search')
def dashboard_search(q: str = '', limit: int = 20, db: Session = Depends(get_db), user: UserContext = Depends(require_permission('view_questions'))):
    return VersionedQuestionBankService(db).dashboard_search(q=q, limit=limit)


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


@router.get('/departments', response_model=list[DepartmentOut])
def list_departments(db: Session = Depends(get_db), user: UserContext = Depends(require_permission('view_questions'))):
    return db.query(Department).order_by(Department.code.asc()).all()


@router.post('/departments', response_model=DepartmentOut)
def create_department(payload: DepartmentCreate, db: Session = Depends(get_db), user: UserContext = Depends(require_permission('manage_settings'))):
    try:
        item = VersionedQuestionBankService(db).create_department(**payload.model_dump())
        log_audit(db, action='question_bank.department.create', status='success', message='Tạo bộ môn thành công', user=user, target_type='department', target_id=item.id)
        return item
    except Exception as exc:
        log_audit(db, action='question_bank.department.create', status='failed', error_type=AuditErrorType.VALIDATION_ERROR, message=str(exc), user=user, target_type='department')
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get('/subjects', response_model=list[SubjectOut])
def list_subjects(department_id: str | None = None, db: Session = Depends(get_db), user: UserContext = Depends(require_permission('view_questions'))):
    query = db.query(Subject)
    if department_id:
        query = query.filter(Subject.department_id == department_id)
    return query.order_by(Subject.code.asc()).all()


@router.post('/subjects', response_model=SubjectOut)
def create_subject(payload: SubjectCreate, db: Session = Depends(get_db), user: UserContext = Depends(require_permission('manage_settings'))):
    try:
        item = VersionedQuestionBankService(db).create_subject(**payload.model_dump())
        log_audit(db, action='question_bank.subject.create', status='success', message='Tạo môn học thành công', user=user, target_type='subject', target_id=item.id)
        return item
    except Exception as exc:
        log_audit(db, action='question_bank.subject.create', status='failed', error_type=AuditErrorType.VALIDATION_ERROR, message=str(exc), user=user, target_type='subject')
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get('/subject-offerings', response_model=list[SubjectOfferingOut])
@router.get('/subject-versions', response_model=list[SubjectOfferingOut])
def list_subject_offerings(subject_id: str | None = None, db: Session = Depends(get_db), user: UserContext = Depends(require_permission('view_questions'))):
    query = db.query(SubjectOffering)
    if subject_id:
        query = query.filter(SubjectOffering.subject_id == subject_id)
    return query.order_by(SubjectOffering.code.asc()).all()


@router.post('/subject-offerings', response_model=SubjectOfferingOut)
@router.post('/subject-versions', response_model=SubjectOfferingOut)
def create_subject_offering(payload: SubjectOfferingCreate, db: Session = Depends(get_db), user: UserContext = Depends(require_permission('manage_settings'))):
    try:
        item = VersionedQuestionBankService(db).create_subject_offering(**payload.model_dump(), actor=user.user_id)
        log_audit(db, action='question_bank.subject_offering.create', status='success', message='Tạo phiên bản môn thành công', user=user, target_type='subject_offering', target_id=item.id)
        return item
    except Exception as exc:
        log_audit(db, action='question_bank.subject_offering.create', status='failed', error_type=AuditErrorType.VALIDATION_ERROR, message=str(exc), user=user, target_type='subject_offering')
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get('/chapters', response_model=list[ChapterOut])
def list_chapters(subject_id: str | None = None, subject_offering_id: str | None = None, db: Session = Depends(get_db), user: UserContext = Depends(require_permission('view_questions'))):
    query = db.query(SubjectChapter)
    if subject_id:
        query = query.filter(SubjectChapter.subject_id == subject_id)
    if subject_offering_id:
        query = query.filter(SubjectChapter.subject_offering_id == subject_offering_id)
    return query.order_by(SubjectChapter.sort_order.asc(), SubjectChapter.chapter_no.asc()).all()


@router.post('/chapters', response_model=ChapterOut)
def create_chapter(payload: ChapterCreate, db: Session = Depends(get_db), user: UserContext = Depends(require_permission('manage_settings'))):
    try:
        item = VersionedQuestionBankService(db).create_chapter(**payload.model_dump())
        log_audit(db, action='question_bank.chapter.create', status='success', message='Tạo chapter/bài học thành công', user=user, target_type='chapter', target_id=item.id)
        return item
    except Exception as exc:
        log_audit(db, action='question_bank.chapter.create', status='failed', error_type=AuditErrorType.VALIDATION_ERROR, message=str(exc), user=user, target_type='chapter')
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get('/bank-versions', response_model=list[BankVersionOut])
def list_bank_versions(chapter_id: str | None = None, subject_id: str | None = None, subject_offering_id: str | None = None, db: Session = Depends(get_db), user: UserContext = Depends(require_permission('view_questions'))):
    query = db.query(QuestionBankVersion)
    if chapter_id:
        query = query.filter(QuestionBankVersion.chapter_id == chapter_id)
    if subject_id:
        query = query.filter(QuestionBankVersion.subject_id == subject_id)
    if subject_offering_id:
        query = query.filter(QuestionBankVersion.subject_offering_id == subject_offering_id)
    return query.order_by(QuestionBankVersion.created_at.desc()).all()


@router.post('/bank-versions', response_model=BankVersionOut)
def create_bank_version(payload: BankVersionCreate, db: Session = Depends(get_db), user: UserContext = Depends(require_permission('edit_questions'))):
    try:
        item = VersionedQuestionBankService(db).create_bank_version(**payload.model_dump(), actor=user.user_id)
        log_audit(db, action='question_bank.version.create', status='success', message='Tạo phiên bản ngân hàng câu hỏi thành công', user=user, target_type='bank_version', target_id=item.id)
        return item
    except Exception as exc:
        log_audit(db, action='question_bank.version.create', status='failed', error_type=AuditErrorType.VALIDATION_ERROR, message=str(exc), user=user, target_type='bank_version')
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get('/material-versions', response_model=list[MaterialVersionOut])
def list_material_versions(bank_version_id: str | None = None, db: Session = Depends(get_db), user: UserContext = Depends(require_permission('view_questions'))):
    query = db.query(LearningMaterialVersion)
    if bank_version_id:
        query = query.filter(LearningMaterialVersion.bank_version_id == bank_version_id)
    return query.order_by(LearningMaterialVersion.created_at.desc()).all()


@router.post('/material-versions', response_model=MaterialVersionOut)
def create_material_version(payload: MaterialVersionCreate, db: Session = Depends(get_db), user: UserContext = Depends(require_permission('edit_questions'))):
    try:
        item = VersionedQuestionBankService(db).create_material_version(**payload.model_dump(), actor=user.user_id)
        log_audit(db, action='question_bank.material_version.create', status='success', message='Tạo phiên bản tài liệu thành công', user=user, target_type='material_version', target_id=item.id)
        return item
    except Exception as exc:
        log_audit(db, action='question_bank.material_version.create', status='failed', error_type=AuditErrorType.VALIDATION_ERROR, message=str(exc), user=user, target_type='material_version')
        raise HTTPException(status_code=400, detail=str(exc)) from exc






@router.delete('/material-versions/{material_version_id}', response_model=MaterialDeleteOut)
def delete_material_version(material_version_id: str, db: Session = Depends(get_db), user: UserContext = Depends(require_permission('edit_questions'))):
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


@router.get('/bank-versions/{bank_version_id}/material-chunks', response_model=list[MaterialChunkOut])
def list_bank_material_chunks(bank_version_id: str, material_version_id: str | None = None, db: Session = Depends(get_db), user: UserContext = Depends(require_permission('view_questions'))):
    query = db.query(MaterialChunk).filter(MaterialChunk.bank_version_id == bank_version_id)
    if material_version_id:
        query = query.filter(MaterialChunk.material_version_id == material_version_id)
    return query.order_by(MaterialChunk.material_version_id.asc(), MaterialChunk.chunk_index.asc()).all()


@router.post('/bank-versions/{bank_version_id}/generate/preview', response_model=BankGeneratePreviewOut)
async def preview_generate_questions_from_bank_version(bank_version_id: str, payload: BankGenerateRequest, db: Session = Depends(get_db), user: UserContext = Depends(require_permission('estimate_cost'))):
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


@router.get('/bank-versions/{bank_version_id}/questions', response_model=list[BankVersionQuestionOut])
def list_bank_version_questions(bank_version_id: str, status_filter: str | None = None, limit: int = 100, db: Session = Depends(get_db), user: UserContext = Depends(require_permission('view_questions'))):
    query = db.query(Question).filter(Question.bank_version_id == bank_version_id)
    if status_filter:
        query = query.filter(Question.status == status_filter)
    return query.order_by(Question.created_at.desc()).limit(min(max(limit, 1), 500)).all()



@router.post('/bank-versions/{bank_version_id}/diff/preview', response_model=BankVersionDiffPreviewOut)
def preview_bank_version_diff(bank_version_id: str, payload: BankVersionDiffPreviewRequest, db: Session = Depends(get_db), user: UserContext = Depends(require_permission('view_questions'))):
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
    try:
        result = VersionedQuestionBankService(db).mark_document_diff_resolved(bank_version_id=bank_version_id, note=payload.note, actor=user.user_id)
        log_audit(db, action='question_bank.version.diff.mark_resolved', status='success', message=result.get('message', ''), user=user, target_type='bank_version', target_id=bank_version_id)
        return result
    except Exception as exc:
        log_audit(db, action='question_bank.version.diff.mark_resolved', status='failed', error_type=AuditErrorType.VALIDATION_ERROR, message=str(exc), user=user, target_type='bank_version', target_id=bank_version_id)
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get('/bank-versions/{bank_version_id}/release/readiness', response_model=BankReleaseReadinessOut)
def bank_release_readiness(bank_version_id: str, db: Session = Depends(get_db), user: UserContext = Depends(require_permission('view_questions'))):
    return VersionedQuestionBankService(db).release_readiness(bank_version_id=bank_version_id)


@router.get('/releases', response_model=list[BankReleaseOut])
def list_releases(bank_version_id: str | None = None, chapter_id: str | None = None, db: Session = Depends(get_db), user: UserContext = Depends(require_permission('view_questions'))):
    query = db.query(QuestionBankRelease)
    if bank_version_id:
        query = query.filter(QuestionBankRelease.bank_version_id == bank_version_id)
    if chapter_id:
        query = query.filter(QuestionBankRelease.chapter_id == chapter_id)
    return query.order_by(QuestionBankRelease.created_at.desc()).all()


@router.post('/releases', response_model=BankReleaseOut)
def create_release(payload: BankReleaseCreate, db: Session = Depends(get_db), user: UserContext = Depends(require_permission('publish_questions'))):
    try:
        item = VersionedQuestionBankService(db).create_release(**payload.model_dump(), actor=user.user_id)
        log_audit(db, action='question_bank.release.create', status='success', message='Tạo Bank Release thành công; 1 release = 1 Open edX Library', user=user, target_type='bank_release', target_id=item.id, metadata={'openedx_library_key': item.openedx_library_key})
        return item
    except Exception as exc:
        log_audit(db, action='question_bank.release.create', status='failed', error_type=AuditErrorType.VALIDATION_ERROR, message=str(exc), user=user, target_type='bank_release')
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post('/releases/{release_id}/publish-openedx', response_model=BankReleasePublishOut)
async def publish_release_to_openedx(release_id: str, payload: BankReleasePublishRequest, db: Session = Depends(get_db), user: UserContext = Depends(require_permission('publish_questions'))):
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


@router.get('/course-mappings', response_model=list[CourseMappingOut])
def list_course_mappings(subject_id: str | None = None, db: Session = Depends(get_db), user: UserContext = Depends(require_permission('view_questions'))):
    query = db.query(EdxCourseMapping)
    if subject_id:
        query = query.filter(EdxCourseMapping.subject_id == subject_id)
    return query.order_by(EdxCourseMapping.created_at.desc()).all()


@router.post('/course-mappings/validate', response_model=MappingValidationOut)
def validate_course_mapping(payload: CourseMappingValidateRequest, db: Session = Depends(get_db), user: UserContext = Depends(require_permission('publish_questions'))):
    result = VersionedQuestionBankService(db).validate_course_mapping(**payload.model_dump())
    log_audit(db, action='question_bank.course_mapping.validate', status='success' if result.get('ok') else 'failed', error_type=None if result.get('ok') else AuditErrorType.VALIDATION_ERROR, message=result.get('message', ''), user=user, course_id=payload.openedx_course_id, target_type='course_mapping', metadata=result)
    return result


@router.post('/course-mappings', response_model=CourseMappingOut)
def create_course_mapping(payload: CourseMappingCreate, db: Session = Depends(get_db), user: UserContext = Depends(require_permission('publish_questions'))):
    try:
        item = VersionedQuestionBankService(db).create_course_mapping(**payload.model_dump(), actor=user.user_id)
        log_audit(db, action='question_bank.course_mapping.create', status='success', message='Map khóa học Open edX vào môn học thành công', user=user, course_id=item.openedx_course_id, target_type='course_mapping', target_id=item.id)
        return item
    except Exception as exc:
        log_audit(db, action='question_bank.course_mapping.create', status='failed', error_type=AuditErrorType.VALIDATION_ERROR, message=str(exc), user=user, target_type='course_mapping')
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get('/course-chapter-mappings', response_model=list[CourseChapterMappingOut])
def list_course_chapter_mappings(course_mapping_id: str | None = None, db: Session = Depends(get_db), user: UserContext = Depends(require_permission('view_questions'))):
    query = db.query(EdxCourseChapterMapping)
    if course_mapping_id:
        query = query.filter(EdxCourseChapterMapping.course_mapping_id == course_mapping_id)
    return query.order_by(EdxCourseChapterMapping.created_at.desc()).all()


@router.post('/course-chapter-mappings/validate', response_model=MappingValidationOut)
def validate_course_chapter_mapping(payload: CourseChapterMappingValidateRequest, db: Session = Depends(get_db), user: UserContext = Depends(require_permission('publish_questions'))):
    result = VersionedQuestionBankService(db).validate_course_chapter_mapping(**payload.model_dump())
    log_audit(db, action='question_bank.course_chapter_mapping.validate', status='success' if result.get('ok') else 'failed', error_type=None if result.get('ok') else AuditErrorType.VALIDATION_ERROR, message=result.get('message', ''), user=user, target_type='course_chapter_mapping', metadata=result)
    return result


@router.post('/course-chapter-mappings', response_model=CourseChapterMappingOut)
def create_course_chapter_mapping(payload: CourseChapterMappingCreate, db: Session = Depends(get_db), user: UserContext = Depends(require_permission('publish_questions'))):
    try:
        item = VersionedQuestionBankService(db).create_course_chapter_mapping(**payload.model_dump())
        log_audit(db, action='question_bank.course_chapter_mapping.create', status='success', message='Map chapter Open edX vào Bank Release thành công', user=user, target_type='course_chapter_mapping', target_id=item.id)
        return item
    except Exception as exc:
        log_audit(db, action='question_bank.course_chapter_mapping.create', status='failed', error_type=AuditErrorType.VALIDATION_ERROR, message=str(exc), user=user, target_type='course_chapter_mapping')
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get('/course-quiz-instances', response_model=list[CourseQuizInstanceOut])
def list_course_quiz_instances(openedx_course_id: str | None = None, bank_release_id: str | None = None, limit: int = 100, db: Session = Depends(get_db), user: UserContext = Depends(require_permission('view_questions'))):
    return VersionedQuestionBankService(db).list_course_quiz_instances(openedx_course_id=openedx_course_id, bank_release_id=bank_release_id, limit=limit)


@router.post('/course-quiz-instances/{instance_id}/rollback', response_model=CourseQuizRollbackOut)
async def rollback_course_quiz_instance(instance_id: str, payload: CourseQuizRollbackRequest, db: Session = Depends(get_db), user: UserContext = Depends(require_permission('publish_questions'))):
    try:
        result = await VersionedQuestionBankService(db).rollback_course_quiz_instance(instance_id=instance_id, mode=payload.mode, note=payload.note, actor=user.user_id)
        log_audit(db, action='question_bank.course_quiz.rollback', status='success', message=result.get('message', ''), user=user, target_type='course_quiz_instance', target_id=instance_id, metadata=result)
        return result
    except Exception as exc:
        log_audit(db, action='question_bank.course_quiz.rollback', status='failed', error_type=AuditErrorType.EXTERNAL_SERVICE_ERROR, message=str(exc), user=user, target_type='course_quiz_instance', target_id=instance_id)
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get('/quiz-blueprints', response_model=list[QuizBlueprintOut])
def list_quiz_blueprints(chapter_id: str | None = None, db: Session = Depends(get_db), user: UserContext = Depends(require_permission('view_questions'))):
    query = db.query(QuizBlueprint)
    if chapter_id:
        query = query.filter(QuizBlueprint.chapter_id == chapter_id)
    return query.order_by(QuizBlueprint.created_at.desc()).all()


@router.post('/quiz-blueprints', response_model=QuizBlueprintOut)
def create_quiz_blueprint(payload: QuizBlueprintCreate, db: Session = Depends(get_db), user: UserContext = Depends(require_permission('publish_questions'))):
    try:
        item = VersionedQuestionBankService(db).create_quiz_blueprint(**payload.model_dump())
        log_audit(db, action='question_bank.quiz_blueprint.create', status='success', message='Tạo blueprint quiz thành công', user=user, target_type='quiz_blueprint', target_id=item.id)
        return item
    except Exception as exc:
        log_audit(db, action='question_bank.quiz_blueprint.create', status='failed', error_type=AuditErrorType.VALIDATION_ERROR, message=str(exc), user=user, target_type='quiz_blueprint')
        raise HTTPException(status_code=400, detail=str(exc)) from exc
