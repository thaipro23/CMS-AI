from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import StreamingResponse
from io import BytesIO
from typing import Any
from sqlalchemy.orm import Session
from sqlalchemy import func, or_
from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

from app.core.rbac import UserContext, get_user_context, require_permission
from app.db.session import get_db
from app.models.academic import (
    AcademicCampus,
    AcademicClass,
    AcademicClassStudent,
    AcademicClassSyncJob,
    AcademicStudent,
    AcademicSubject,
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
    AcademicClassSyncJobOut,
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
    AcademicEnrollmentSyncIn,
    AcademicEnrollmentSyncOut,
    AcademicFullCmsSyncIn,
    AcademicFullCmsSyncOut,
    AcademicLearningSyncIn,
    AcademicLearningSyncOut,
    AcademicLearningSummaryOut,
    AcademicImportResultOut,
    AcademicMappingResolveOut,
    AcademicMappingSummaryOut,
    AcademicManualMappingImportIn,
    AcademicManualMappingImportOut,
    AcademicResolveClassUsersIn,
    AcademicStudentListOut,
    AcademicSubjectOut,
    AcademicSubjectManagementListOut,
    AcademicSubjectCourseAutoMapOut,
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
from app.core.json_safe import json_safe_value


def _safe_error_message(message: str = 'academic_operation_failed') -> dict[str, str]:
    return {
        'code': message,
        'message': 'Không thể hoàn tất thao tác học vụ. Vui lòng thử lại hoặc liên hệ quản trị.',
    }

router = APIRouter()


def _excel_value(value: Any) -> Any:
    if value is None:
        return ''
    if isinstance(value, (list, tuple, set)):
        return ', '.join(str(item) for item in value if item is not None)
    return value


def _grade10(value: Any) -> float | None:
    if value is None or value == '':
        return None
    try:
        number = float(value)
    except Exception:
        return None
    if 0 <= number <= 1:
        number *= 100.0
    return round(max(0.0, min(100.0, number)) / 10.0, 2)


def _component_key(item: dict[str, Any]) -> str:
    return str(item.get('key') or item.get('name') or '').strip()


def _component_name(item: dict[str, Any]) -> str:
    return str(item.get('name') or item.get('key') or 'Đầu điểm').strip()


def _component_score_text(item: dict[str, Any] | None) -> Any:
    if not item:
        return ''
    if item.get('percent') is not None:
        return _grade10(item.get('percent'))
    try:
        earned = float(item.get('earned'))
        possible = float(item.get('possible'))
        if possible > 0:
            return round(max(0.0, min(10.0, earned / possible * 10.0)), 2)
    except Exception:
        pass
    return ''


def _training_component_columns(report: dict[str, Any]) -> list[dict[str, str]]:
    columns: list[dict[str, str]] = []
    seen: set[str] = set()
    for item in report.get('items') or []:
        for cls in item.get('classes') or []:
            for score in cls.get('learning_component_summaries') or []:
                if not isinstance(score, dict):
                    continue
                key = _component_key(score)
                name = _component_name(score)
                dedupe = (key or name).lower()
                if not dedupe or dedupe in seen:
                    continue
                seen.add(dedupe)
                columns.append({'key': key or name, 'name': name})
    columns.sort(key=lambda item: str(item.get('name') or item.get('key') or '').lower())
    return columns


def _setup_sheet(ws, headers: list[str], widths: list[int] | None = None) -> None:
    header_fill = PatternFill('solid', fgColor='111827')
    for col, name in enumerate(headers, 1):
        cell = ws.cell(row=1, column=col, value=name)
        cell.font = Font(color='FFFFFF', bold=True)
        cell.fill = header_fill
        cell.alignment = Alignment(horizontal='center', vertical='center', wrap_text=True)
    ws.freeze_panes = 'A2'
    for idx, width in enumerate(widths or [], 1):
        ws.column_dimensions[get_column_letter(idx)].width = width


def _append_row(ws, values: list[Any]) -> None:
    ws.append([_excel_value(value) for value in values])


def _build_training_teacher_report_xlsx(report: dict[str, Any]) -> bytes:
    wb = Workbook()
    ws = wb.active
    ws.title = 'TongQuanGV'
    overview_headers = [
        'Hệ', 'Cơ sở', 'Giảng viên', 'Username', 'Email', 'Số môn', 'Môn', 'Số lớp',
        'SV lượt lớp', 'SV riêng biệt', 'Đã đồng bộ CMS', 'Đã enroll', 'Có hoạt động',
        'Course completion TB (%)', 'Điểm tổng TB (hệ 10)', 'Lớp chưa map Course',
        'SV rủi ro', 'SV trễ deadline', 'Lượt quiz trễ', 'Chưa đồng bộ CMS', 'Chưa enroll', 'Chưa học', 'Tiến độ thấp',
        'Điểm thấp', 'Lỗi đồng bộ', 'Cập nhật gần nhất', 'Cảnh báo'
    ]
    _setup_sheet(ws, overview_headers, [12, 12, 28, 24, 30, 10, 28, 10, 12, 14, 16, 12, 12, 20, 18, 18, 12, 16, 14, 18, 12, 12, 14, 12, 12, 22, 48])
    for item in report.get('items') or []:
        statuses = item.get('status_counts') or {}
        _append_row(ws, [
            item.get('branch'), item.get('campus'), item.get('teacher_name'), item.get('teacher_username'), item.get('teacher_email'),
            item.get('subject_count'), item.get('subject_codes'), item.get('class_count'), item.get('student_count'), item.get('unique_student_count'),
            item.get('cms_synced_count'), item.get('learning_enrolled_count'), item.get('learning_active_count'),
            item.get('learning_avg_progress_percent'), item.get('learning_avg_grade_10'), item.get('classes_without_course_count'),
            item.get('risk_student_count'), item.get('deadline_late_student_count'), item.get('deadline_late_quiz_count'), statuses.get('cms_not_synced'), statuses.get('not_enrolled'), statuses.get('no_activity'),
            statuses.get('low_progress'), statuses.get('low_grade'), statuses.get('sync_error'), item.get('last_synced_at'), item.get('learning_alerts'),
        ])

    class_ws = wb.create_sheet('ChiTietLop')
    component_columns = _training_component_columns(report)
    class_headers = [
        'Giảng viên', 'Username GV', 'Hệ', 'Cơ sở', 'Học kỳ', 'Block', 'Môn', 'Tên môn',
        'Lớp', 'Tên lớp', 'Course CMS', 'Nguồn mapping', 'SV', 'Đã đồng bộ CMS', 'Đã enroll',
        'Có hoạt động', 'Course completion TB (%)', 'Điểm tổng TB (hệ 10)',
        *[column['name'] for column in component_columns],
        'Số Quiz', 'Quiz đã đến hạn',
        'SV trễ deadline', 'Lượt quiz trễ', 'Đợt quiz kế tiếp', 'Ngày làm quiz kế tiếp', 'Deadline kế tiếp',
        'Chưa đồng bộ CMS', 'Chưa enroll', 'Chưa học', 'Tiến độ thấp', 'Điểm thấp', 'Lỗi đồng bộ', 'Cập nhật gần nhất', 'Cảnh báo'
    ]
    _setup_sheet(class_ws, class_headers, [28, 22, 10, 12, 18, 16, 12, 30, 16, 26, 38, 20, 8, 16, 12, 12, 20, 18, *([12] * len(component_columns)), 10, 14, 16, 14, 18, 18, 18, 18, 12, 12, 14, 12, 12, 22, 48])
    for item in report.get('items') or []:
        for cls in item.get('classes') or []:
            statuses = cls.get('status_counts') or {}
            _append_row(class_ws, [
                item.get('teacher_name'), item.get('teacher_username'), cls.get('branch'), cls.get('campus'), cls.get('term_name'), cls.get('block_name'),
                cls.get('subject_code'), cls.get('subject_name'), cls.get('class_code'), cls.get('class_name'), cls.get('openedx_course_id'), cls.get('openedx_mapping_source'),
                cls.get('student_count'), cls.get('cms_synced_count'), cls.get('learning_enrolled_count'), cls.get('learning_active_count'),
                cls.get('learning_avg_progress_percent'), cls.get('learning_avg_grade_10'),
                *[
                    _component_score_text(next((score for score in (cls.get('learning_component_summaries') or []) if isinstance(score, dict) and (_component_key(score) == column['key'] or _component_name(score) == column['name'])), None))
                    for column in component_columns
                ],
                cls.get('deadline_quiz_count'), cls.get('deadline_due_quiz_count'),
                cls.get('deadline_late_student_count'), cls.get('deadline_late_quiz_count'), cls.get('deadline_next_quiz_label'), cls.get('deadline_next_quiz_from_date'), cls.get('deadline_next_quiz_due_date'),
                statuses.get('cms_not_synced'), statuses.get('not_enrolled'), statuses.get('no_activity'), statuses.get('low_progress'), statuses.get('low_grade'), statuses.get('sync_error'), cls.get('learning_last_synced_at'), cls.get('learning_alerts'),
            ])

    watch_ws = wb.create_sheet('SinhVienCanTheoDoi')
    watch_headers = [
        'Giảng viên', 'Username GV', 'Học kỳ', 'Block', 'Môn', 'Tên môn', 'Lớp', 'Mã SV',
        'Username', 'Họ tên', 'Email', 'Username CMS', 'Trạng thái', 'Enrollment',
        'Course completion (%)', 'Điểm tổng (hệ 10)', 'Quiz đã đến hạn', 'Quiz đã hoàn thành đúng hạn',
        'Quiz trễ', 'Danh sách quiz trễ', 'Đợt quiz kế tiếp', 'Deadline kế tiếp', 'Hoạt động cuối', 'Cập nhật cuối'
    ]
    _setup_sheet(watch_ws, watch_headers, [28, 22, 18, 16, 12, 30, 16, 14, 22, 28, 32, 22, 20, 16, 22, 18, 14, 20, 12, 34, 18, 18, 22, 22])
    for row in report.get('student_watch_rows') or []:
        _append_row(watch_ws, [
            row.get('teacher_name'), row.get('teacher_username'), row.get('term_name'), row.get('block_name'), row.get('subject_code'), row.get('subject_name'), row.get('class_code'),
            row.get('student_code'), row.get('student_username'), row.get('student_name'), row.get('student_email'), row.get('openedx_username'), row.get('status_label'),
            row.get('enrollment_status'), row.get('progress_percent'), row.get('grade_10'), row.get('deadline_due_quiz_count'), row.get('deadline_completed_due_quiz_count'),
            row.get('deadline_late_quiz_count'), row.get('deadline_late_quizzes'), row.get('deadline_next_quiz_label'), row.get('deadline_next_quiz_due_date'), row.get('last_activity_at'), row.get('last_synced_at'),
        ])

    guide = wb.create_sheet('HuongDan')
    guide['A1'] = 'Báo cáo quản lý đào tạo theo giảng viên'
    guide['A1'].font = Font(size=15, bold=True)
    notes = [
        'Mỗi dòng TongQuanGV là một giảng viên theo bộ lọc trên AI Server.',
        'SV lượt lớp tính theo class-student enrollment; một sinh viên học nhiều lớp có thể được tính nhiều lần.',
        'SV riêng biệt là số sinh viên không trùng trong phạm vi các lớp của giảng viên đó.',
        'Course completion lấy từ progress CMS/Open edX; Điểm tổng được quy đổi từ phần trăm sang hệ 10.',
        'SinhVienCanTheoDoi chỉ liệt kê sinh viên có trạng thái cần xử lý: chưa đồng bộ CMS, chưa enroll, chưa học, tiến độ thấp, điểm thấp, lỗi đồng bộ hoặc trễ deadline quiz.',
        'Deadline quiz được tính theo quy tắc: mỗi block 7 tuần, 6 tuần đầu dành deadline quiz từ Thứ 2 đến Thứ 7, tuần 7 Ôn+Thi; số quiz được chia đều vào 6 tuần và phần dư dồn vào các tuần đầu.',
    ]
    for idx, note in enumerate(notes, 3):
        guide.cell(row=idx, column=1, value=f'- {note}')
    guide.column_dimensions['A'].width = 110

    for sheet in wb.worksheets:
        for row in sheet.iter_rows():
            for cell in row:
                cell.alignment = Alignment(vertical='top', wrap_text=True)
        if sheet.max_row > 1:
            sheet.auto_filter.ref = sheet.dimensions

    raw = BytesIO()
    wb.save(raw)
    return raw.getvalue()


def _enqueue_class_sync_job(
    *,
    db: Session,
    user: UserContext,
    class_id: str,
    job_type: str,
    force: bool,
    limit: int,
    mode: str | None = None,
    auto_map_course: bool | None = None,
    sync_learning: bool | None = None,
) -> AcademicClassSyncJob:
    service = AcademicService(db)
    service.assert_can_access_class(user, class_id)
    clean_limit = max(1, min(500, int(limit or 500)))

    # Class sync jobs mutate the same CMS/Open edX and snapshot rows. Returning
    # the existing active job makes the operation idempotent across refresh/F5
    # and prevents users from accidentally enqueueing duplicate jobs.
    existing_job = (
        db.query(AcademicClassSyncJob)
        .filter(
            AcademicClassSyncJob.class_id == class_id,
            AcademicClassSyncJob.status.in_(['queued', 'running']),
        )
        .order_by(AcademicClassSyncJob.created_at.desc())
        .first()
    )
    if existing_job:
        return existing_job

    job = AcademicClassSyncJob(
        job_type=job_type,
        status='queued',
        class_id=class_id,
        requested_by=user.user_id,
        force=bool(force),
        limit=clean_limit,
        mode=mode,
        progress_current=0,
        progress_total=100,
        progress_label='Đang chờ xử lý',
        request_json=json_safe_value({'force': bool(force), 'limit': clean_limit, 'mode': mode, 'auto_map_course': auto_map_course, 'sync_learning': sync_learning}),
        result_json={},
    )
    db.add(job)
    db.commit()
    db.refresh(job)
    from app.worker import academic_class_sync_task
    academic_class_sync_task.delay(job.id)
    return job




def _require_academic_sync_permission(
    user: UserContext = Depends(get_user_context),
    db: Session = Depends(get_db),
) -> UserContext:
    """Allow academic CMS/Open edX mutations only for sync-capable users."""
    if 'sync_course' in user.permissions or 'manage_settings' in user.permissions:
        return user
    try:
        service = BusinessRBACService(db)
        if service.has_any_business_permission(user, 'sync_course') or service.has_any_business_permission(user, 'manage_settings'):
            return user
    except HTTPException:
        raise
    except Exception:
        pass
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail='Bạn không có quyền đồng bộ/thao tác học vụ CMS/Open edX.',
    )

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



@router.get('/training/teachers')
def list_training_teacher_report(
    term_id: str | None = None,
    branch: str | None = None,
    campus: str | None = None,
    search: str | None = None,
    learning_status: str | None = Query(None, description='Lọc giáo viên theo cảnh báo học tập'),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    user: UserContext = Depends(require_permission('view_questions')),
    db: Session = Depends(get_db),
):
    return AcademicService(db).training_teacher_report(
        user,
        term_id=term_id,
        branch=branch,
        campus=campus,
        search=search,
        learning_status=learning_status,
        page=page,
        page_size=page_size,
    )


@router.get('/training/teachers/export')
def export_training_teacher_report(
    term_id: str | None = None,
    branch: str | None = None,
    campus: str | None = None,
    search: str | None = None,
    learning_status: str | None = Query(None, description='Lọc giáo viên theo cảnh báo học tập'),
    user: UserContext = Depends(require_permission('view_questions')),
    db: Session = Depends(get_db),
):
    report = AcademicService(db).training_teacher_report(
        user,
        term_id=term_id,
        branch=branch,
        campus=campus,
        search=search,
        learning_status=learning_status,
        page=1,
        page_size=200,
        include_all=True,
        include_students=True,
    )
    content = _build_training_teacher_report_xlsx(report)
    return StreamingResponse(
        BytesIO(content),
        media_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        headers={'Content-Disposition': 'attachment; filename="training-management-teacher-report.xlsx"'},
    )


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


@router.delete('/terms/{term_id}', response_model=AcademicTermWithBlocksOut)
def delete_academic_term(
    term_id: str,
    user: UserContext = Depends(require_permission('manage_settings')),
    db: Session = Depends(get_db),
):
    _require_academic_admin(db, user)
    service = AcademicService(db)
    term = db.query(AcademicTerm).filter(AcademicTerm.id == term_id).first()
    if not term:
        raise HTTPException(status_code=404, detail='Không tìm thấy học kỳ')
    term.active = False
    meta = dict(term.metadata_json or {})
    meta.update({'deleted_from_ui': True})
    term.metadata_json = meta
    blocks = service.list_blocks(term_id=term.id, active=None)
    for block in blocks:
        block.active = False
    db.commit()
    db.refresh(term)
    log_audit(db, action='academic.term.delete', status='success', message='Đã xóa/ẩn học kỳ và block', user=user, target_type='academic_term', target_id=term.id, metadata={'term_code': term.term_code, 'branch': term.branch})
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
    campus: str | None = None,
    branch: str | None = None,
    search: str | None = None,
    learning_status: str | None = Query(None, description='Lọc trạng thái học tập/cảnh báo'),
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
        campus=campus,
        branch=branch,
        search=search,
        learning_status=learning_status,
        page=page,
        page_size=page_size,
    )



@router.get('/teacher/subjects', response_model=AcademicSubjectManagementListOut)
def list_teacher_subjects(
    term_id: str | None = None,
    branch: str | None = None,
    campus: str | None = None,
    search: str | None = None,
    learning_status: str | None = Query(None, description='Lọc trạng thái học tập/cảnh báo'),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    user: UserContext = Depends(require_permission('view_questions')),
    db: Session = Depends(get_db),
):
    return AcademicService(db).list_teacher_subjects(
        user, term_id=term_id, branch=branch, campus=campus, search=search, learning_status=learning_status, page=page, page_size=page_size
    )


@router.get('/subjects/{subject_id}/classes', response_model=AcademicClassListOut)
def list_subject_classes(
    subject_id: str,
    term_id: str | None = None,
    block_id: str | None = None,
    campus: str | None = None,
    branch: str | None = None,
    search: str | None = None,
    learning_status: str | None = Query(None, description='Lọc trạng thái học tập/cảnh báo'),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    user: UserContext = Depends(require_permission('view_questions')),
    db: Session = Depends(get_db),
):
    service = AcademicService(db)
    service.assert_can_access_subject(user, subject_id)
    return service.list_teacher_classes(
        user, term_id=term_id, block_id=block_id, subject_id=subject_id, campus=campus, branch=branch, search=search, learning_status=learning_status, page=page, page_size=page_size
    )


@router.post('/subjects/{subject_id}/course-mapping/auto', response_model=AcademicSubjectCourseAutoMapOut)
def auto_map_subject_course(
    subject_id: str,
    term_id: str = Query(...),
    branch: str | None = Query(None),
    user: UserContext = Depends(_require_academic_sync_permission),
    db: Session = Depends(get_db),
):
    result = AcademicService(db).auto_map_subject_course(user, term_id=term_id, subject_id=subject_id, branch=branch)
    log_audit(
        db,
        action='academic.subject_course_mapping.auto',
        status='success' if result.get('ok') else 'failed',
        message=result.get('message', ''),
        user=user,
        course_id=(result.get('mapping') or {}).get('openedx_course_id') if isinstance(result.get('mapping'), dict) else None,
        target_type='academic_subject',
        target_id=subject_id,
        metadata={'term_id': term_id, 'branch': branch, 'status': result.get('status')},
    )
    return result


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
        raise HTTPException(status_code=400, detail=_safe_error_message('academic_validation_failed')) from exc


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
        raise HTTPException(status_code=400, detail=_safe_error_message('academic_validation_failed')) from exc


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
    learning_status: str | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    user: UserContext = Depends(require_permission('view_questions')),
    db: Session = Depends(get_db),
):
    return AcademicService(db).list_class_students(user, class_id, search=search, learning_status=learning_status, page=page, page_size=page_size)


@router.get('/classes/{class_id}/mapping-summary', response_model=AcademicMappingSummaryOut)
def get_class_mapping_summary(
    class_id: str,
    user: UserContext = Depends(require_permission('view_questions')),
    db: Session = Depends(get_db),
):
    return AcademicService(db).mapping_summary_for_class(user, class_id)


@router.get('/classes/{class_id}/learning-summary', response_model=AcademicLearningSummaryOut)
def get_class_learning_summary(
    class_id: str,
    user: UserContext = Depends(require_permission('view_questions')),
    db: Session = Depends(get_db),
):
    return AcademicService(db).learning_summary_for_class(user, class_id)




@router.post('/classes/{class_id}/cms-sync-check/jobs', response_model=AcademicClassSyncJobOut)
def enqueue_class_cms_sync_check(
    class_id: str,
    payload: AcademicResolveClassUsersIn,
    user: UserContext = Depends(_require_academic_sync_permission),
    db: Session = Depends(get_db),
):
    return _enqueue_class_sync_job(db=db, user=user, class_id=class_id, job_type='cms_sync_check', force=payload.force, limit=payload.limit)


@router.post('/classes/{class_id}/cms-enrollment-sync/jobs', response_model=AcademicClassSyncJobOut)
def enqueue_class_cms_enrollment_sync(
    class_id: str,
    payload: AcademicEnrollmentSyncIn,
    user: UserContext = Depends(_require_academic_sync_permission),
    db: Session = Depends(get_db),
):
    return _enqueue_class_sync_job(db=db, user=user, class_id=class_id, job_type='cms_enrollment_sync', force=payload.force, limit=payload.limit, mode=payload.mode)


@router.post('/classes/{class_id}/learning-sync/jobs', response_model=AcademicClassSyncJobOut)
def enqueue_class_learning_sync(
    class_id: str,
    payload: AcademicLearningSyncIn,
    user: UserContext = Depends(_require_academic_sync_permission),
    db: Session = Depends(get_db),
):
    return _enqueue_class_sync_job(db=db, user=user, class_id=class_id, job_type='learning_sync', force=payload.force, limit=payload.limit)


@router.post('/classes/{class_id}/full-cms-sync/jobs', response_model=AcademicClassSyncJobOut)
def enqueue_class_full_cms_sync(
    class_id: str,
    payload: AcademicFullCmsSyncIn,
    user: UserContext = Depends(_require_academic_sync_permission),
    db: Session = Depends(get_db),
):
    return _enqueue_class_sync_job(
        db=db,
        user=user,
        class_id=class_id,
        job_type='full_cms_sync',
        force=payload.force,
        limit=payload.limit,
        mode=payload.mode,
        auto_map_course=payload.auto_map_course,
        sync_learning=payload.sync_learning,
    )


@router.get('/classes/{class_id}/sync-jobs/{job_id}', response_model=AcademicClassSyncJobOut)
def get_class_sync_job(
    class_id: str,
    job_id: str,
    user: UserContext = Depends(require_permission('view_questions')),
    db: Session = Depends(get_db),
):
    AcademicService(db).assert_can_access_class(user, class_id)
    job = db.query(AcademicClassSyncJob).filter(AcademicClassSyncJob.id == job_id, AcademicClassSyncJob.class_id == class_id).first()
    if not job:
        raise HTTPException(status_code=404, detail='Không tìm thấy job đồng bộ lớp')
    return job


@router.get('/classes/{class_id}/sync-jobs', response_model=list[AcademicClassSyncJobOut])
def list_class_sync_jobs(
    class_id: str,
    limit: int = Query(10, ge=1, le=50),
    user: UserContext = Depends(require_permission('view_questions')),
    db: Session = Depends(get_db),
):
    AcademicService(db).assert_can_access_class(user, class_id)
    return db.query(AcademicClassSyncJob).filter(AcademicClassSyncJob.class_id == class_id).order_by(AcademicClassSyncJob.created_at.desc()).limit(limit).all()

@router.post('/classes/{class_id}/full-cms-sync', response_model=AcademicFullCmsSyncOut)
def sync_class_full_cms_flow(
    class_id: str,
    payload: AcademicFullCmsSyncIn,
    user: UserContext = Depends(_require_academic_sync_permission),
    db: Session = Depends(get_db),
):
    service = AcademicService(db)
    try:
        result = service.sync_class_full_cms_flow(
            user,
            class_id,
            force=payload.force,
            limit=payload.limit,
            mode=payload.mode,
            auto_map_course=payload.auto_map_course,
            sync_learning=payload.sync_learning,
        )
        log_audit(
            db,
            action='academic.full_cms_sync.class',
            status='success',
            message=result.get('message', 'Đồng bộ full CMS hoàn tất'),
            user=user,
            target_type='academic_class',
            target_id=class_id,
            course_id=result.get('openedx_course_id'),
            metadata={'counts': result.get('counts', {}), 'status': result.get('status')},
        )
        return result
    except HTTPException:
        raise
    except Exception as exc:
        db.rollback()
        log_audit(db, action='academic.full_cms_sync.class', status='failed', error_type=AuditErrorType.EXTERNAL_SERVICE_ERROR, message=str(exc), user=user, target_type='academic_class', target_id=class_id)
        raise HTTPException(status_code=502, detail=_safe_error_message('academic_external_sync_failed')) from exc


@router.post('/classes/{class_id}/cms-enrollment-sync', response_model=AcademicEnrollmentSyncOut)
def sync_class_cms_enrollment(
    class_id: str,
    payload: AcademicEnrollmentSyncIn,
    user: UserContext = Depends(_require_academic_sync_permission),
    db: Session = Depends(get_db),
):
    service = AcademicService(db)
    try:
        result = service.sync_class_course_enrollment(user, class_id, force=payload.force, limit=payload.limit, mode=payload.mode)
        log_audit(
            db,
            action='academic.cms_enrollment_sync.class',
            status='success',
            message='Tự enrollment sinh viên đã đồng bộ CMS vào Course CMS thành công',
            user=user,
            target_type='academic_class',
            target_id=class_id,
            metadata={'counts': result.get('counts', {}), 'updated': result.get('updated', 0), 'openedx_course_id': result.get('openedx_course_id')},
        )
        return result
    except HTTPException:
        raise
    except Exception as exc:
        db.rollback()
        log_audit(
            db,
            action='academic.cms_enrollment_sync.class',
            status='failed',
            error_type=AuditErrorType.EXTERNAL_SERVICE_ERROR,
            message=str(exc),
            user=user,
            target_type='academic_class',
            target_id=class_id,
        )
        raise HTTPException(status_code=502, detail=_safe_error_message('academic_external_sync_failed')) from exc

@router.post('/classes/{class_id}/learning-sync', response_model=AcademicLearningSyncOut)
def sync_class_learning_insight(
    class_id: str,
    payload: AcademicLearningSyncIn,
    user: UserContext = Depends(_require_academic_sync_permission),
    db: Session = Depends(get_db),
):
    service = AcademicService(db)
    try:
        result = service.sync_class_learning_insight(user, class_id, force=payload.force, limit=payload.limit)
        log_audit(
            db,
            action='academic.learning_sync.class',
            status='success',
            message='Cập nhật tiến độ/điểm CMS cho lớp thành công',
            user=user,
            target_type='academic_class',
            target_id=class_id,
            metadata={'counts': result.get('counts', {}), 'updated': result.get('updated', 0), 'openedx_course_id': result.get('openedx_course_id')},
        )
        return result
    except HTTPException:
        raise
    except Exception as exc:
        db.rollback()
        log_audit(
            db,
            action='academic.learning_sync.class',
            status='failed',
            error_type=AuditErrorType.EXTERNAL_SERVICE_ERROR,
            message=str(exc),
            user=user,
            target_type='academic_class',
            target_id=class_id,
        )
        raise HTTPException(status_code=502, detail=_safe_error_message('academic_external_sync_failed')) from exc


def _run_class_cms_sync_check(class_id: str, payload: AcademicResolveClassUsersIn, user: UserContext, db: Session) -> dict:
    service = AcademicService(db)
    try:
        result = service.resolve_class_openedx_users(user, class_id, force=payload.force, limit=payload.limit)
        log_audit(
            db,
            action='academic.cms_sync_check.class',
            status='success',
            message='Kiểm tra đồng bộ CMS theo AP username thành công',
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
            action='academic.cms_sync_check.class',
            status='failed',
            error_type=AuditErrorType.EXTERNAL_SERVICE_ERROR,
            message=str(exc),
            user=user,
            target_type='academic_class',
            target_id=class_id,
        )
        raise HTTPException(status_code=502, detail=_safe_error_message('academic_external_sync_failed')) from exc


@router.post('/classes/{class_id}/cms-sync-check', response_model=AcademicMappingResolveOut)
def check_class_cms_sync(
    class_id: str,
    payload: AcademicResolveClassUsersIn,
    user: UserContext = Depends(_require_academic_sync_permission),
    db: Session = Depends(get_db),
):
    return _run_class_cms_sync_check(class_id, payload, user, db)


@router.post('/classes/{class_id}/resolve-openedx-users', response_model=AcademicMappingResolveOut)
def resolve_class_openedx_users_legacy_alias(
    class_id: str,
    payload: AcademicResolveClassUsersIn,
    user: UserContext = Depends(_require_academic_sync_permission),
    db: Session = Depends(get_db),
):
    # Backward-compatible alias. UI and docs use /cms-sync-check from v25.9.16.2.23.
    return _run_class_cms_sync_check(class_id, payload, user, db)


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
    user: UserContext = Depends(require_permission('view_questions')),
    db: Session = Depends(get_db),
):
    service = AcademicService(db)
    decision = service.access_decision(user)
    query = db.query(AcademicCampus)
    if branch:
        query = query.filter(AcademicCampus.branch == branch)
    if active is not None:
        query = query.filter(AcademicCampus.active.is_(active))
    if not decision.unrestricted:
        access_conditions = []
        if decision.teacher_ids:
            teacher_campuses = db.query(AcademicClass.campus).join(
                AcademicTeacherAssignment, AcademicTeacherAssignment.class_id == AcademicClass.id
            ).filter(AcademicTeacherAssignment.teacher_id.in_(decision.teacher_ids))
            if branch:
                teacher_campuses = teacher_campuses.filter(AcademicClass.branch == branch)
            access_conditions.append(AcademicCampus.campus_code.in_(teacher_campuses.distinct()))
        if decision.subject_codes:
            subject_campuses = db.query(AcademicClass.campus).join(
                AcademicSubject, AcademicSubject.id == AcademicClass.subject_id
            ).filter(func.lower(AcademicSubject.subject_code).in_(decision.subject_codes))
            if branch:
                subject_campuses = subject_campuses.filter(AcademicClass.branch == branch)
            access_conditions.append(AcademicCampus.campus_code.in_(subject_campuses.distinct()))
        if not access_conditions:
            query = query.filter(False)
        else:
            query = query.filter(or_(*access_conditions))
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


@router.delete('/campuses/{campus_id}', response_model=AcademicCampusOut)
def delete_academic_campus(
    campus_id: str,
    user: UserContext = Depends(require_permission('manage_settings')),
    db: Session = Depends(get_db),
):
    _require_academic_admin(db, user)
    campus = db.query(AcademicCampus).filter(AcademicCampus.id == campus_id).first()
    if not campus:
        raise HTTPException(status_code=404, detail='Không tìm thấy cơ sở')
    campus.active = False
    meta = dict(campus.metadata_json or {})
    meta.update({'deleted_from_ui': True})
    campus.metadata_json = meta
    db.commit()
    db.refresh(campus)
    log_audit(db, action='academic.campus.delete', status='success', message='Đã xóa/ẩn cơ sở AP', user=user, target_type='academic_campus', target_id=campus.id, metadata={'campus_code': campus.campus_code, 'branch': campus.branch})
    return campus


@router.get('/sync/ap/options', response_model=AcademicAPSyncOptionsOut)
def get_ap_sync_options(
    term_name: str = Query('', description='Tên kỳ AP, ví dụ Summer 2026. Có term_name thì backend gọi AP /get-course để lấy môn.'),
    branch: str = Query('poly'),
    include_subjects: bool = Query(True),
    user: UserContext = Depends(require_permission('manage_settings')),
    db: Session = Depends(get_db),
):
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
        raise HTTPException(status_code=400, detail=_safe_error_message('academic_validation_failed')) from exc



@router.post('/sync/ap/jobs', response_model=AcademicImportResultOut)
def enqueue_sync_from_ap_job(
    payload: AcademicAPSyncIn,
    user: UserContext = Depends(require_permission('manage_settings')),
    db: Session = Depends(get_db),
):
    _require_academic_admin(db, user)
    branch = (payload.branch or 'poly').strip().lower() or 'poly'
    term_name = (payload.term_name or '').strip()
    if not term_name:
        raise HTTPException(status_code=400, detail='Vui lòng chọn kỳ trước khi đồng bộ AP.')
    scope = (payload.sync_scope or 'all').strip().lower() or 'all'
    active = (
        db.query(AcademicSyncRun)
        .filter(
            AcademicSyncRun.source == 'ap',
            AcademicSyncRun.status.in_(['queued', 'running']),
            AcademicSyncRun.term_name == term_name,
            AcademicSyncRun.branch == branch,
        )
        .order_by(AcademicSyncRun.created_at.desc())
        .first()
    )
    if active:
        return {'ok': True, 'message': 'Hệ thống đang có job đồng bộ AP đang chạy. Trạng thái sẽ tự cập nhật.', 'sync_run': active, 'counters': AcademicSyncCounters()}

    request_json = json_safe_value({
        'term_name': term_name,
        'sync_scope': scope,
        'campus': payload.campus,
        'campuses': payload.campuses or [],
        'branch': branch,
        'subject_codes': payload.subject_codes or [],
        'max_subjects': int(payload.max_subjects or 0),
        'dry_run': bool(payload.dry_run),
    })
    importer = AcademicImportService(db)
    run = importer.create_run(
        source='ap',
        mode=f'api_{scope}_job_dry_run' if payload.dry_run else f'api_{scope}_job',
        requested_by=user.user_id,
        term_name=term_name,
        campus=','.join((payload.campuses or [])[:10]) if payload.campuses else payload.campus,
        branch=branch,
        status='queued',
        counters_json={
            'request': request_json,
            'progress': {'current': 0, 'total': 1, 'label': 'Đã đưa job đồng bộ AP vào hàng đợi', 'updated_at': None},
        },
    )
    try:
        from app.worker import academic_ap_sync_task
        async_result = academic_ap_sync_task.delay(run.id)
        data = run.counters_json if isinstance(run.counters_json, dict) else {}
        data['enqueue'] = {'task_name': 'academic_ap_sync_task', 'celery_task_id': getattr(async_result, 'id', None)}
        run.counters_json = json_safe_value(data)
        db.add(run)
        db.commit()
        db.refresh(run)
    except Exception as exc:
        run.status = 'failed'
        run.error_message = f'Không đưa job đồng bộ AP vào Celery/Redis: {exc}'[:4000]
        db.add(run)
        db.commit()
        db.refresh(run)
        raise HTTPException(status_code=503, detail='Không đưa job đồng bộ AP vào hàng đợi. Kiểm tra Redis/worker rồi thử lại.') from exc

    log_audit(
        db,
        action='academic.ap.sync_api.enqueue',
        status='success',
        message='Đã đưa job đồng bộ AP vào hàng đợi',
        user=user,
        target_type='academic_sync_run',
        target_id=run.id,
        metadata=request_json,
    )
    return {'ok': True, 'message': 'Đã đưa job đồng bộ AP vào hàng đợi. Trạng thái sẽ tự cập nhật.', 'sync_run': run, 'counters': AcademicSyncCounters()}


@router.get('/sync/ap/jobs', response_model=list[AcademicSyncRunOut])
def list_ap_sync_jobs(
    term_name: str = Query(''),
    branch: str = Query(''),
    status_filter: str = Query('active', alias='status'),
    limit: int = Query(10, ge=1, le=50),
    user: UserContext = Depends(require_permission('manage_settings')),
    db: Session = Depends(get_db),
):
    _require_academic_admin(db, user)
    query = db.query(AcademicSyncRun).filter(AcademicSyncRun.source == 'ap')
    if term_name.strip():
        query = query.filter(AcademicSyncRun.term_name == term_name.strip())
    if branch.strip():
        query = query.filter(AcademicSyncRun.branch == branch.strip().lower())
    if status_filter == 'active':
        query = query.filter(AcademicSyncRun.status.in_(['queued', 'running']))
    elif status_filter and status_filter != 'all':
        query = query.filter(AcademicSyncRun.status == status_filter)
    return query.order_by(AcademicSyncRun.created_at.desc()).limit(limit).all()


@router.get('/sync/ap/jobs/{run_id}', response_model=AcademicSyncRunOut)
def get_ap_sync_job(
    run_id: str,
    user: UserContext = Depends(require_permission('manage_settings')),
    db: Session = Depends(get_db),
):
    _require_academic_admin(db, user)
    run = db.get(AcademicSyncRun, run_id)
    if not run or run.source != 'ap':
        raise HTTPException(status_code=404, detail='Không tìm thấy job đồng bộ AP')
    return run


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
