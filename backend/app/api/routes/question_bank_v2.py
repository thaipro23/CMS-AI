from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.rbac import UserContext, require_permission
from app.db.session import get_db
from app.models.question_bank import (
    Department,
    EdxCourseChapterMapping,
    EdxCourseMapping,
    LearningMaterialVersion,
    QuestionBankRelease,
    QuestionBankVersion,
    QuizBlueprint,
    Subject,
    SubjectChapter,
)
from app.schemas.question_bank import (
    BankReleaseCreate,
    BankReleaseOut,
    BankSummaryOut,
    BankVersionCreate,
    BankVersionOut,
    ChapterCreate,
    ChapterOut,
    CourseChapterMappingCreate,
    CourseChapterMappingOut,
    CourseMappingCreate,
    CourseMappingOut,
    DepartmentCreate,
    DepartmentOut,
    MaterialVersionCreate,
    MaterialVersionOut,
    QuizBlueprintCreate,
    QuizBlueprintOut,
    SubjectCreate,
    SubjectOut,
)
from app.services.audit_log import AuditErrorType, log_audit
from app.services.question_bank_service import VersionedQuestionBankService

router = APIRouter()


@router.get('/summary', response_model=BankSummaryOut)
def summary(db: Session = Depends(get_db), user: UserContext = Depends(require_permission('view_questions'))):
    return VersionedQuestionBankService(db).summary()


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


@router.get('/chapters', response_model=list[ChapterOut])
def list_chapters(subject_id: str | None = None, db: Session = Depends(get_db), user: UserContext = Depends(require_permission('view_questions'))):
    query = db.query(SubjectChapter)
    if subject_id:
        query = query.filter(SubjectChapter.subject_id == subject_id)
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
def list_bank_versions(chapter_id: str | None = None, subject_id: str | None = None, db: Session = Depends(get_db), user: UserContext = Depends(require_permission('view_questions'))):
    query = db.query(QuestionBankVersion)
    if chapter_id:
        query = query.filter(QuestionBankVersion.chapter_id == chapter_id)
    if subject_id:
        query = query.filter(QuestionBankVersion.subject_id == subject_id)
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


@router.get('/course-mappings', response_model=list[CourseMappingOut])
def list_course_mappings(subject_id: str | None = None, db: Session = Depends(get_db), user: UserContext = Depends(require_permission('view_questions'))):
    query = db.query(EdxCourseMapping)
    if subject_id:
        query = query.filter(EdxCourseMapping.subject_id == subject_id)
    return query.order_by(EdxCourseMapping.created_at.desc()).all()


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


@router.post('/course-chapter-mappings', response_model=CourseChapterMappingOut)
def create_course_chapter_mapping(payload: CourseChapterMappingCreate, db: Session = Depends(get_db), user: UserContext = Depends(require_permission('publish_questions'))):
    try:
        item = VersionedQuestionBankService(db).create_course_chapter_mapping(**payload.model_dump())
        log_audit(db, action='question_bank.course_chapter_mapping.create', status='success', message='Map chapter Open edX vào Bank Release thành công', user=user, target_type='course_chapter_mapping', target_id=item.id)
        return item
    except Exception as exc:
        log_audit(db, action='question_bank.course_chapter_mapping.create', status='failed', error_type=AuditErrorType.VALIDATION_ERROR, message=str(exc), user=user, target_type='course_chapter_mapping')
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
