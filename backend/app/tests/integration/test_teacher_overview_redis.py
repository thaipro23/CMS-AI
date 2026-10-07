"""Real Redis verifies pool lifecycle, isolated stores and cache expiry."""
import os
import time
from uuid import uuid4

import pytest
from fastapi import HTTPException
from redis.exceptions import ConnectionError

from app.core.config import settings
from app.core.redis_client import get_redis_client
from app.core import session_security
from app.services.academic import teacher_report_cache as cache
from app.tests.test_teacher_report_redis_cache import overview
from app.tests.test_teacher_cms_list_performance import seeded_report

pytestmark = pytest.mark.integration


@pytest.fixture
def clients(monkeypatch):
    url = os.environ.get('REDIS_URL')
    if not url:
        pytest.skip('CI Redis URL not configured')
    from urllib.parse import urlsplit, urlunsplit
    parts = urlsplit(url)
    cache_url = urlunsplit((parts.scheme, parts.netloc, '/14', parts.query, parts.fragment))
    monkeypatch.setattr(settings, 'redis_url', url)
    monkeypatch.setattr(settings, 'redis_cache_url', cache_url)
    a, b = get_redis_client(), get_redis_client(cache=True)
    assert a.ping() and b.ping()
    yield a, b
    # Only our namespace is cleaned; never FLUSHDB a shared broker.
    for key in b.scan_iter('ai:teacher-overview:v1:*'):
        b.delete(key)
    a.close()
    b.close()


def test_overview_cache_ttl_expiry_and_committed_invalidation(clients):
    _, client = clients
    with seeded_report() as db:
        assert overview(db)['cache']['redis_status'] == 'miss'
        assert overview(db)['cache']['redis_status'] == 'hit'
        keys = [k for k in client.scan_iter('ai:teacher-overview:v1:*') if k != cache.GENERATION_KEY]
        assert len(keys) == 1 and 0 < client.ttl(keys[0]) <= 45
        client.pexpire(keys[0], 30)
        time.sleep(0.06)
        assert overview(db)['cache']['redis_status'] == 'miss'
        cache.invalidate_teacher_overview_cache()
        assert overview(db)['cache']['redis_status'] == 'miss'


def test_closing_client_does_not_disconnect_shared_pool(clients):
    a, _ = clients
    a.close()
    b = get_redis_client()
    assert a.connection_pool is b.connection_pool
    assert b.ping()
    for _ in range(50):
        get_redis_client().ping()
    assert b.connection_pool._created_connections <= 2


def test_auth_ticket_and_revocation_keep_broker_store(clients):
    broker, cache_client = clients
    jti = 'redis-test-' + uuid4().hex
    try:
        session_security.claim_bridge_ticket_once(jti=jti, ttl_seconds=60)
        with pytest.raises(HTTPException) as error:
            session_security.claim_bridge_ticket_once(jti=jti, ttl_seconds=60)
        assert error.value.status_code == 401
        session_security.revoke_session(jti=jti, expires_at=int(time.time()) + 60)
        assert session_security.is_session_revoked(jti)
        assert broker.exists(f'ai:auth:bridge-used:{jti}') == 1
        assert cache_client.exists(f'ai:auth:bridge-used:{jti}') == 0
    finally:
        broker.delete(f'ai:auth:bridge-used:{jti}', f'ai:auth:session-revoked:{jti}')


def test_security_remains_fail_closed_on_redis_outage(clients, monkeypatch):
    monkeypatch.setattr(settings, 'app_env', 'production')
    monkeypatch.setattr(session_security, 'get_redis_client',
                        lambda: (_ for _ in ()).throw(ConnectionError('offline')))
    with pytest.raises(HTTPException) as error:
        session_security.claim_bridge_ticket_once(jti='ticket', ttl_seconds=30)
    assert error.value.status_code == 503
