from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Response, status
from jose import jwt
from pydantic import BaseModel

from app.core.rbac import ROLE_LABELS, ROLE_PERMISSIONS, UserContext, get_user_context
from app.core.config import settings
from app.core.security import _normalize_role

router = APIRouter()


class OpenEdxSessionExchangeRequest(BaseModel):
    ticket: str


class OpenEdxSessionExchangeResponse(BaseModel):
    access_token: str
    token_type: str = 'bearer'
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
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail='CMS session bridge secret is not configured')
    return str(secret)


def _b64url_decode(value: str) -> bytes:
    padding = '=' * (-len(value) % 4)
    return base64.urlsafe_b64decode((value + padding).encode('ascii'))


def _decode_bridge_ticket(ticket: str) -> dict[str, Any]:
    try:
        payload_b64, supplied_sig = ticket.split('.', 1)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail='Invalid CMS session ticket') from exc
    expected_sig = hmac.new(_bridge_secret().encode('utf-8'), payload_b64.encode('ascii'), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected_sig, supplied_sig):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail='Invalid CMS session ticket signature')
    try:
        payload = json.loads(_b64url_decode(payload_b64).decode('utf-8'))
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail='Invalid CMS session ticket payload') from exc
    now = int(time.time())
    if int(payload.get('exp') or 0) < now:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail='CMS session ticket expired')
    if payload.get('aud') != settings.openedx_session_bridge_audience:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail='CMS session ticket audience mismatch')
    if payload.get('iss') != settings.openedx_session_bridge_issuer:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail='CMS session ticket issuer mismatch')
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
def me(user: UserContext = Depends(get_user_context)):
    return {
        'user_id': user.user_id,
        'email': user.email,
        'role': user.role,
        'label': ROLE_LABELS[user.role],
        'permissions': sorted(user.permissions),
        'course_ids': user.course_ids or [],
        'auth_mode': settings.auth_mode,
    }


@router.get('/roles')
def roles():
    return [
        {'role': role, 'label': ROLE_LABELS[role], 'permissions': sorted(permissions)}
        for role, permissions in ROLE_PERMISSIONS.items()
    ]


@router.post('/openedx-session/exchange', response_model=OpenEdxSessionExchangeResponse)
def exchange_openedx_session(payload: OpenEdxSessionExchangeRequest, response: Response):
    """Exchange a CMS/Studio session bridge ticket for an AI Server JWT.

    The ticket is created by the Open edX CMS connector while the browser is
    already authenticated in CMS. This lets staff open AI Server without typing a
    second password or manually pasting a JWT. The ticket itself is short-lived
    and signed with the shared AI_CONNECTOR_HMAC_SECRET/OPENEDX_CONNECTOR_HMAC_SECRET.
    """
    data = _decode_bridge_ticket(payload.ticket)
    role = _normalize_role(str(data.get('role') or 'viewer'))
    course_ids = _normalize_courses(data.get('course_ids') or data.get('courses'))
    ttl = int(settings.auth_session_token_ttl_seconds or 28800)
    now = int(time.time())
    user_id = str(data.get('sub') or data.get('user_id') or data.get('username') or 'openedx-user')
    claims = {
        'sub': user_id,
        'user_id': user_id,
        'username': data.get('username'),
        'name': data.get('name'),
        'email': data.get('email'),
        'role': role,
        'course_ids': course_ids,
        'iss': 'ai-learning-server',
        'auth_source': 'openedx_cms_session_bridge',
        'iat': now,
        'exp': now + ttl,
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
        access_token=token,
        expires_in=ttl,
        user_id=user_id,
        email=data.get('email'),
        role=role,
        course_ids=course_ids,
        username=data.get('username'),
        name=data.get('name'),
    )
