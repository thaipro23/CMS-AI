from dataclasses import dataclass
from typing import Any
from fastapi import Depends, HTTPException, status
from app.core.config import settings
from app.core.security import Principal, ROLE_LABELS, ROLE_PERMISSIONS, get_principal
from app.db.session import get_db
from sqlalchemy.orm import Session


@dataclass
class UserContext:
    user_id: str
    role: str
    permissions: set[str]
    email: str | None = None
    username: str | None = None
    course_ids: list[str] | None = None
    raw_claims: dict | None = None


def get_user_context(principal: Principal = Depends(get_principal), db: Session = Depends(get_db)) -> UserContext:
    user = UserContext(
        user_id=principal.user_id,
        email=principal.email,
        username=str(principal.raw_claims.get('username') or '') or None,
        role=principal.role,
        permissions=ROLE_PERMISSIONS[principal.role],
        course_ids=principal.course_ids,
        raw_claims=principal.raw_claims,
    )
    # Resolve server-side grants on every request. An SSO session issued before
    # a SYSTEM_ADMIN grant can still carry viewer; course guards must see the
    # current effective role. No elevated role is written back into the token.
    from app.services.business_rbac import BusinessRBACService
    if BusinessRBACService(db).is_system_admin(user):
        user.role = 'admin'
        user.permissions = set(ROLE_PERMISSIONS['admin'])
    return user


def require_permission(permission: str):
    def checker(user: UserContext = Depends(get_user_context), db: Session = Depends(get_db)) -> UserContext:
        if permission in user.permissions:
            return user
        # Bank-first business RBAC lives in the database. This bridge lets a CMS
        # session token with legacy role=viewer still gain the exact AI Server
        # permissions assigned by SYSTEM_ADMIN/DEPARTMENT_HEAD/SUBJECT_OWNER.
        try:
            from app.services.business_rbac import BusinessRBACService
            if BusinessRBACService(db).has_any_business_permission(user, permission):
                return user
        except HTTPException:
            raise
        except Exception:
            # Do not turn a broken RBAC table into an accidental allow.
            pass
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail='Bạn không có quyền thực hiện thao tác này.',
        )
    return checker


def _production_requires_course_scope(user: UserContext) -> bool:
    return (
        settings.require_course_scope_in_production
        and settings.app_env.lower() in {'prod', 'production'}
        and user.role != 'admin'
    )


def ensure_course_access(user: UserContext, course_id: str | None) -> None:
    """Course-level guard for JWT/SSO claims.

    Admin can access every course. Non-admin users are restricted by course_ids.
    In production, a non-admin token without course_ids is denied instead of
    silently seeing every course. Demo/dev remains permissive for local testing.
    """
    if user.role == 'admin':
        return
    allowed = set(user.course_ids or [])
    if _production_requires_course_scope(user) and not allowed:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail='Tài khoản chưa được cấp quyền truy cập khóa học.')
    if not course_id:
        return
    if allowed and course_id not in allowed:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail='Bạn không có quyền truy cập khóa học này.')


def restrict_query_to_courses(query: Any, model: Any, user: UserContext):
    if user.role == 'admin':
        return query
    allowed = list(user.course_ids or [])
    if _production_requires_course_scope(user) and not allowed:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail='Tài khoản chưa được cấp quyền truy cập khóa học.')
    if allowed:
        return query.filter(model.course_id.in_(allowed))
    return query
