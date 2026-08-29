from __future__ import annotations

import time

from fastapi import HTTPException, status

from app.core.config import is_hardened_deployment, settings


def enforce_operation_rate_limit(
    *,
    namespace: str,
    actor_id: str,
    limit: int,
    window_seconds: int = 60,
    code: str = 'OPERATION_RATE_LIMITED',
    message: str = 'Có quá nhiều yêu cầu. Vui lòng thử lại sau.',
) -> None:
    """Fixed-window Redis limiter for expensive authenticated operations.

    Hardened environments fail closed when Redis is unavailable. Development
    remains usable without Redis so unit tests and local authoring are not
    coupled to infrastructure.
    """
    if int(limit or 0) <= 0:
        return
    try:
        import redis

        client = redis.Redis.from_url(settings.redis_url, decode_responses=True)
        bucket = int(time.time()) // max(1, int(window_seconds))
        key = f'ai:operation-rate:{namespace}:{actor_id}:{bucket}'
        pipe = client.pipeline()
        pipe.incr(key)
        pipe.expire(key, max(1, int(window_seconds)) + 5)
        count, _ = pipe.execute()
    except Exception as exc:
        if is_hardened_deployment():
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail={
                    'code': 'OPERATION_RATE_LIMIT_UNAVAILABLE',
                    'message': 'Kho kiểm soát tần suất thao tác đang không khả dụng.',
                },
            ) from exc
        return
    if int(count or 0) > int(limit):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail={'code': code, 'message': message},
            headers={'Retry-After': str(max(1, int(window_seconds)))},
        )
