from __future__ import annotations

import hashlib
import time
from typing import Any

from fastapi import HTTPException, status

from app.core.config import is_production, settings


def _redis_client():
    try:
        import redis

        return redis.Redis.from_url(settings.redis_url, decode_responses=True)
    except Exception as exc:  # pragma: no cover - import/runtime guard
        if is_production():
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail={
                    'code': 'AUTH_SECURITY_STORE_UNAVAILABLE',
                    'message': 'Kho bảo mật phiên đăng nhập đang không khả dụng.',
                },
            ) from exc
        return None


def ticket_fingerprint(ticket: str) -> str:
    return hashlib.sha256(ticket.encode('utf-8')).hexdigest()


def enforce_fixed_window_rate_limit(*, key: str, limit: int, window_seconds: int) -> None:
    if limit <= 0:
        return
    client = _redis_client()
    if client is None:
        return
    bucket = int(time.time()) // max(1, window_seconds)
    redis_key = f'ai:rate:{key}:{bucket}'
    try:
        pipe = client.pipeline()
        pipe.incr(redis_key)
        pipe.expire(redis_key, max(1, window_seconds) + 5)
        count, _ = pipe.execute()
    except Exception as exc:
        if is_production():
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail={
                    'code': 'AUTH_RATE_LIMIT_UNAVAILABLE',
                    'message': 'Không thể xác minh giới hạn đăng nhập lúc này.',
                },
            ) from exc
        return
    if int(count or 0) > limit:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail={
                'code': 'AUTH_RATE_LIMITED',
                'message': 'Có quá nhiều yêu cầu đăng nhập. Vui lòng thử lại sau.',
            },
            headers={'Retry-After': str(max(1, window_seconds))},
        )


def claim_bridge_ticket_once(*, jti: str, ttl_seconds: int) -> None:
    if not jti:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={'code': 'CMS_TICKET_JTI_MISSING', 'message': 'CMS session ticket thiếu mã dùng một lần.'},
        )
    client = _redis_client()
    if client is None:
        return
    key = f'ai:auth:bridge-used:{jti}'
    try:
        claimed = client.set(key, '1', ex=max(1, ttl_seconds), nx=True)
    except Exception as exc:
        if is_production():
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail={
                    'code': 'CMS_TICKET_REPLAY_STORE_UNAVAILABLE',
                    'message': 'Không thể xác minh CMS session ticket lúc này.',
                },
            ) from exc
        return
    if not claimed:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={'code': 'CMS_TICKET_REPLAYED', 'message': 'CMS session ticket đã được sử dụng hoặc không còn hợp lệ.'},
        )


def revoke_session(*, jti: str | None, expires_at: int | None) -> None:
    if not jti:
        return
    client = _redis_client()
    if client is None:
        return
    ttl = max(1, int(expires_at or 0) - int(time.time()))
    try:
        client.set(f'ai:auth:session-revoked:{jti}', '1', ex=ttl)
    except Exception as exc:
        if is_production():
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail={'code': 'AUTH_LOGOUT_STORE_UNAVAILABLE', 'message': 'Không thể thu hồi phiên đăng nhập lúc này.'},
            ) from exc


def is_session_revoked(jti: str | None) -> bool:
    if not jti:
        return False
    client = _redis_client()
    if client is None:
        return False
    try:
        return bool(client.exists(f'ai:auth:session-revoked:{jti}'))
    except Exception as exc:
        if is_production():
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail={'code': 'AUTH_SESSION_STORE_UNAVAILABLE', 'message': 'Không thể xác minh phiên đăng nhập lúc này.'},
            ) from exc
        return False
