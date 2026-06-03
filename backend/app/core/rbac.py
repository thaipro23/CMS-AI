from dataclasses import dataclass
from typing import Any
from fastapi import Depends, HTTPException, status
from app.core.config import settings
from app.core.security import Principal, ROLE_LABELS, ROLE_PERMISSIONS, get_principal


@dataclass
class UserContext:
    user_id: str
    role: str
    permissions: set[str]
    email: str | None = None
    course_ids: list[str] | None = None


def get_user_context(principal: Principal = Depends(get_principal)) -> UserContext:
    return UserContext(
        user_id=principal.user_id,
        email=principal.email,
        role=principal.role,
        permissions=ROLE_PERMISSIONS[principal.role],
        course_ids=principal.course_ids,
    )


def require_permission(permission: str):
    def checker(user: UserContext = Depends(get_user_context)) -> UserContext:
        if permission not in user.permissions:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f'Role {user.role} does not have permission: {permission}',
            )
        return user
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
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail='Production token has no course_ids claim; access denied')
    if not course_id:
        return
    if allowed and course_id not in allowed:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail='You do not have access to this course')


def restrict_query_to_courses(query: Any, model: Any, user: UserContext):
    if user.role == 'admin':
        return query
    allowed = list(user.course_ids or [])
    if _production_requires_course_scope(user) and not allowed:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail='Production token has no course_ids claim; access denied')
    if allowed:
        return query.filter(model.course_id.in_(allowed))
    return query
