"""Bounded, fork-safe Redis pools for direct application commands.

Celery owns its broker/backend pools separately. Explicitly supplying our pool
means Redis.close() returns client resources without disconnecting shared pools.
"""
from functools import lru_cache
import os

import redis
from redis.backoff import NoBackoff
from redis.retry import Retry

from app.core.config import settings


@lru_cache(maxsize=8)
def _pool(pid: int, url: str, timeout: float, max_connections: int):
    return redis.ConnectionPool.from_url(
        url, decode_responses=True, socket_connect_timeout=timeout,
        socket_timeout=timeout, max_connections=max_connections,
        retry=Retry(NoBackoff(), 0), retry_on_timeout=False,
    )


def get_redis_client(*, cache: bool = False):
    url = (settings.redis_cache_url or settings.redis_url) if cache else settings.redis_url
    pool = _pool(os.getpid(), url, float(settings.redis_socket_timeout_seconds),
                 int(settings.redis_max_connections))
    return redis.Redis(connection_pool=pool)
