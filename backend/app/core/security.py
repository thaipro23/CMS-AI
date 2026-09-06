from dataclasses import dataclass, field
from typing import Any
from fastapi import Header, HTTPException, Request, status
from jose import JWTError, jwt
from app.core.config import settings
from app.core.session_security import is_session_revoked


@dataclass
class Principal:
    user_id: str
    email: str | None = None
    role: str = 'viewer'
    course_ids: list[str] = field(default_factory=list)
    raw_claims: dict[str, Any] = field(default_factory=dict)


ROLE_PERMISSIONS: dict[str, set[str]] = {
    'admin': {
        'view_dashboard', 'view_questions', 'sync_course', 'estimate_cost', 'generate_questions',
        'edit_questions', 'delete_questions', 'review_questions', 'publish_questions', 'export_questions', 'manage_budget',
        'view_jobs', 'manage_settings', 'publish_to_openedx', 'view_user_analytics'
    },
    'teacher': {
        'view_dashboard', 'view_questions', 'sync_course', 'estimate_cost', 'generate_questions',
        'edit_questions', 'delete_questions', 'review_questions', 'publish_questions', 'export_questions', 'view_jobs',
        'publish_to_openedx'
    },
    'reviewer': {
        'view_dashboard', 'view_questions', 'estimate_cost', 'edit_questions',
        'review_questions', 'export_questions', 'view_jobs'
    },
    'viewer': {'view_dashboard', 'view_questions', 'view_jobs'},
}

ROLE_LABELS: dict[str, str] = {
    'admin': 'Admin - toàn quyền',
    'teacher': 'Teacher - sync/generate/review/publish/delete draft',
    'reviewer': 'Reviewer - duyệt/sửa câu hỏi, không generate/delete',
    'viewer': 'Viewer - chỉ xem dashboard/ngân hàng',
}


def _normalize_role(role: str | None) -> str:
    role = (role or 'viewer').lower().strip()
    if role not in ROLE_PERMISSIONS:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail='Vai trò tài khoản không hợp lệ.')
    return role


def _normalize_courses(value: Any) -> list[str]:
    if not value:
        return []
    if isinstance(value, list):
        return [str(item) for item in value if item]
    if isinstance(value, str):
        return [item.strip() for item in value.split(',') if item.strip()]
    return []


def _principal_from_demo_headers(x_user_id: str | None, x_user_role: str | None, x_user_email: str | None, x_course_ids: str | None) -> Principal:
    if settings.app_env.lower() in {'prod', 'production'}:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail='Demo header authentication is disabled in production. Set AUTH_MODE=jwt or AUTH_MODE=openedx_sso.',
        )
    role = _normalize_role(x_user_role)
    return Principal(user_id=x_user_id or 'demo-user', email=x_user_email, role=role, course_ids=_normalize_courses(x_course_ids))


def _principal_from_jwt(token: str) -> Principal:
    if not settings.jwt_secret or settings.jwt_secret == 'dev_secret_change_me':
        if settings.app_env.lower() in {'prod', 'production'}:
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail='Đăng nhập hệ thống chưa được cấu hình. Vui lòng liên hệ quản trị viên.')
    try:
        claims = jwt.decode(
            token,
            settings.jwt_secret,
            algorithms=[settings.jwt_algorithm],
            issuer=settings.jwt_issuer,
            audience=settings.jwt_audience,
            options={'require_exp': True, 'require_sub': True},
        )
    except JWTError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail='Phiên đăng nhập không hợp lệ hoặc đã hết hạn. Vui lòng đăng nhập lại.') from exc
    if not claims.get('sub') or not claims.get('exp'):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail='Phiên đăng nhập thiếu thông tin xác thực. Vui lòng đăng nhập lại.')
    if claims.get('token_type') != 'ai_session':
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail='Phiên đăng nhập không hợp lệ. Vui lòng đăng nhập lại.')
    if is_session_revoked(str(claims.get('jti') or '') or None):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={'code': 'SESSION_REVOKED', 'message': 'Phiên đăng nhập đã được thu hồi.'},
        )
    role = _normalize_role(claims.get('role'))
    if role == 'admin' and not (claims.get('is_superuser') is True or claims.get('is_super_admin') is True or claims.get('ai_system_admin') is True):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail='Chưa xác minh được quyền quản trị của tài khoản.')
    course_ids = _normalize_courses(claims.get('courses') or claims.get('course_ids'))
    return Principal(
        user_id=str(claims.get('sub') or claims.get('user_id') or 'jwt-user'),
        email=claims.get('email'),
        role=role,
        course_ids=course_ids,
        raw_claims=claims,
    )


def get_principal(
    request: Request,
    authorization: str | None = Header(default=None),
    x_user_id: str | None = Header(default=None),
    x_user_role: str | None = Header(default=None),
    x_user_email: str | None = Header(default=None),
    x_course_ids: str | None = Header(default=None),
) -> Principal:
    """Resolve the authenticated user.

    Security rules:
    - demo mode is development-only and uses X-User-* headers.
    - jwt mode requires Authorization: Bearer <jwt>; X-User-Role is ignored.
    - openedx_sso mode accepts the short-lived AI JWT issued by /auth/openedx-session/exchange after CMS session bridge validation; raw client-supplied roles are never trusted.
    """
    auth_mode = (settings.auth_mode or 'demo').lower().strip()

    if auth_mode == 'demo':
        if not settings.allow_demo_role_header:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail='Demo role header auth is disabled')
        return _principal_from_demo_headers(x_user_id, x_user_role, x_user_email, x_course_ids)

    if auth_mode in {'jwt', 'openedx_sso'}:
        if authorization and authorization.lower().startswith('bearer '):
            return _principal_from_jwt(authorization.split(' ', 1)[1])
        # Production-friendly option for reverse proxies/SSO: store the JWT in an
        # HttpOnly Secure SameSite cookie instead of localStorage.
        cookie_token = request.cookies.get('ai_openedx_access_token')
        if cookie_token:
            return _principal_from_jwt(cookie_token)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail='Vui lòng đăng nhập để tiếp tục.')

    raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f'Unsupported AUTH_MODE={settings.auth_mode}')
