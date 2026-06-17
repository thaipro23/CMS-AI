from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from app.core.rbac import UserContext, ensure_course_access, require_permission
from app.db.session import get_db
from app.models.audit import AuditLog
from app.models.rbac import UserRoleAssignment
from app.models.question_bank import BankOperationJob, CourseQuizInstance, EdxCourseChapterMapping, EdxCourseMapping, QuizBlueprint
from app.services.business_rbac import BusinessRBACService

router = APIRouter()


def _actor_identity(user: UserContext) -> set[str]:
    raw = user.raw_claims or {}
    return {str(v).strip() for v in [user.user_id, user.email, user.username, raw.get('email'), raw.get('username')] if str(v or '').strip()}


def _visible_audit_row(db: Session, service: BusinessRBACService, user: UserContext, row: AuditLog) -> bool:
    if service.is_system_admin(user):
        return True
    if row.actor_id and row.actor_id in _actor_identity(user):
        return True
    target_type = (row.target_type or '').lower()
    target_id = row.target_id or ''
    metadata = row.metadata_json or {}
    try:
        if target_type in {'department', 'bank_department'} and target_id:
            return service.is_visible_scope(user, 'DEPARTMENT', target_id)
        if target_type in {'subject', 'bank_subject'} and target_id:
            return service.is_visible_scope(user, 'SUBJECT', target_id)
        if target_type in {'subject_offering', 'subject_version'} and target_id:
            return service.is_visible_scope(user, 'SUBJECT_VERSION', target_id)
        if target_type in {'chapter', 'subject_chapter'} and target_id:
            return service.is_visible_scope(user, 'CHAPTER', target_id)
        if target_type in {'bank_version'} and target_id:
            return service.is_visible_scope(user, 'BANK_VERSION', target_id)
        if target_type in {'bank_release'} and target_id:
            return service.is_visible_scope(user, 'RELEASE', target_id)
        if target_type == 'quiz_blueprint' and target_id:
            item = db.get(QuizBlueprint, target_id)
            return bool(item and service.is_visible_scope(user, 'CHAPTER', item.chapter_id))
        if target_type == 'course_quiz_instance' and target_id:
            item = db.get(CourseQuizInstance, target_id)
            return bool(item and service.is_visible_scope(user, 'CHAPTER', item.chapter_id))
        if target_type == 'course_mapping' and target_id:
            item = db.get(EdxCourseMapping, target_id)
            return bool(item and service.is_visible_scope(user, 'SUBJECT', item.subject_id))
        if target_type == 'course_chapter_mapping' and target_id:
            item = db.get(EdxCourseChapterMapping, target_id)
            return bool(item and service.is_visible_scope(user, 'CHAPTER', item.subject_chapter_id))
        if target_type == 'bank_operation_job' and target_id:
            job = db.get(BankOperationJob, target_id)
            if not job:
                return False
            if job.bank_version_id and service.is_visible_scope(user, 'BANK_VERSION', job.bank_version_id):
                return True
            if job.release_id and service.is_visible_scope(user, 'RELEASE', job.release_id):
                return True
            if job.course_quiz_instance_id:
                item = db.get(CourseQuizInstance, job.course_quiz_instance_id)
                if item and service.is_visible_scope(user, 'CHAPTER', item.chapter_id):
                    return True
            return False
        if target_type == 'rbac_assignment' and target_id:
            item = db.get(UserRoleAssignment, target_id)
            if not item:
                return False
            return item.user_id in _actor_identity(user) or service.can_grant(user, item.role_code, item.scope_type, item.scope_id)
        # Some audit rows store scope in metadata only.
        scope_type = metadata.get('scope_type') or metadata.get('target_scope_type')
        scope_id = metadata.get('scope_id') or metadata.get('target_scope_id')
        if scope_type and scope_id:
            return service.is_visible_scope(user, str(scope_type), str(scope_id))
    except Exception:
        return False
    return False


def _serialize(row: AuditLog):
    return {
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
    service = BusinessRBACService(db)
    ordered = query.order_by(AuditLog.created_at.desc())
    if service.is_system_admin(user):
        total = ordered.count()
        rows = ordered.offset((page - 1) * page_size).limit(page_size).all()
        return {
            'items': [_serialize(row) for row in rows],
            'total': total,
            'page': page,
            'page_size': page_size,
            'total_pages': max(1, (total + page_size - 1) // page_size),
        }

    # Non-admin audit is fail-closed. We intentionally do not expose global logs.
    # Pull a bounded window and filter by RBAC/actor server-side so users only see
    # their own actions or actions inside their assigned Bank scope.
    candidate_rows = ordered.limit(max(1000, page * page_size * 10)).all()
    visible = [row for row in candidate_rows if _visible_audit_row(db, service, user, row)]
    total = len(visible)
    rows = visible[(page - 1) * page_size: page * page_size]
    return {
        'items': [_serialize(row) for row in rows],
        'total': total,
        'page': page,
        'page_size': page_size,
        'total_pages': max(1, (total + page_size - 1) // page_size),
    }
