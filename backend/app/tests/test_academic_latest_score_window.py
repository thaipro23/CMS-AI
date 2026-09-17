from __future__ import annotations

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.models.academic import AcademicBulkOperationJob, AcademicClassSyncJob
from app.services.academic import student_management_runtime as runtime
from app.services.academic import daily_teacher_report_runtime as daily_runtime
from app.models.academic import AcademicClass, AcademicTerm


class _Celery:
    def __init__(self):
        self.calls: list[dict] = []

    def send_task(self, name, args=None, queue=None, countdown=None):
        self.calls.append({
            'name': name,
            'args': list(args or []),
            'queue': queue,
            'countdown': countdown,
        })
        return type('AsyncResult', (), {'id': f'task-{len(self.calls)}'})()


def _engine():
    engine = create_engine(
        'sqlite+pysqlite:///:memory:',
        connect_args={'check_same_thread': False},
        poolclass=StaticPool,
    )
    AcademicBulkOperationJob.__table__.create(engine)
    AcademicClassSyncJob.__table__.create(engine)
    return engine


def _parent(class_count: int = 15) -> AcademicBulkOperationJob:
    return AcademicBulkOperationJob(
        id='score-parent',
        job_type=runtime.LATEST_SCORE_JOB_TYPE,
        status='queued',
        requested_by='admin',
        request_json={
            'approved_class_ids': [f'class-{index}' for index in range(1, class_count + 1)],
            'requester_context': {'user_id': 'admin'},
            'force': True,
            'limit': 500,
        },
        result_json={},
    )


def test_latest_score_initial_dispatch_enqueues_only_ten_classes(monkeypatch):
    engine = _engine()
    factory = sessionmaker(bind=engine)
    monkeypatch.setattr(runtime, 'SessionLocal', factory)
    with Session(engine) as db:
        parent = _parent()
        db.add(parent)
        db.commit()
        db.refresh(parent)
        db.expunge(parent)

    celery = _Celery()
    result = runtime._enqueue_latest_score_children(celery, parent)

    class_calls = [call for call in celery.calls if call['name'] == runtime.CLASS_SYNC_TASK]
    assert len(class_calls) == 10
    assert result['class_total'] == 15
    assert result['queued'] == 10
    assert len(result['child_job_ids']) == 10
    assert celery.calls[-1]['name'] == runtime.LATEST_SCORE_WATCHDOG_TASK
    engine.dispose()


def test_latest_score_watchdog_releases_completed_slots_for_next_classes(monkeypatch):
    engine = _engine()
    factory = sessionmaker(bind=engine)
    monkeypatch.setattr(runtime, 'SessionLocal', factory)
    with Session(engine) as db:
        parent = _parent()
        db.add(parent)
        db.commit()
        db.refresh(parent)
        db.expunge(parent)

    celery = _Celery()
    runtime._enqueue_latest_score_children(celery, parent)
    with Session(engine) as db:
        first_children = (
            db.query(AcademicClassSyncJob)
            .filter(AcademicClassSyncJob.parent_job_id == 'score-parent')
            .order_by(AcademicClassSyncJob.class_id.asc())
            .all()
        )
        for child in first_children[:3]:
            child.status = 'completed'
        db.commit()

    before = len([call for call in celery.calls if call['name'] == runtime.CLASS_SYNC_TASK])
    result = runtime._watch_latest_score_children(celery, 'score-parent')
    after = len([call for call in celery.calls if call['name'] == runtime.CLASS_SYNC_TASK])

    assert after - before == 3
    assert len(result['child_job_ids']) == 13
    assert result['active'] == 10
    assert result['completed'] == 3
    engine.dispose()


def test_daily_0500_scheduler_also_dispatches_only_the_ten_class_window(monkeypatch):
    engine = create_engine(
        'sqlite+pysqlite:///:memory:',
        connect_args={'check_same_thread': False},
        poolclass=StaticPool,
    )
    for model in (AcademicTerm, AcademicClass, AcademicBulkOperationJob, AcademicClassSyncJob):
        model.__table__.create(engine)
    factory = sessionmaker(bind=engine)
    monkeypatch.setattr(daily_runtime, 'SessionLocal', factory)
    with Session(engine) as db:
        term = AcademicTerm(
            id='term-fa26', term_code='FA26', term_name='Fall 2026', branch='poly', active=True,
        )
        db.add(term)
        db.add_all([
            AcademicClass(
                id=f'daily-class-{index}',
                term_id=term.id,
                subject_id='subject-1',
                class_code=f'SOA102.{index:02d}',
                class_name=f'SOA102.{index:02d}',
                campus='hn',
                branch='poly',
                active=True,
            )
            for index in range(1, 16)
        ])
        db.commit()

    celery = _Celery()
    result = daily_runtime.start_daily_score_report_pipeline(celery)

    class_calls = [call for call in celery.calls if call['name'] == 'academic_class_sync_task']
    assert len(class_calls) == 10
    with Session(engine) as db:
        parent = db.get(AcademicBulkOperationJob, result['created_parent_ids'][0])
        assert parent.result_json['target_class_count'] == 15
        assert len(parent.result_json['child_job_ids']) == 10
        assert parent.result_json['dispatch_window'] == 10
        first_children = (
            db.query(AcademicClassSyncJob)
            .filter(AcademicClassSyncJob.parent_job_id == parent.id)
            .order_by(AcademicClassSyncJob.class_id.asc())
            .all()
        )
        for child in first_children[:3]:
            child.status = 'completed'
        db.commit()

    before = len(class_calls)
    progress = daily_runtime.run_daily_score_report_parent(
        celery,
        result['created_parent_ids'][0],
    )
    class_calls = [call for call in celery.calls if call['name'] == 'academic_class_sync_task']
    assert len(class_calls) - before == 3
    assert progress['status'] == 'running'
    assert progress['terminal_count'] == 3
    engine.dispose()
