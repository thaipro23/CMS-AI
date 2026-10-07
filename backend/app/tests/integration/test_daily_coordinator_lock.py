"""Uses the disposable PostgreSQL/Redis services provided by CI."""
import os
from copy import deepcopy
from datetime import datetime

import pytest
import redis
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.services.academic import daily_academic_pipeline as runtime
from app.tests.test_daily_continuation_backlog import seed
from app.tests.test_academic_daily_pipeline_recovery import FakeCelery
from app.models.academic import AcademicBulkOperationJob, AcademicClassSyncJob

pytestmark = pytest.mark.integration
KEY = 'ai-server:academic-daily:coordinator'


@pytest.fixture
def redis_client(monkeypatch):
    url = os.environ.get('REDIS_URL')
    if not url:
        pytest.skip('CI Redis URL not configured')
    client = redis.Redis.from_url(url)
    assert client.ping()
    # Exercise the actual application shared-pool client, including lock-token
    # decoding and coordinator client.close(), rather than a replacement factory.
    monkeypatch.setattr(runtime.settings, 'redis_url', url)
    yield client
    client.close()


@pytest.fixture
def factory(tmp_path, monkeypatch):
    engine = create_engine(f'sqlite+pysqlite:///{tmp_path}/coordination.sqlite')
    AcademicBulkOperationJob.__table__.create(engine)
    AcademicClassSyncJob.__table__.create(engine)
    factory = sessionmaker(bind=engine)
    monkeypatch.setattr(runtime, 'SessionLocal', factory)
    yield factory
    engine.dispose()


def test_redis_excludes_watchdog_and_worker_until_owner_releases(redis_client, factory):
    now = datetime.utcnow()
    with factory() as db:
        root = seed(db, now)
        before = deepcopy(root.result_json)
    lease = redis_client.lock(KEY, timeout=240, blocking=False)
    assert lease.acquire(blocking=False)
    try:
        celery = FakeCelery()
        assert runtime.recover_daily_academic_pipeline(celery, now=now)['status'] == 'coordinator_busy'
        assert runtime.run_daily_academic_pipeline(celery, 'root')['status'] == 'coordinator_busy'
        assert not celery.sent
        with factory() as db:
            assert db.get(AcademicBulkOperationJob, 'root').result_json == before
    finally:
        lease.release()
    result = runtime.recover_daily_academic_pipeline(celery, now=now)
    assert result['republished'] == 1
    assert celery.sent[0][2]['queue'] == 'sync-fast'
    assert redis_client.exists(KEY) == 0


def test_redis_lease_is_bounded_and_released_on_error(redis_client, factory):
    with pytest.raises(RuntimeError, match='worker failed'):
        with runtime._daily_coordinator_session() as (db, acquired):
            assert acquired
            assert 0 < redis_client.ttl(KEY) <= 240
            raise RuntimeError('worker failed')
    assert redis_client.exists(KEY) == 0


def test_expired_owner_cannot_release_new_redis_owner(redis_client, factory):
    next_owner = redis_client.lock(KEY, timeout=240, blocking=False)
    with runtime._daily_coordinator_session() as (db, acquired):
        assert acquired
        redis_client.delete(KEY)  # Simulate expiration of the first owner's lease.
        assert next_owner.acquire(blocking=False)
    try:
        assert next_owner.owned()
    finally:
        next_owner.release()


def test_postgres_lock_stays_on_same_connection_across_commits(monkeypatch):
    url = os.environ.get('DATABASE_URL')
    if not url or not url.startswith('postgresql'):
        pytest.skip('CI PostgreSQL URL not configured')
    engine = create_engine(url, pool_size=2, max_overflow=0)
    monkeypatch.setattr(runtime, 'SessionLocal', sessionmaker(bind=engine))
    monkeypatch.setattr(runtime, '_daily_redis_client', lambda: None)
    try:
        with runtime._daily_coordinator_session() as (db, acquired):
            assert acquired
            db.commit()
            with sessionmaker(bind=engine)() as other:
                assert runtime._try_daily_root_db_lock(other, 'coordinator') is False
                db.commit()
                assert runtime._try_daily_root_db_lock(other, 'coordinator') is False
        with sessionmaker(bind=engine)() as other:
            assert runtime._try_daily_root_db_lock(other, 'coordinator') is True
            runtime._release_daily_root_db_lock(other, 'coordinator')
    finally:
        engine.dispose()


def test_postgres_error_does_not_leave_advisory_lock_in_pool(monkeypatch):
    from sqlalchemy import text
    from sqlalchemy.exc import DBAPIError
    from sqlalchemy.pool import NullPool
    url = os.environ.get('DATABASE_URL')
    if not url or not url.startswith('postgresql'):
        pytest.skip('CI PostgreSQL URL not configured')
    engine = create_engine(url, pool_size=1, max_overflow=0)
    probe = create_engine(url, poolclass=NullPool)  # Always a different physical session.
    monkeypatch.setattr(runtime, 'SessionLocal', sessionmaker(bind=engine))
    monkeypatch.setattr(runtime, '_daily_redis_client', lambda: None)
    try:
        with pytest.raises(DBAPIError):
            with runtime._daily_coordinator_session() as (db, acquired):
                assert acquired
                db.execute(text('SELECT 1 / 0'))
        with sessionmaker(bind=probe)() as other:
            assert runtime._try_daily_root_db_lock(other, 'coordinator') is True
            runtime._release_daily_root_db_lock(other, 'coordinator')
    finally:
        probe.dispose()
        engine.dispose()
