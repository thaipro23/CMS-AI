from __future__ import annotations

import os
import uuid

import pytest
import redis
from sqlalchemy import create_engine, text


pytestmark = pytest.mark.integration


def test_postgres_migration_head_and_idempotency_contract() -> None:
    engine = create_engine(os.environ['DATABASE_URL'], pool_pre_ping=True)
    with engine.begin() as connection:
        version = connection.execute(text('SELECT version_num FROM alembic_version')).scalar_one()
        assert version == '0061_v25_9_16_7_2_64_39'
        column_exists = connection.execute(text("""
            SELECT EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_schema = 'public'
                  AND table_name = 'ai_bank_version_diffs'
                  AND column_name = 'idempotency_key'
            )
        """)).scalar_one()
        assert column_exists is True
        constraint_exists = connection.execute(text("""
            SELECT EXISTS (
                SELECT 1 FROM pg_constraint
                WHERE conname = 'uq_ai_bank_version_diff_idempotency'
            )
        """)).scalar_one()
        assert constraint_exists is True


def test_redis_supports_single_use_and_ttl_contract() -> None:
    client = redis.Redis.from_url(os.environ['REDIS_URL'], decode_responses=True)
    key = f'ai-server:ci:single-use:{uuid.uuid4()}'
    assert client.set(key, 'used', ex=30, nx=True) is True
    assert client.set(key, 'replayed', ex=30, nx=True) is None
    ttl = client.ttl(key)
    assert 0 < ttl <= 30
    client.delete(key)
