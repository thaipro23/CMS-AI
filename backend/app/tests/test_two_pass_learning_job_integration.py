from __future__ import annotations

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.academic import AcademicClassSyncJob
from app.worker import _enqueue_delayed_learning_sync_followup, academic_class_sync_task


def test_delayed_learning_job_is_durable_scheduled_and_deduplicated(monkeypatch):
    engine = create_engine('sqlite+pysqlite:///:memory:')
    AcademicClassSyncJob.__table__.create(engine)
    scheduled: list[dict] = []
    monkeypatch.setattr(settings, 'academic_learning_sync_replica_delay_seconds', 60)
    monkeypatch.setattr(academic_class_sync_task, 'apply_async', lambda **kwargs: scheduled.append(kwargs))

    with Session(engine) as db:
        job, reused = _enqueue_delayed_learning_sync_followup(
            db,
            requested_by='operator',
            class_id='class-1',
            force=True,
            limit=500,
            requester_context={'user_id': 'operator'},
            parent_job_id='full-job-1',
        )
        duplicate, duplicate_reused = _enqueue_delayed_learning_sync_followup(
            db,
            requested_by='operator',
            class_id='class-1',
            force=True,
            limit=500,
            requester_context={'user_id': 'operator'},
            parent_job_id='full-job-1',
        )

    assert not reused
    assert duplicate_reused
    assert duplicate.id == job.id
    assert job.job_type == 'learning_sync'
    assert job.status == 'queued'
    assert job.request_json['delayed_after_enrollment'] is True
    assert scheduled == [{'args': [job.id], 'countdown': 60}]
    engine.dispose()
