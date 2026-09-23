from datetime import datetime, timedelta
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.models.academic import (
    AcademicBulkOperationJob,
    AcademicClass,
    AcademicClassSyncJob,
    AcademicTerm,
)
from app.services.academic import daily_teacher_report_runtime
from app.services.academic import student_management_runtime
from app.services.academic.scheduled_parent import (
    ContinuationPublishError,
    confirm_parent_continuation,
    create_or_load_scheduled_parent,
    publish_parent_continuation,
    recover_due_parent_continuations,
    scheduled_parent_key,
)


def _engine():
    engine = create_engine('sqlite+pysqlite:///:memory:')
    AcademicBulkOperationJob.__table__.create(engine)
    return engine


def _values():
    return {
        'job_type': 'daily_score_report_pipeline',
        'status': 'queued',
        'term_id': 'term-1',
        'branch': 'poly',
        'campus': None,
        'requested_by': 'scheduler',
        'progress_current': 0,
        'progress_total': 100,
        'progress_label': 'queued',
        'request_json': {'run_date_vn': '2026-09-22'},
        'result_json': {},
    }


def test_duplicate_schedule_delivery_loads_one_parent_by_stable_key():
    engine = _engine()
    key = scheduled_parent_key(
        'score-report-daily',
        run_date_vn='2026-09-22',
        term_id='term-1',
        branch='POLY',
    )
    with Session(engine) as db:
        first, first_created = create_or_load_scheduled_parent(
            db,
            idempotency_key=key,
            values=_values(),
        )
        second, second_created = create_or_load_scheduled_parent(
            db,
            idempotency_key=key,
            values=_values(),
        )

        assert first.id == second.id
        assert first_created is True
        assert second_created is False
        assert db.query(AcademicBulkOperationJob).count() == 1
        assert key == 'score-report-daily:2026-09-22:term-1:poly'
    engine.dispose()


def test_publish_failure_is_committed_as_dispatch_pending_before_error():
    engine = _engine()
    now = datetime(2026, 9, 22, 5, 0, 0)
    with Session(engine) as db:
        parent, _ = create_or_load_scheduled_parent(
            db,
            idempotency_key='score-report-daily:2026-09-22:term-1:poly',
            values=_values(),
        )

        def fail_publish(**kwargs):
            raise ConnectionError('broker unavailable')

        with pytest.raises(ContinuationPublishError):
            publish_parent_continuation(
                db,
                parent,
                publisher=fail_publish,
                task_name='academic_daily_score_report_parent_task',
                args=[parent.id],
                queue='sync-bulk',
                countdown=30,
                now=now,
            )

        db.expire_all()
        persisted = db.get(AcademicBulkOperationJob, parent.id)
        continuation = persisted.result_json['continuation']
        assert continuation['status'] == 'dispatch_pending'
        assert continuation['attempt_count'] == 1
        assert continuation['last_error_class'] == 'ConnectionError'
        assert continuation['last_error'] == 'broker unavailable'
        assert continuation['due_at'] > now.isoformat()
        assert persisted.status == 'queued'
    engine.dispose()


def test_recovery_scanner_republishes_due_non_terminal_parent():
    engine = _engine()
    now = datetime(2026, 9, 22, 5, 10, 0)
    published = []
    with Session(engine) as db:
        parent, _ = create_or_load_scheduled_parent(
            db,
            idempotency_key='score-report-daily:2026-09-22:term-1:poly',
            values=_values(),
        )
        parent.result_json = {
            'continuation': {
                'status': 'dispatch_pending',
                'attempt_count': 1,
                'due_at': (now - timedelta(seconds=1)).isoformat(),
                'task_name': 'academic_daily_score_report_parent_task',
                'args': [parent.id],
                'queue': 'sync-bulk',
                'countdown': 0,
            }
        }
        db.add(parent)
        db.commit()

        result = recover_due_parent_continuations(
            db,
            publisher=lambda **kwargs: published.append(kwargs) or 'task-2',
            job_types={'daily_score_report_pipeline'},
            now=now,
            max_attempts=5,
        )

        assert result == {
            'scanned': 1,
            'republished': 1,
            'failed': 0,
            'errors': [],
        }
        assert published[0]['task_name'] == 'academic_daily_score_report_parent_task'
        db.refresh(parent)
        assert parent.result_json['continuation']['status'] == 'dispatched'
        assert parent.result_json['continuation']['attempt_count'] == 2
        assert parent.result_json['continuation']['task_id'] == 'task-2'
    engine.dispose()


def test_worker_confirmation_prevents_recovery_of_accepted_continuation():
    engine = _engine()
    with Session(engine) as db:
        parent, _ = create_or_load_scheduled_parent(
            db,
            idempotency_key='score-report-daily:2026-09-22:term-1:poly',
            values=_values(),
        )
        parent.result_json = {
            'continuation': {
                'status': 'dispatched',
                'attempt_count': 1,
                'due_at': '2026-09-22T05:01:00',
            }
        }
        db.add(parent)
        db.commit()

        confirm_parent_continuation(
            db,
            parent,
            now=datetime(2026, 9, 22, 5, 0, 30),
        )

        db.refresh(parent)
        assert parent.result_json['continuation']['status'] == 'confirmed'
        assert parent.result_json['continuation']['confirmed_at'] == '2026-09-22T05:00:30'
    engine.dispose()


def test_duplicate_0500_scheduler_delivery_creates_one_parent(monkeypatch):
    engine = create_engine(
        'sqlite+pysqlite:///:memory:',
        connect_args={'check_same_thread': False},
        poolclass=StaticPool,
    )
    for model in (
        AcademicTerm,
        AcademicClass,
        AcademicBulkOperationJob,
        AcademicClassSyncJob,
    ):
        model.__table__.create(engine)
    factory = sessionmaker(bind=engine)
    monkeypatch.setattr(daily_teacher_report_runtime, 'SessionLocal', factory)
    with factory() as db:
        db.add(AcademicTerm(
            id='term-1',
            term_code='FA26',
            term_name='Fall 2026',
            branch='poly',
            active=True,
        ))
        db.add(AcademicClass(
            id='class-1',
            term_id='term-1',
            subject_id='subject-1',
            class_code='SOA102.01',
            class_name='SOA102.01',
            campus='hn',
            branch='poly',
            active=True,
        ))
        db.commit()

    class Celery:
        def __init__(self):
            self.calls = []

        def send_task(self, name, args=None, **options):
            self.calls.append((name, list(args or []), options))
            return type('Task', (), {'id': f'task-{len(self.calls)}'})()

    celery = Celery()
    first = daily_teacher_report_runtime.start_daily_score_report_pipeline(celery)
    second = daily_teacher_report_runtime.start_daily_score_report_pipeline(celery)

    assert first['created_parent_ids']
    assert second['created_parent_ids'] == []
    assert second['reused_parent_ids'] == first['created_parent_ids']
    with factory() as db:
        parents = db.query(AcademicBulkOperationJob).filter(
            AcademicBulkOperationJob.job_type
            == daily_teacher_report_runtime.DAILY_PARENT_JOB_TYPE,
        ).all()
        assert len(parents) == 1
        assert parents[0].idempotency_key.startswith('score-report-daily:')
    engine.dispose()


def test_0300_scheduler_does_not_swallow_continuation_publish_error(monkeypatch):
    parent = SimpleNamespace(
        id='parent-1',
        status='running',
        result_json={'phase': 'ap_sync_pending'},
        progress_current=1,
        progress_label='queued',
        updated_at=None,
    )
    run = SimpleNamespace(id='run-1')

    class FakeSession:
        def add(self, value):
            return None

        def commit(self):
            return None

        def rollback(self):
            return None

        def close(self):
            return None

        def get(self, model, object_id):
            return parent

    class FakeWorkflow:
        def __init__(self, db):
            self.db = db

        def enqueue_sync_from_ap_job(self, payload, *, user):
            return {'sync_run': run}

    monkeypatch.setattr(student_management_runtime, 'SessionLocal', FakeSession)
    monkeypatch.setattr(
        student_management_runtime,
        '_active_configured_terms',
        lambda db: [SimpleNamespace(id='term-1', branch='poly', term_name='Fall 2026')],
    )
    monkeypatch.setattr(
        student_management_runtime,
        '_campus_codes_for_term',
        lambda db, term, branch: ['hn'],
    )
    monkeypatch.setattr(
        student_management_runtime,
        'create_or_load_scheduled_parent',
        lambda db, **kwargs: (parent, True),
    )
    monkeypatch.setattr(
        student_management_runtime,
        'AcademicAPSyncWorkflowService',
        FakeWorkflow,
    )
    monkeypatch.setattr(student_management_runtime, '_mark_ap_03_run', lambda *args, **kwargs: None)

    original = ConnectionError('broker unavailable')

    def fail_publish(*args, **kwargs):
        raise ContinuationPublishError(parent.id, original)

    monkeypatch.setattr(student_management_runtime, '_publish_ap_followup', fail_publish)

    with pytest.raises(ContinuationPublishError) as raised:
        student_management_runtime._start_ap_03_schedule(SimpleNamespace())

    assert raised.value.original is original
