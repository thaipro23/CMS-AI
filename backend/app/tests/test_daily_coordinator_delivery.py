from copy import deepcopy
from datetime import datetime, timedelta
from types import SimpleNamespace

import pytest
from celery import Celery
from celery.exceptions import Retry
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.models.academic import AcademicBulkOperationJob, AcademicClassSyncJob
from app.services.academic import daily_academic_pipeline as runtime
from app.services.academic.scheduled_parent import confirm_parent_continuation


@pytest.fixture
def database(tmp_path, monkeypatch):
    engine = create_engine(f"sqlite+pysqlite:///{tmp_path / 'delivery.sqlite'}")
    for model in (AcademicBulkOperationJob, AcademicClassSyncJob):
        model.__table__.create(engine)
    factory = sessionmaker(bind=engine)
    monkeypatch.setattr(runtime, 'SessionLocal', factory)
    owner = SimpleNamespace(locked=False)

    class Lease:
        def acquire(self, **kwargs):
            if owner.locked:
                return False
            owner.locked = True
            return True

        def release(self):
            owner.locked = False

    class Redis:
        def lock(self, *args, **kwargs):
            return Lease()

        def close(self):
            pass

    monkeypatch.setattr(runtime, '_daily_redis_client', Redis)
    yield factory, owner
    engine.dispose()


def seed(factory, *, failed=False):
    now = datetime.utcnow()
    with factory() as db:
        root = AcademicBulkOperationJob(
            id='root', job_type=runtime.DAILY_ROOT_JOB_TYPE,
            idempotency_key=runtime.daily_root_key(now.date().isoformat()),
            status='failed' if failed else 'running', progress_current=1,
            request_json={'run_date_vn': now.date().isoformat(), 'scopes': []},
            result_json={'phase': 'ap_sync', 'stage_round': 0, 'artifacts': {},
                         'code': 'continuation_recovery_exhausted' if failed else None,
                         'continuation': {
                             'status': 'failed' if failed else 'dispatched',
                             'attempt_count': 5, 'publish_failure_count': 0,
                             'due_at': (now - timedelta(seconds=1)).isoformat(),
                             'task_name': runtime.DAILY_ROOT_TASK, 'args': ['root'],
                             'queue': 'sync-fast', 'countdown': 0}},
        )
        db.add(root)
        db.commit()


class ImmediateConsumer:
    def __init__(self, factory, owner):
        self.factory, self.owner = factory, owner
        self.observed_locks = []
        self.sent = []

    def send_task(self, name, args=None, **options):
        self.sent.append((name, args, options))
        self.observed_locks.append(self.owner.locked)
        # Simulate a fast worker acknowledgement before send_task returns.
        # The dispatcher must never overwrite its confirmed state afterwards.
        if not self.owner.locked:
            with self.factory() as db:
                root = db.get(AcademicBulkOperationJob, args[0])
                confirm_parent_continuation(db, root, expected_task_name=name)
        return SimpleNamespace(id='delivered-task')


@pytest.mark.parametrize('operation', ['start', 'recover', 'resume', 'worker'])
def test_root_is_published_after_coordinator_unlock(database, monkeypatch, operation):
    factory, owner = database
    celery = ImmediateConsumer(factory, owner)
    if operation == 'start':
        scopes = [{'scope_key': f'{branch}:term', 'term_id': 'term',
                   'branch': branch} for branch in ('poly', 'ptcd')]
        monkeypatch.setattr(runtime, 'discover_daily_scopes', lambda db: scopes)
        runtime.start_daily_academic_pipeline(celery)
    else:
        seed(factory, failed=operation == 'resume')
        if operation == 'recover':
            runtime.recover_daily_academic_pipeline(celery)
        elif operation == 'resume':
            runtime.resume_daily_academic_pipeline(celery, 'root')
        else:
            # Isolate the external AP boundary; exercise the real root dispatch
            # and coordinator context, including a zero-countdown continuation.
            def stage(app, db, root, state):
                runtime._publish_root_continuation(app, db, root, countdown=0)
                return {'ok': True, 'status': 'waiting_stage'}
            monkeypatch.setattr(runtime, '_run_ap_stage', stage)
            runtime.run_daily_academic_pipeline(celery, 'root')

    assert celery.observed_locks == [False]
    with factory() as db:
        root = db.get(AcademicBulkOperationJob, celery.sent[0][1][0])
        assert root.result_json['continuation']['status'] == 'confirmed'


def test_registered_root_task_retries_lock_contention(database, monkeypatch):
    factory, owner = database
    seed(factory)
    owner.locked = True
    app = Celery('daily-contention', broker='memory://', backend='cache+memory://')
    runtime.register_daily_academic_pipeline_tasks(app)
    task = app.tasks[runtime.DAILY_ROOT_TASK]
    retries = []
    def retry(**kwargs):
        retries.append(kwargs)
        raise Retry('coordinator still owned')
    monkeypatch.setattr(task, 'retry', retry)
    with pytest.raises(Retry):
        task.run('root')
    assert retries[0]['countdown'] == 30
    assert task.max_retries is None
    with factory() as db:
        assert db.get(AcademicBulkOperationJob, 'root').progress_current == 1
        assert db.query(AcademicClassSyncJob).count() == 0


def test_deferred_broker_failures_keep_the_retry_budget(database):
    factory, owner = database
    seed(factory)
    class Offline:
        def send_task(self, *args, **options):
            assert not owner.locked
            raise ConnectionError('broker offline')
    now = datetime.utcnow()
    for i in range(2):
        result = runtime.recover_daily_academic_pipeline(
            Offline(), now=now + timedelta(minutes=i))
        assert result['republished'] == 0
        assert len(result['errors']) == 1
        with factory() as db:
            root = db.get(AcademicBulkOperationJob, 'root')
            assert root.result_json['continuation']['status'] == 'dispatch_pending'
            assert root.result_json['continuation']['publish_failure_count'] == i + 1
            assert root.result_json['stage_round'] == 0


def test_fast_new_intent_is_not_overwritten(database):
    factory, owner = database
    seed(factory)
    class Consumer(ImmediateConsumer):
        def send_task(self, name, args=None, **options):
            with factory() as db:
                root = db.get(AcademicBulkOperationJob, args[0])
                state = deepcopy(root.result_json)
                state['phase'] = 'course_mapping'
                state['continuation'] = {'status': 'confirmed', 'dispatch_id': 'new-intent'}
                root.result_json = state
                db.commit()
            return SimpleNamespace(id='old-delivery')
    runtime.recover_daily_academic_pipeline(Consumer(factory, owner))
    with factory() as db:
        root = db.get(AcademicBulkOperationJob, 'root')
        assert root.result_json['phase'] == 'course_mapping'
        assert root.result_json['continuation'] == {
            'status': 'confirmed', 'dispatch_id': 'new-intent'}


def test_expired_root_delivery_cannot_start_ap(database, monkeypatch):
    factory, owner = database
    seed(factory)
    with factory() as db:
        root = db.get(AcademicBulkOperationJob, 'root')
        root.created_at = datetime.utcnow() - timedelta(hours=25)
        db.add(AcademicBulkOperationJob(
            id='scope', parent_job_id='root', job_type='academic_daily_provision_scope',
            status='queued', request_json={}, result_json={}))
        db.commit()
    def ap(*args):
        pytest.fail('expired root must not dispatch AP')
    monkeypatch.setattr(runtime, '_run_ap_stage', ap)
    result = runtime.run_daily_academic_pipeline(ImmediateConsumer(factory, owner), 'root')
    assert result['status'] == 'failed'
    with factory() as db:
        root = db.get(AcademicBulkOperationJob, 'root')
        assert root.status == 'failed'
        assert root.result_json['code'] == 'pipeline_runtime_exceeded'
        assert db.get(AcademicBulkOperationJob, 'scope').status == 'failed'


def test_prepared_delivery_survives_coordinator_failure(database, monkeypatch):
    factory, owner = database
    seed(factory)
    with factory() as db:
        root = db.get(AcademicBulkOperationJob, 'root')
        state = deepcopy(root.result_json)
        state['continuation']['publish_failure_count'] = 2
        root.result_json = state
        db.commit()
    def stage(app, db, root, state):
        runtime._publish_root_continuation(app, db, root)
        raise RuntimeError('coordinator died before unlock')
    monkeypatch.setattr(runtime, '_run_ap_stage', stage)
    celery = ImmediateConsumer(factory, owner)
    with pytest.raises(RuntimeError, match='coordinator died'):
        runtime.run_daily_academic_pipeline(celery, 'root')
    assert not celery.sent
    assert not owner.locked
    with factory() as db:
        root = db.get(AcademicBulkOperationJob, 'root')
        intent = root.result_json['continuation']
        assert intent['status'] == 'dispatch_pending'
        assert intent['publish_failure_count'] == 0  # confirmation reset before stage
        assert datetime.fromisoformat(intent['due_at']) <= datetime.utcnow()
    result = runtime.recover_daily_academic_pipeline(celery)
    assert result['republished'] == 1
    assert celery.observed_locks == [False]
