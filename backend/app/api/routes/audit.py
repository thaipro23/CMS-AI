from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from app.core.rbac import UserContext, ensure_course_access, require_permission
from app.db.session import get_db
from app.models.audit import AuditLog

router = APIRouter()


@router.get('')
async def list_audit_logs(
    course_id: str | None = Query(default=None),
    status: str | None = Query(default=None),
    error_type: str | None = Query(default=None),
    actor_id: str | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
    user: UserContext = Depends(require_permission('view_jobs')),
):
    if course_id:
        ensure_course_access(user, course_id)
    query = db.query(AuditLog)
    if course_id:
        query = query.filter(AuditLog.course_id == course_id)
    if status and status != 'all':
        query = query.filter(AuditLog.status == status)
    if error_type and error_type != 'all':
        query = query.filter(AuditLog.error_type == error_type)
    if actor_id:
        query = query.filter(AuditLog.actor_id.ilike(f'%{actor_id}%'))
    total = query.count()
    rows = query.order_by(AuditLog.created_at.desc()).offset((page - 1) * page_size).limit(page_size).all()
    return {
        'items': [
            {
                'id': row.id,
                'course_id': row.course_id,
                'actor_id': row.actor_id,
                'actor_role': row.actor_role,
                'action': row.action,
                'target_type': row.target_type,
                'target_id': row.target_id,
                'status': row.status,
                'error_type': row.error_type,
                'message': row.message,
                'metadata': row.metadata_json or {},
                'created_at': row.created_at.isoformat() if row.created_at else None,
            }
            for row in rows
        ],
        'total': total,
        'page': page,
        'page_size': page_size,
        'total_pages': max(1, (total + page_size - 1) // page_size),
    }
