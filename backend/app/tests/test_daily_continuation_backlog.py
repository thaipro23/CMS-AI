from datetime import datetime, timedelta
from copy import deepcopy
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.models.academic import AcademicBulkOperationJob, AcademicClassSyncJob
from app.services.academic import daily_academic_pipeline as runtime
from app.services.academic.scheduled_parent import (recover_due_parent_continuations, publish_parent_continuation, ContinuationPublishError)
from app.tests.test_academic_daily_pipeline_recovery import FakeCelery

@pytest.fixture
def factory(monkeypatch):
    engine = create_engine('sqlite+pysqlite:///:memory:')
    AcademicBulkOperationJob.__table__.create(engine)
    AcademicClassSyncJob.__table__.create(engine)
    factory = sessionmaker(bind=engine)
    monkeypatch.setattr(runtime, 'SessionLocal', factory)
    yield factory
    engine.dispose()

def seed(db, now, *, attempts=5, status='running', code=None, age=1):
    state = {'phase': 'score_update', 'stage_round': 2, 'stage_target_keys': ['class-1'],
             'attempts_by_stage': {'score_update': {'2': {'class-1': 'score-2'}}},
             'artifacts': {'kept': 'file-1'},
             'continuation': {'status': 'dispatched', 'attempt_count': attempts,
                 'due_at': (now-timedelta(seconds=1)).isoformat(),
                 'task_name': runtime.DAILY_ROOT_TASK, 'args': ['root'],
                 'queue': 'sync-bulk', 'countdown': 0, 'last_error': None}}
    if code:
        state['code'] = code
        state['continuation']['status'] = 'failed'
    root = AcademicBulkOperationJob(id='root', job_type=runtime.DAILY_ROOT_JOB_TYPE, status=status,
        created_at=now-timedelta(hours=age), progress_current=60,
        idempotency_key='academic-daily:v2:2026-10-07',
        request_json={'run_date_vn': '2026-10-07', 'scopes': []}, result_json=state,
        error_message='Scheduled continuation recovery limit exceeded.' if code else None,
        finished_at=now if code else None)
    db.add_all([root, AcademicBulkOperationJob(id='scope',
        job_type='academic_daily_score-report_scope', parent_job_id='root', status='running',
        progress_current=45, request_json={}, result_json={}),
        AcademicClassSyncJob(id='score-2', job_type='learning_sync', status='completed',
            class_id='class-1', parent_job_id='scope',
            request_json={'daily_root_job_id': 'root'}, result_json={})])
    db.commit()
    return root

def test_successfully_queued_continuations_do_not_exhaust_recovery(factory):
    now = datetime.utcnow()
    with factory() as db:
        seed(db, now)
        for _ in range(8):
            result = recover_due_parent_continuations(db, publisher=lambda **kwargs: 'queued-task',
                job_types={runtime.DAILY_ROOT_JOB_TYPE}, now=now, max_attempts=5, max_runtime_seconds=86400)
            db.expire_all()
            root = db.get(AcademicBulkOperationJob, 'root')
            assert root.status == 'running'
            assert result['failed'] == 0 and result['republished'] == 1
            assert root.result_json['continuation']['publish_failure_count'] == 0
            state = deepcopy(root.result_json)
            state['continuation']['due_at'] = (now-timedelta(seconds=1)).isoformat()
            root.result_json = state
            db.commit()

def test_runtime_failure_propagates_to_scope_without_resetting_child(factory):
    now = datetime.utcnow()
    with factory() as db:
        seed(db, now, attempts=1, age=25)
    result = runtime.recover_daily_academic_pipeline(FakeCelery(), now=now)
    assert result['failed'] == 1
    with factory() as db:
        assert db.get(AcademicBulkOperationJob, 'root').status == 'failed'
        scope = db.get(AcademicBulkOperationJob, 'scope')
        assert scope.status == 'failed'
        assert scope.result_json['root_failure_code'] == 'pipeline_runtime_exceeded'
        assert db.get(AcademicClassSyncJob, 'score-2').status == 'completed'

def test_resume_keeps_round_artifact_and_completed_child(factory):
    now = datetime.utcnow()
    with factory() as db:
        seed(db, now, status='failed', code='continuation_recovery_exhausted')
    celery = FakeCelery()
    result = runtime.resume_daily_academic_pipeline(celery, 'root', now=now, actor='vynnk')
    assert result['ok'] is True
    assert celery.sent[0][0] == runtime.DAILY_ROOT_TASK
    assert celery.sent[0][2]['queue'] == 'sync-fast'
    with factory() as db:
        root = db.get(AcademicBulkOperationJob, 'root')
        assert root.status == 'running' and root.finished_at is None
        assert root.result_json['stage_round'] == 2
        assert root.result_json['attempts_by_stage']['score_update']['2'] == {'class-1': 'score-2'}
        assert root.result_json['artifacts'] == {'kept': 'file-1'}
        assert db.query(AcademicClassSyncJob).count() == 1
        assert db.get(AcademicClassSyncJob, 'score-2').status == 'completed'
    again = runtime.resume_daily_academic_pipeline(celery, 'root', now=now)
    assert again['status'] == 'already_running'
    assert len(celery.sent) == 1

@pytest.mark.parametrize('code,age', [('score_update_exhausted', 1), ('continuation_recovery_exhausted', 25)])
def test_resume_refuses_business_failure_or_expired_root(factory, code, age):
    now = datetime.utcnow()
    with factory() as db:
        seed(db, now, status='failed', code=code, age=age)
    celery = FakeCelery()
    result = runtime.resume_daily_academic_pipeline(celery, 'root', now=now)
    assert result['ok'] is False and not celery.sent
    with factory() as db:
        assert db.get(AcademicBulkOperationJob, 'root').status == 'failed'


def test_broker_failures_still_exhaust_after_five_attempts(factory):
    now = datetime.utcnow()
    calls = []
    def fail(**kwargs):
        calls.append(kwargs)
        raise ConnectionError('Redis unavailable')
    with factory() as db:
        root = seed(db, now, attempts=1)
        for attempt in range(5):
            with pytest.raises(ContinuationPublishError):
                publish_parent_continuation(db, root, publisher=fail, task_name=runtime.DAILY_ROOT_TASK,
                                            args=['root'], queue='sync-fast', now=now)
            assert root.result_json['continuation']['publish_failure_count'] == attempt+1
        result = recover_due_parent_continuations(db, publisher=fail,
            job_types={runtime.DAILY_ROOT_JOB_TYPE}, now=now+timedelta(minutes=10))
        assert result['failed'] == 1
        assert root.status == 'failed'
        assert len(calls) == 5


def test_watchdog_does_not_republish_before_queue_visibility_lease(factory):
    now = datetime.utcnow()
    with factory() as db:
        root = seed(db, now)
        state = deepcopy(root.result_json)
        state['continuation']['dispatched_at'] = (now-timedelta(minutes=5)).isoformat()
        root.result_json = state
        db.commit()
    celery = FakeCelery()
    result = runtime.recover_daily_academic_pipeline(celery, now=now)
    assert result['republished'] == 0
    assert not celery.sent
    with factory() as db:
        assert db.get(AcademicBulkOperationJob, 'root').status == 'running'


def test_resume_refuses_newer_daily_run(factory):
    now = datetime.utcnow()
    with factory() as db:
        seed(db, now, status='failed', code='continuation_recovery_exhausted')
        db.add(AcademicBulkOperationJob(id='newer', job_type=runtime.DAILY_ROOT_JOB_TYPE,
            status='completed', request_json={'run_date_vn': '2026-10-08'}, result_json={}))
        db.commit()
    celery = FakeCelery()
    result = runtime.resume_daily_academic_pipeline(celery, 'root', now=now)
    assert result['code'] == 'newer_or_active_daily_root_exists'
    assert not celery.sent


def test_old_delivery_keeps_terminal_root_diagnostics(factory):
    now = datetime.utcnow()
    with factory() as db:
        root = seed(db, now, status='failed', code='continuation_recovery_exhausted')
        previous = deepcopy(root.result_json)
    runtime.run_daily_academic_pipeline(FakeCelery(), 'root')
    with factory() as db:
        assert db.get(AcademicBulkOperationJob, 'root').result_json == previous


def test_redis_busy_prevents_watchdog_and_worker_state_changes(factory, monkeypatch):
    now = datetime.utcnow()
    class BusyLease:
        def acquire(self, **kwargs): return False
    class Redis:
        def lock(self, *args, **kwargs): return BusyLease()
        def close(self): pass
    monkeypatch.setattr(runtime, '_daily_redis_client', Redis)
    with factory() as db:
        root = seed(db, now)
        previous = deepcopy(root.result_json)
    celery = FakeCelery()
    assert runtime.recover_daily_academic_pipeline(celery, now=now)['status'] == 'coordinator_busy'
    assert runtime.run_daily_academic_pipeline(celery, 'root')['status'] == 'coordinator_busy'
    with factory() as db:
        assert db.get(AcademicBulkOperationJob, 'root').result_json == previous
    assert not celery.sent


def test_runtime_limit_applies_even_when_delivery_lease_is_not_due(factory):
    now = datetime.utcnow()
    with factory() as db:
        root = seed(db, now, attempts=1, age=25)
        state = deepcopy(root.result_json)
        state['continuation']['due_at'] = (now+timedelta(hours=1)).isoformat()
        root.result_json = state
        db.commit()
    result = runtime.recover_daily_academic_pipeline(FakeCelery(), now=now)
    assert result['failed'] == 1
    with factory() as db:
        assert db.get(AcademicBulkOperationJob, 'scope').status == 'failed'


def test_direct_publish_exhaustion_marks_scope_failed(factory):
    now = datetime.utcnow()
    with factory() as db:
        root = seed(db, now)
        state = deepcopy(root.result_json)
        state['continuation']['publish_failure_count'] = 5
        root.result_json = state
        db.commit()
        with pytest.raises(ContinuationPublishError):
            runtime._publish_root_continuation(FakeCelery(), db, root)
        assert root.status == 'failed'
        assert db.get(AcademicBulkOperationJob, 'scope').status == 'failed'


def test_scheduler_busy_requeues_start_instead_of_losing_daily_run(factory, monkeypatch):
    class BusyLease:
        def acquire(self, **kwargs): return False
    class Redis:
        def lock(self, *args, **kwargs): return BusyLease()
        def close(self): pass
    monkeypatch.setattr(runtime, '_daily_redis_client', Redis)
    celery = FakeCelery()
    result = runtime.start_daily_academic_pipeline(celery)
    assert result['status'] == 'coordinator_busy'
    assert len(celery.sent) == 1
    assert celery.sent[0][0] == runtime.DAILY_START_TASK
    assert celery.sent[0][2]['queue'] == 'sync-fast'
    assert celery.sent[0][2]['countdown'] == 30


def test_resume_preserves_durable_intent_when_broker_is_unavailable(factory):
    now = datetime.utcnow()
    with factory() as db:
        seed(db, now, status='failed', code='continuation_recovery_exhausted')
    class FailingCelery:
        def send_task(self, *args, **kwargs):
            raise ConnectionError('broker unavailable')
    result = runtime.resume_daily_academic_pipeline(FailingCelery(), 'root', now=now)
    assert result['status'] == 'dispatch_pending'
    with factory() as db:
        root = db.get(AcademicBulkOperationJob, 'root')
        assert root.status == 'running'
        assert root.result_json['stage_round'] == 2
        assert root.result_json['continuation']['publish_failure_count'] == 1
        assert db.get(AcademicClassSyncJob, 'score-2').status == 'completed'
    recovered = runtime.recover_daily_academic_pipeline(FakeCelery(), now=now+timedelta(minutes=1))
    assert recovered['republished'] == 1


def test_resume_reopens_only_scope_failed_by_root_transport_error(factory):
    now = datetime.utcnow()
    with factory() as db:
        root = seed(db, now, status='failed', code='continuation_recovery_exhausted')
        scope = db.get(AcademicBulkOperationJob, 'scope')
        scope.status = 'failed'
        scope.error_message = root.error_message
        scope.result_json = {'root_failure_code': 'continuation_recovery_exhausted'}
        db.add(AcademicBulkOperationJob(id='provision', parent_job_id='root', status='completed',
            job_type='academic_daily_provision_scope', request_json={}, result_json={}))
        db.commit()
    result = runtime.resume_daily_academic_pipeline(FakeCelery(), 'root', now=now)
    assert result['ok']
    with factory() as db:
        assert db.get(AcademicBulkOperationJob, 'scope').status == 'running'
        assert db.get(AcademicBulkOperationJob, 'provision').status == 'completed'


def test_watchdog_repairs_scopes_of_already_failed_root(factory):
    now = datetime.utcnow()
    with factory() as db:
        seed(db, now, status='failed', code='continuation_recovery_exhausted')
    celery = FakeCelery()
    runtime.recover_daily_academic_pipeline(celery, now=now)
    assert not celery.sent
    with factory() as db:
        assert db.get(AcademicBulkOperationJob, 'scope').status == 'failed'
        assert db.get(AcademicClassSyncJob, 'score-2').status == 'completed'


def test_legacy_mixed_queue_wait_and_one_broker_error_does_not_exhaust(factory):
    now = datetime.utcnow()
    with factory() as db:
        root = seed(db, now)
        state = deepcopy(root.result_json)
        state['continuation'].update(status='dispatch_pending', last_error='broker offline',
                                     last_error_class='ConnectionError')
        root.result_json = state
        db.commit()
        result = recover_due_parent_continuations(db, publisher=lambda **kw: 'new-task',
            job_types={runtime.DAILY_ROOT_JOB_TYPE}, now=now, max_runtime_seconds=86400)
        assert result['republished'] == 1
        assert root.status == 'running'


def test_advisory_unlock_rolls_back_failed_transaction_first():
    from types import SimpleNamespace
    class FailedSession:
        aborted = True
        released = False
        def get_bind(self): return SimpleNamespace(dialect=SimpleNamespace(name='postgresql'))
        def rollback(self): self.aborted = False
        def execute(self, *args):
            if self.aborted: raise RuntimeError('current transaction is aborted')
            self.released = True
            return SimpleNamespace(scalar=lambda: True)
        def commit(self): pass
    db = FailedSession()
    runtime._release_daily_root_db_lock(db, 'coordinator')
    assert db.released is True
