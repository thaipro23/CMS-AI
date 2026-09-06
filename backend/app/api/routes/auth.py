from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy.orm import Session
from jose import jwt
from pydantic import BaseModel

from app.core.rbac import ROLE_LABELS, ROLE_PERMISSIONS, UserContext, get_user_context
from app.db.session import get_db
from app.services.business_rbac import BusinessRBACService
from app.core.config import is_production, settings
from app.core.security import _normalize_role
from app.core.session_security import (
    claim_bridge_ticket_once,
    enforce_fixed_window_rate_limit,
    revoke_session,
    ticket_fingerprint,
)

router = APIRouter()


class OpenEdxSessionExchangeRequest(BaseModel):
    ticket: str


class OpenEdxSessionExchangeResponse(BaseModel):
    access_token: str | None = None
    token_type: str = 'cookie'
    expires_in: int
    user_id: str
    email: str | None = None
    role: str
    course_ids: list[str] = []
    username: str | None = None
    name: str | None = None


def _bridge_secret() -> str:
    secret = settings.openedx_session_bridge_secret or settings.openedx_connector_hmac_secret
    if not secret:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail='Kết nối đăng nhập CMS chưa được cấu hình. Vui lòng liên hệ quản trị viên.')
    return str(secret)


def _b64url_decode(value: str) -> bytes:
    padding = '=' * (-len(value) % 4)
    return base64.urlsafe_b64decode((value + padding).encode('ascii'))


def _decode_bridge_ticket(ticket: str) -> dict[str, Any]:
    try:
        payload_b64, supplied_sig = ticket.split('.', 1)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail='Phiên đăng nhập CMS không hợp lệ. Vui lòng đăng nhập lại.') from exc
    expected_sig = hmac.new(_bridge_secret().encode('utf-8'), payload_b64.encode('ascii'), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected_sig, supplied_sig):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail='Không xác minh được phiên đăng nhập CMS. Vui lòng đăng nhập lại.')
    try:
        payload = json.loads(_b64url_decode(payload_b64).decode('utf-8'))
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail='Dữ liệu phiên đăng nhập CMS không hợp lệ. Vui lòng đăng nhập lại.') from exc
    now = int(time.time())
    issued_at = int(payload.get('iat') or 0)
    expires_at = int(payload.get('exp') or 0)
    max_age = max(30, min(int(settings.openedx_session_bridge_max_age_seconds or 60), 120))
    if not issued_at or not expires_at or not payload.get('jti'):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={'code': 'CMS_TICKET_CLAIMS_INVALID', 'message': 'Phiên đăng nhập thiếu thông tin xác thực. Vui lòng đăng nhập lại.'},
        )
    if expires_at < now:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail={'code': 'CMS_TICKET_EXPIRED', 'message': 'Phiên đăng nhập CMS đã hết hạn. Vui lòng đăng nhập lại.'})
    if issued_at > now + 10 or now - issued_at > max_age or expires_at - issued_at > max_age:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail={'code': 'CMS_TICKET_TOO_OLD', 'message': 'Phiên đăng nhập CMS đã hết hạn. Vui lòng đăng nhập lại.'})
    if payload.get('aud') != settings.openedx_session_bridge_audience:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail='Phiên đăng nhập không dành cho hệ thống này.')
    if payload.get('iss') != settings.openedx_session_bridge_issuer:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail='Không xác minh được nguồn cấp phiên đăng nhập.')
    return payload


def _normalize_courses(value: Any) -> list[str]:
    if not value:
        return []
    if isinstance(value, list):
        return [str(item) for item in value if item]
    if isinstance(value, str):
        return [item.strip() for item in value.split(',') if item.strip()]
    return []


@router.get('/me')
def me(user: UserContext = Depends(get_user_context), db: Session = Depends(get_db)):
    business = BusinessRBACService(db)
    business_permissions = business.effective_permissions_for_user(user)
    return {
        'user_id': user.user_id,
        'email': user.email,
        'role': user.role,
        'label': ROLE_LABELS[user.role],
        'permissions': sorted(user.permissions),
        'business_permissions': sorted(business_permissions),
        'effective_legacy_role': business.effective_legacy_role_for_user(user.user_id, user.role, email=user.email, username=getattr(user, 'username', None)),
        'course_ids': user.course_ids or [],
        'auth_mode': settings.auth_mode,
    }


@router.get('/roles')
def roles():
    return [
        {'role': role, 'label': ROLE_LABELS[role], 'permissions': sorted(permissions)}
        for role, permissions in ROLE_PERMISSIONS.items()
    ]


@router.post('/openedx-session/exchange', response_model=OpenEdxSessionExchangeResponse, response_model_exclude_none=True)
def exchange_openedx_session(payload: OpenEdxSessionExchangeRequest, request: Request, response: Response, db: Session = Depends(get_db)):
    """Exchange a CMS/Studio session bridge ticket for an AI Server JWT.

    The ticket is created by the Open edX CMS connector while the browser is
    already authenticated in CMS. This lets staff open AI Server without typing a
    second password or manually pasting a JWT. The ticket itself is short-lived
    and signed with the shared AI_CONNECTOR_HMAC_SECRET/OPENEDX_CONNECTOR_HMAC_SECRET.
    """
    client_ip = str(getattr(request.client, 'host', '') or 'unknown')
    fingerprint = ticket_fingerprint(payload.ticket)
    enforce_fixed_window_rate_limit(
        key=f'auth-exchange-ip:{client_ip}',
        limit=int(settings.auth_exchange_rate_limit_per_minute or 20),
        window_seconds=60,
    )
    enforce_fixed_window_rate_limit(
        key=f'auth-exchange-ticket:{fingerprint}',
        limit=int(settings.auth_exchange_ticket_rate_limit_per_minute or 3),
        window_seconds=60,
    )
    data = _decode_bridge_ticket(payload.ticket)
    now = int(time.time())
    claim_bridge_ticket_once(jti=str(data.get('jti') or ''), ttl_seconds=max(1, int(data.get('exp') or now) - now))
    is_super_admin = bool(data.get('is_superuser') or data.get('is_super_admin'))
    # v25.9.16.7.2.64.13: Open edX staff/course author is not an AI legacy role.
    # Only Open edX superuser/super_admin may receive legacy role=admin. All
    # other users receive viewer and are authorized through business RBAC/AP
    # assignments only.
    base_role = 'admin' if is_super_admin else 'viewer'
    course_ids = _normalize_courses(data.get('course_ids') or data.get('courses'))
    ttl = max(900, min(int(settings.auth_session_token_ttl_seconds or 7200), 2 * 60 * 60))
    now = int(time.time())
    user_id = str(data.get('sub') or data.get('user_id') or data.get('username') or 'openedx-user')
    role = _normalize_role(base_role)
    claims = {
        'sub': user_id,
        'user_id': user_id,
        'username': data.get('username'),
        'name': data.get('name'),
        'email': data.get('email'),
        'role': role,
        'course_ids': course_ids,
        'iss': settings.jwt_issuer,
        'aud': settings.jwt_audience,
        'token_type': 'ai_session',
        'auth_source': 'openedx_cms_session_bridge',
        'is_staff': bool(data.get('is_staff')),
        'is_superuser': bool(data.get('is_superuser')),
        'is_super_admin': bool(data.get('is_super_admin') or data.get('is_superuser')),
        'ai_system_admin': bool(is_super_admin),
        'iat': now,
        'exp': now + ttl,
        'jti': str(uuid.uuid4()),
    }
    token = jwt.encode(claims, settings.jwt_secret, algorithm=settings.jwt_algorithm)

    cookie_kwargs: dict[str, Any] = {
        'key': 'ai_openedx_access_token',
        'value': token,
        'httponly': True,
        'secure': bool(settings.auth_cookie_secure),
        'samesite': settings.auth_cookie_samesite or 'lax',
        'max_age': ttl,
        'path': '/',
    }
    if settings.auth_cookie_domain:
        cookie_kwargs['domain'] = settings.auth_cookie_domain
    response.set_cookie(**cookie_kwargs)

    return OpenEdxSessionExchangeResponse(
        access_token=None if is_production() else token,
        token_type='cookie' if is_production() else 'bearer',
        expires_in=ttl,
        user_id=user_id,
        email=data.get('email'),
        role=role,
        course_ids=course_ids,
        username=data.get('username'),
        name=data.get('name'),
    )


@router.post('/logout')
def logout(request: Request, response: Response):
    token = request.cookies.get('ai_openedx_access_token')
    if token:
        try:
            claims = jwt.decode(
                token,
                settings.jwt_secret,
                algorithms=[settings.jwt_algorithm],
                issuer=settings.jwt_issuer,
                audience=settings.jwt_audience,
                options={'verify_exp': False},
            )
            revoke_session(jti=str(claims.get('jti') or '') or None, expires_at=int(claims.get('exp') or 0))
        except HTTPException:
            raise
        except Exception:
            # Invalid/expired cookies are still cleared; never expose token details.
            pass
    delete_kwargs: dict[str, Any] = {'key': 'ai_openedx_access_token', 'path': '/'}
    if settings.auth_cookie_domain:
        delete_kwargs['domain'] = settings.auth_cookie_domain
    response.delete_cookie(**delete_kwargs)
    return {'ok': True, 'ui_status': 'success', 'ui_title': 'Đã đăng xuất', 'ui_message': 'Phiên đăng nhập đã được thu hồi.'}
