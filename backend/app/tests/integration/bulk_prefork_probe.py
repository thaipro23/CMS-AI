"""Local-only task registration for an isolated prefork capacity probe.

This module is excluded from production images with backend/app/tests. It never
calls the LMS or changes class/student records. Importing the real worker loads
the application's actual dependencies/configuration into the prefork children.
"""
import os
import resource
import time

from app.core.redis_client import get_redis_client
from app.worker import celery_app


@celery_app.task(name='ci_bulk_prefork_probe')
def probe(key: str, count: int):
    client = get_redis_client()
    pid = os.getpid()
    client.sadd(key, pid)
    client.expire(key, 60)
    deadline = time.monotonic() + 15
    while client.scard(key) < count:
        if time.monotonic() > deadline:
            raise RuntimeError('Ten probe tasks did not start concurrently')
        time.sleep(0.05)
    return {'pid': pid, 'peak_rss_mib': resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024}
