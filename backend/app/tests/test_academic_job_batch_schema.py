from __future__ import annotations

from app.models.academic import AcademicClassSyncJob


def test_class_sync_job_has_durable_parent_and_unique_idempotency_key():
    columns = AcademicClassSyncJob.__table__.columns

    assert 'parent_job_id' in columns
    assert columns['parent_job_id'].nullable is True
    assert 'idempotency_key' in columns
    assert columns['idempotency_key'].nullable is True
    assert columns['idempotency_key'].unique is True

