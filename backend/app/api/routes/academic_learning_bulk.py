from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.routes.academic import _requester_context_json, _require_academic_sync_permission
from app.core.json_safe import json_safe_value
from app.core.rbac import UserContext
from app.db.session import get_db
from app.models.academic import AcademicBulkOperationJob, AcademicClass
from app.services.academic_service import AcademicService
from app.worker import celery_app


router = APIRouter()


class AcademicLearningRefreshFilterIn(BaseModel):
    term_id: str = Field(..., min_length=1)
    branch: str = Field('poly', max_length=64)
    campus: str | None = Field(None, max_length=64)
    search: str | None = Field(None, max_length=255)
    learning_status: str | None = Field(None, max_length=80)
    force: bool = True
    limit: int = Field(500, ge=1, le=500)
    max_classes: int = Field(3000, ge=1, le=5000)
    mode: str | None = Field(None, max_length=50)


def _same_filter(job: AcademicBulkOperationJob, payload: AcademicLearningRefreshFilterIn) -> bool:
    request = job.request_json if isinstance(job.request_json, dict) else {}
    return (
        str(request.get('search') or '').strip().casefold() == str(payload.search or '').strip().casefold()
        and str(request.get('learning_status') or '').strip().casefold()
        == str(payload.learning_status or '').strip().casefold()
    )


@router.post('/subjects/learning/refresh/jobs')
def enqueue_latest_learning_refresh(
    payload: AcademicLearningRefreshFilterIn,
    user: UserContext = Depends(_require_academic_sync_permission),
    db: Session = Depends(get_db),
):
    """Refresh learning scores for the current CMS filter without auto-mapping.

    The scope is frozen at enqueue time through the same access-filtered subject
    query used by Student Management. Only classes that already resolve to an
    Open edX course are admitted. Course mapping, AP sync and enrollment writes
    are deliberately outside this operation.
    """
    branch = str(payload.branch or 'poly').strip().lower() or 'poly'
    campus = str(payload.campus or '').strip().lower() or None

    active_jobs = (
        db.query(AcademicBulkOperationJob)
        .filter(
            AcademicBulkOperationJob.job_type == 'learning_refresh_filter',
            AcademicBulkOperationJob.term_id == payload.term_id,
            AcademicBulkOperationJob.branch == branch,
            AcademicBulkOperationJob.campus == campus,
            AcademicBulkOperationJob.status.in_(['queued', 'running']),
        )
        .order_by(AcademicBulkOperationJob.created_at.desc())
        .limit(20)
        .all()
    )
    for active in active_jobs:
        if _same_filter(active, payload):
            return {
                'ok': True,
                'job_id': active.id,
                'status': active.status,
                'class_total': int((active.request_json or {}).get('approved_class_total') or 0),
                'reused': True,
                'message': 'Tác vụ lấy điểm mới nhất cho phạm vi này đang chạy.',
            }

    service = AcademicService(db)
    preview = service.auto_map_subject_courses_for_filter(
        user,
        term_id=payload.term_id,
        branch=branch,
        campus=campus,
        search=payload.search,
        learning_status=payload.learning_status,
        max_classes=max(1, min(5000, int(payload.max_classes or 3000))),
        dry_run=True,
    )
    scoped_ids = [str(item) for item in (preview.get('class_ids') or []) if str(item or '').strip()]
    class_rows = (
        db.query(AcademicClass)
        .filter(AcademicClass.id.in_(scoped_ids), AcademicClass.active.is_(True))
        .all()
        if scoped_ids
        else []
    )
    mapped_class_ids: list[str] = []
    skipped_unmapped = 0
    for class_row in class_rows:
        mapping = service.effective_course_mapping_for_class(class_row)
        if mapping and str(mapping.openedx_course_id or '').strip():
            mapped_class_ids.append(str(class_row.id))
        else:
            skipped_unmapped += 1

    request_json = json_safe_value({
        'term_id': payload.term_id,
        'branch': branch,
        'campus': campus,
        'search': payload.search,
        'learning_status': payload.learning_status,
        'force': bool(payload.force),
        'limit': max(1, min(500, int(payload.limit or 500))),
        'mode': payload.mode,
        'max_classes': max(1, min(5000, int(payload.max_classes or 3000))),
        'approved_class_ids': mapped_class_ids,
        'approved_class_total': len(mapped_class_ids),
        'scope_class_total': len(scoped_ids),
        'skipped_unmapped_count': skipped_unmapped,
        'requester_context': _requester_context_json(user),
        'scope_enforced_by_backend': True,
        'operation': 'latest_learning_scores_only',
    })
    job = AcademicBulkOperationJob(
        job_type='learning_refresh_filter',
        status='queued' if mapped_class_ids else 'completed',
        term_id=payload.term_id,
        branch=branch,
        campus=campus,
        requested_by=user.user_id or user.username,
        progress_current=0 if mapped_class_ids else 100,
        progress_total=100,
        progress_label=(
            'Đang chờ lấy điểm mới nhất'
            if mapped_class_ids
            else 'Không có lớp đã ghép Course CMS để lấy điểm'
        ),
        request_json=request_json,
        result_json=(
            {}
            if mapped_class_ids
            else json_safe_value({
                'ok': True,
                'class_total': 0,
                'scope_class_total': len(scoped_ids),
                'skipped_unmapped_count': skipped_unmapped,
                'message': 'Không có lớp đã ghép Course CMS trong phạm vi hiện tại.',
            })
        ),
        finished_at=None if mapped_class_ids else datetime.utcnow(),
    )
    db.add(job)
    db.commit()
    db.refresh(job)

    if mapped_class_ids:
        try:
            celery_app.send_task(
                'academic_learning_refresh_filter_task',
                args=[job.id],
                queue='sync-bulk',
            )
        except Exception as exc:
            job.status = 'failed'
            job.progress_label = 'Không đưa được tác vụ lấy điểm vào hàng đợi'
            job.error_message = str(exc)[:4000]
            job.result_json = json_safe_value({'ok': False, 'message': job.progress_label})
            job.finished_at = datetime.utcnow()
            job.updated_at = datetime.utcnow()
            db.add(job)
            db.commit()
            raise

    return {
        'ok': True,
        'job_id': job.id,
        'status': job.status,
        'class_total': len(mapped_class_ids),
        'scope_class_total': len(scoped_ids),
        'skipped_unmapped_count': skipped_unmapped,
        'reused': False,
        'message': (
            f'Đã tạo tác vụ lấy điểm mới nhất cho {len(mapped_class_ids)} lớp.'
            if mapped_class_ids
            else 'Không có lớp đã ghép Course CMS để lấy điểm.'
        ),
    }
