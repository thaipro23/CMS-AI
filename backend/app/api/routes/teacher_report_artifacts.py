from __future__ import annotations

from datetime import datetime, timezone
from urllib.parse import quote
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.api.routes.academic import _require_academic_view_permission
from app.core.rbac import UserContext
from app.db.session import get_db
from app.models.academic import AcademicBulkOperationJob, AcademicTeacherReportJob
from app.services.academic.daily_teacher_report_runtime import (
    DAILY_PARENT_JOB_TYPE,
    SCHEDULED_EXPORT_JOB_TYPE,
    vn_iso,
)
from app.services.business_rbac import BusinessRBACService
from app.services.object_storage import StorageError, get_object_storage


router = APIRouter()
VN_TZ = ZoneInfo('Asia/Ho_Chi_Minh')
XLSX_MEDIA_TYPE = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'


def _utc_now_naive() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _local_date_from_iso(value: str | None):
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(VN_TZ).date()
    except Exception:
        return None


def _artifact_scope_access(
    db: Session,
    user: UserContext,
    *,
    term_id: str,
    branch: str,
    campus: str | None,
) -> None:
    rbac = BusinessRBACService(db)
    rbac.ensure_requested_branch_filter_allowed(
        user,
        branch,
        term_id=term_id,
        require_filter_when_scoped=True,
        action='tải báo cáo quản lý giáo viên',
    )
    # A campus-specific artifact follows normal campus access. The HO artifact
    # is broad and therefore remains restricted to an unrestricted/system actor.
    rbac.require_academic_scope(
        user,
        campus=campus,
        requested_by='academic-score-scheduler',
        request_json={
            'scope_enforced_by_backend': True,
            'scheduled': True,
            'management_scope': True,
        },
        action='tải báo cáo quản lý giáo viên',
    )


def _latest_artifact_job(
    db: Session,
    *,
    term_id: str,
    branch: str,
    campus: str | None,
) -> AcademicTeacherReportJob | None:
    query = db.query(AcademicTeacherReportJob).filter(
        AcademicTeacherReportJob.job_type == SCHEDULED_EXPORT_JOB_TYPE,
        AcademicTeacherReportJob.status == 'completed',
        AcademicTeacherReportJob.term_id == term_id,
        func.lower(func.coalesce(AcademicTeacherReportJob.branch, '')) == branch.lower(),
        AcademicTeacherReportJob.file_path.isnot(None),
    )
    if campus:
        query = query.filter(
            func.lower(func.coalesce(AcademicTeacherReportJob.campus, '')) == campus.lower(),
        )
    else:
        query = query.filter(AcademicTeacherReportJob.campus.is_(None))
    return query.order_by(
        AcademicTeacherReportJob.finished_at.desc().nullslast(),
        AcademicTeacherReportJob.created_at.desc(),
    ).first()


def _today_parent_status(db: Session, *, term_id: str, branch: str) -> dict | None:
    local_today = datetime.now(VN_TZ).date().isoformat()
    rows = db.query(AcademicBulkOperationJob).filter(
        AcademicBulkOperationJob.job_type == DAILY_PARENT_JOB_TYPE,
        AcademicBulkOperationJob.term_id == term_id,
        func.lower(func.coalesce(AcademicBulkOperationJob.branch, '')) == branch.lower(),
    ).order_by(AcademicBulkOperationJob.created_at.desc()).limit(12).all()
    for row in rows:
        request = row.request_json if isinstance(row.request_json, dict) else {}
        if str(request.get('run_date_vn') or '') == local_today:
            result = row.result_json if isinstance(row.result_json, dict) else {}
            return {
                'id': row.id,
                'status': row.status,
                'progress_current': row.progress_current,
                'progress_total': row.progress_total,
                'progress_label': row.progress_label,
                'failed_class_count': int(result.get('failed_class_count') or 0),
                'skipped_report_scopes': result.get('skipped_report_scopes') or [],
                'updated_at': vn_iso(row.updated_at),
            }
    return None


def _artifact_payload(
    db: Session,
    job: AcademicTeacherReportJob | None,
    *,
    term_id: str,
    branch: str,
    campus: str | None,
) -> dict:
    today_parent = _today_parent_status(db, term_id=term_id, branch=branch)
    if not job:
        return {
            'available': False,
            'term_id': term_id,
            'branch': branch,
            'campus': campus,
            'scope': (campus or 'HO').upper(),
            'generated_at': None,
            'source_synced_at': None,
            'timezone': 'Asia/Ho_Chi_Minh',
            'is_current_day': False,
            'warning': (
                'Chưa có file báo cáo thành công. Hệ thống sẽ tạo sau đợt đồng bộ điểm 05:00 +07.'
                if not today_parent
                else 'Báo cáo hôm nay chưa được tạo thành công.'
            ),
            'today_run': today_parent,
        }

    result = job.result_json if isinstance(job.result_json, dict) else {}
    generated_at = str(result.get('generated_at') or vn_iso(job.finished_at or job.updated_at))
    source_synced_at = str(result.get('source_synced_at') or generated_at)
    is_current_day = _local_date_from_iso(generated_at) == datetime.now(VN_TZ).date()
    warning = None
    if not is_current_day:
        warning = 'Báo cáo hôm nay chưa hoàn tất; đang dùng file thành công gần nhất.'
    elif today_parent and today_parent.get('status') == 'failed':
        warning = 'Đợt cập nhật 05:00 hôm nay có lỗi; file này là bản thành công gần nhất.'

    return {
        'available': True,
        'job_id': job.id,
        'term_id': term_id,
        'branch': branch,
        'campus': campus,
        'scope': (campus or 'HO').upper(),
        'file_name': job.file_name,
        'generated_at': generated_at,
        'source_synced_at': source_synced_at,
        'timezone': 'Asia/Ho_Chi_Minh',
        'is_current_day': is_current_day,
        'warning': warning,
        'today_run': today_parent,
    }


@router.get('/training/teacher-reports/latest')
def get_latest_teacher_report_artifact(
    term_id: str = Query(..., min_length=1),
    branch: str = Query('poly', pattern='^(poly|ptcd)$'),
    campus: str | None = Query(None),
    user: UserContext = Depends(_require_academic_view_permission),
    db: Session = Depends(get_db),
):
    clean_campus = str(campus or '').strip().lower() or None
    clean_branch = str(branch or 'poly').strip().lower()
    _artifact_scope_access(
        db,
        user,
        term_id=term_id,
        branch=clean_branch,
        campus=clean_campus,
    )
    job = _latest_artifact_job(
        db,
        term_id=term_id,
        branch=clean_branch,
        campus=clean_campus,
    )
    return _artifact_payload(
        db,
        job,
        term_id=term_id,
        branch=clean_branch,
        campus=clean_campus,
    )


@router.get('/training/teacher-reports/latest/download')
def download_latest_teacher_report_artifact(
    term_id: str = Query(..., min_length=1),
    branch: str = Query('poly', pattern='^(poly|ptcd)$'),
    campus: str | None = Query(None),
    user: UserContext = Depends(_require_academic_view_permission),
    db: Session = Depends(get_db),
):
    clean_campus = str(campus or '').strip().lower() or None
    clean_branch = str(branch or 'poly').strip().lower()
    _artifact_scope_access(
        db,
        user,
        term_id=term_id,
        branch=clean_branch,
        campus=clean_campus,
    )
    job = _latest_artifact_job(
        db,
        term_id=term_id,
        branch=clean_branch,
        campus=clean_campus,
    )
    if not job or not job.file_path:
        raise HTTPException(status_code=404, detail='Chưa có file báo cáo 05:00 thành công để tải.')
    try:
        raw = get_object_storage().read_bytes(job.file_path)
    except StorageError as exc:
        raise HTTPException(status_code=503, detail='File báo cáo đang không đọc được từ kho lưu trữ.') from exc
    file_name = job.file_name or f'teacher-report-{term_id}.xlsx'
    encoded = quote(file_name, safe='')
    return Response(
        content=raw,
        media_type=XLSX_MEDIA_TYPE,
        headers={
            'Content-Disposition': f"attachment; filename*=UTF-8''{encoded}",
            'X-Report-Generated-At': str((job.result_json or {}).get('generated_at') or vn_iso(job.finished_at)),
            'X-Report-Timezone': 'Asia/Ho_Chi_Minh',
        },
    )
