from concurrent.futures import ThreadPoolExecutor
from datetime import datetime

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app import worker
from app.models.academic import AcademicClassSyncJob
from app.services.academic.subject_delivery import AcademicSubjectDeliveryService
from app.services.academic_service import AcademicService
from app.services.academic.job_claim import claim_class_sync_job


def _create_job_table(engine):
    AcademicClassSyncJob.__table__.create(engine)


def _queued_job(job_id='job-1'):
    return AcademicClassSyncJob(
        id=job_id,
        job_type='learning_sync',
        status='queued',
        class_id='class-1',
        requested_by='operator-1',
        force=False,
        limit=500,
        progress_current=0,
        progress_total=100,
        request_json={
            'approved_class_id': 'class-1',
            'requester_context': {
                'user_id': 'operator-1',
                'username': 'operator-1',
                'role': 'admin',
                'permissions': ['academic.manage'],
                'authenticated_admin_claims': {'is_superuser': True},
            },
        },
        result_json={},
    )


def test_two_sessions_racing_for_one_queued_job_get_exactly_one_claim(tmp_path):
    db_path = tmp_path / 'claim.sqlite'
    engine = create_engine(
        f'sqlite+pysqlite:///{db_path}',
        connect_args={'check_same_thread': False, 'timeout': 10},
    )
    _create_job_table(engine)
    factory = sessionmaker(bind=engine)
    with factory() as db:
        db.add(_queued_job())
        db.commit()

    def claim():
        with factory() as db:
            result = claim_class_sync_job(
                db,
                'job-1',
                now=datetime(2026, 9, 22, 5, 0, 0),
            )
            return result.id if result is not None else None

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: claim(), range(2)))

    assert sorted(value is not None for value in results) == [False, True]
    with factory() as db:
        persisted = db.get(AcademicClassSyncJob, 'job-1')
        assert persisted.status == 'running'
        assert persisted.started_at == datetime(2026, 9, 22, 5, 0, 0)
    engine.dispose()


def test_running_job_cannot_be_claimed_again():
    engine = create_engine('sqlite+pysqlite:///:memory:')
    _create_job_table(engine)
    with Session(engine) as db:
        job = _queued_job()
        job.status = 'running'
        job.started_at = datetime(2026, 9, 22, 4, 59, 0)
        db.add(job)
        db.commit()

        assert claim_class_sync_job(
            db,
            'job-1',
            now=datetime(2026, 9, 22, 5, 0, 0),
        ) is None
        db.refresh(job)
        assert job.started_at == datetime(2026, 9, 22, 4, 59, 0)
    engine.dispose()


def test_duplicate_delivery_for_running_job_never_calls_service(monkeypatch):
    engine = create_engine('sqlite+pysqlite:///:memory:')
    _create_job_table(engine)
    factory = sessionmaker(bind=engine)
    with factory() as db:
        job = _queued_job('job-running')
        job.status = 'running'
        job.started_at = datetime(2026, 9, 22, 5, 0, 0)
        db.add(job)
        db.commit()

    calls = []
    monkeypatch.setattr(worker, 'SessionLocal', factory)
    monkeypatch.setattr(
        AcademicService,
        'assert_can_access_class',
        lambda self, user, class_id: None,
    )
    monkeypatch.setattr(
        AcademicSubjectDeliveryService,
        'assert_cms_workflow_allowed_for_class',
        lambda self, class_id, *, job_type: None,
    )
    monkeypatch.setattr(
        AcademicService,
        'sync_class_learning_insight',
        lambda self, user, class_id, **kwargs: calls.append(class_id) or {'ok': True},
    )

    result = worker.academic_class_sync_task.run('job-running')

    assert calls == []
    assert result == {
        'ok': True,
        'skipped': True,
        'reason': 'not_queued',
        'status': 'running',
    }
    with factory() as db:
        assert db.get(AcademicClassSyncJob, 'job-running').status == 'running'
    engine.dispose()
