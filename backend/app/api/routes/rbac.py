from __future__ import annotations

from fastapi import APIRouter, Depends, Header, HTTPException
from sqlalchemy.orm import Session

from app.core.config import is_production, settings
from app.core.rbac import UserContext, get_user_context, require_permission
from app.db.session import get_db
from app.schemas.rbac import (
    EffectiveRBACOut,
    RBACBootstrapOut,
    RBACPermissionOut,
    RBACRoleOut,
    RoleAssignmentCreate,
    RoleAssignmentListOut,
    RoleAssignmentOut,
    RoleAssignmentRevoke,
)
from app.services.audit_log import AuditErrorType, log_audit
from app.services.business_rbac import BusinessRBACService

router = APIRouter()


@router.get('/me', response_model=EffectiveRBACOut)
def effective_me(user: UserContext = Depends(get_user_context), db: Session = Depends(get_db)):
    service = BusinessRBACService(db)
    assignments = service.active_assignments_for_actor(user)
    raw_claims = user.raw_claims or {}
    return {
        'user_id': user.user_id,
        'legacy_role': user.role,
        'effective_legacy_role': service.effective_legacy_role_for_user(
            user.user_id,
            user.role,
            email=user.email or raw_claims.get('email'),
            username=user.username or raw_claims.get('username'),
        ),
        'permissions': sorted(service.effective_permissions_for_user(user)),
        'assignments': [service.serialize_assignment(item) for item in assignments],
    }


@router.get('/roles', response_model=list[RBACRoleOut])
def list_roles(user: UserContext = Depends(require_permission('view_questions')), db: Session = Depends(get_db)):
    return BusinessRBACService(db).list_roles()


@router.get('/permissions', response_model=list[RBACPermissionOut])
def list_permissions(user: UserContext = Depends(require_permission('view_questions')), db: Session = Depends(get_db)):
    return BusinessRBACService(db).list_permissions()


@router.get('/assignments', response_model=RoleAssignmentListOut)
def list_assignments(
    user_id: str | None = None,
    role_code: str | None = None,
    scope_type: str | None = None,
    scope_id: str | None = None,
    include_revoked: bool = False,
    user: UserContext = Depends(require_permission('view_questions')),
    db: Session = Depends(get_db),
):
    service = BusinessRBACService(db)
    items = service.list_assignments(
        actor=user,
        user_id=user_id,
        role_code=role_code,
        scope_type=scope_type,
        scope_id=scope_id,
        include_revoked=include_revoked,
    )
    return {'items': [service.serialize_assignment(item) for item in items], 'total': len(items)}


@router.post('/assignments', response_model=RoleAssignmentOut)
def create_assignment(payload: RoleAssignmentCreate, user: UserContext = Depends(require_permission('view_questions')), db: Session = Depends(get_db)):
    service = BusinessRBACService(db)
    try:
        item = service.create_assignment(actor=user, **payload.model_dump())
        log_audit(
            db,
            action='rbac.assignment.create',
            status='success',
            message='Gán quyền nghiệp vụ thành công',
            user=user,
            target_type='rbac_assignment',
            target_id=item.id,
            metadata={'assignee': item.user_id, 'role_code': item.role_code, 'scope_type': item.scope_type, 'scope_id': item.scope_id, 'sync_openedx_requested': payload.sync_openedx},
        )
        return service.serialize_assignment(item)
    except HTTPException:
        raise
    except Exception as exc:
        log_audit(db, action='rbac.assignment.create', status='failed', error_type=AuditErrorType.VALIDATION_ERROR, message=str(exc), user=user, target_type='rbac_assignment')
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.delete('/assignments/{assignment_id}', response_model=RoleAssignmentOut)
def revoke_assignment(assignment_id: str, payload: RoleAssignmentRevoke | None = None, user: UserContext = Depends(require_permission('view_questions')), db: Session = Depends(get_db)):
    service = BusinessRBACService(db)
    try:
        item = service.revoke_assignment(assignment_id, actor=user, revoke_reason=(payload.revoke_reason if payload else ''))
        log_audit(
            db,
            action='rbac.assignment.revoke',
            status='success',
            message='Thu hồi quyền nghiệp vụ thành công',
            user=user,
            target_type='rbac_assignment',
            target_id=item.id,
            metadata={'assignee': item.user_id, 'role_code': item.role_code, 'scope_type': item.scope_type, 'scope_id': item.scope_id},
        )
        return service.serialize_assignment(item)
    except HTTPException:
        raise
    except Exception as exc:
        log_audit(db, action='rbac.assignment.revoke', status='failed', error_type=AuditErrorType.VALIDATION_ERROR, message=str(exc), user=user, target_type='rbac_assignment', target_id=assignment_id)
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post('/bootstrap/system-admin', response_model=RBACBootstrapOut)
def bootstrap_system_admin(
    payload: RoleAssignmentCreate,
    db: Session = Depends(get_db),
    x_rbac_bootstrap_token: str | None = Header(default=None, alias='X-RBAC-Bootstrap-Token'),
):
    """Guarded one-time bootstrap for the first SYSTEM_ADMIN.

    Production is disabled unless RBAC_BOOTSTRAP_TOKEN is configured and the
    exact value is supplied in X-RBAC-Bootstrap-Token. After the first active
    SYSTEM_ADMIN exists, this endpoint refuses to create more admins.
    """
    if is_production():
        if not settings.rbac_bootstrap_token:
            raise HTTPException(status_code=403, detail='RBAC bootstrap bị tắt trong production. Hãy đăng nhập bằng Open edX superuser/AI_ADMIN rồi gán quyền.')
        if x_rbac_bootstrap_token != settings.rbac_bootstrap_token:
            raise HTTPException(status_code=403, detail='Sai RBAC bootstrap token')
    if settings.rbac_bootstrap_token and x_rbac_bootstrap_token != settings.rbac_bootstrap_token:
        raise HTTPException(status_code=403, detail='Sai RBAC bootstrap token')
    if payload.role_code != 'SYSTEM_ADMIN' or payload.scope_type != 'SYSTEM':
        raise HTTPException(status_code=400, detail='Bootstrap chỉ nhận role SYSTEM_ADMIN scope SYSTEM')
    service = BusinessRBACService(db)
    item, created = service.bootstrap_system_admin(user_id=payload.user_id, email=payload.email, reason=payload.grant_reason)
    if not created:
        return {'ok': False, 'created': False, 'message': 'Đã có SYSTEM_ADMIN. Hãy dùng API gán quyền bình thường.', 'assignment': None}
    return {'ok': True, 'created': True, 'message': 'Đã tạo SYSTEM_ADMIN đầu tiên.', 'assignment': service.serialize_assignment(item)}
