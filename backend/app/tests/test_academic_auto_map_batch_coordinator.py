from __future__ import annotations

from datetime import datetime, timedelta
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.routes.academic import reconcile_bulk_operation_jobs
from app.core.config import settings
from app.models.academic import (
    AcademicBulkOperationJob,
    AcademicClass,
    AcademicClassSyncJob,
    AcademicTerm,
)
from app.services.academic.batch_coordinator import plan_batch_dispatch
from app.services.academic_service import AcademicService


NOW = datetime(2026, 9, 12, 12, 0, 0)


def _child(class_id: str, status: str):
    return SimpleNamespace(class_id=class_id, status=status)


def test_empty_batch_dispatches_only_the_four_slot_window():
    assert settings.academic_bulk_sync_dispatch_window == 4

    plan = plan_batch_dispatch(
        [f'class-{index}' for index in range(1, 16)],
        [],
        window=settings.academic_bulk_sync_dispatch_window,
    )

    assert plan.dispatch_class_ids == [f'class-{index}' for index in range(1, 5)]
    assert plan.window == 4
    assert plan.active_count == 0
    assert plan.finished is False


def test_redelivery_never_selects_a_class_that_already_has_a_child():
    targets = [f'class-{index}' for index in range(1, 7)]
    children = [
        _child('class-1', 'completed'),
        _child('class-2', 'running'),
        _child('class-3', 'queued'),
    ]

    first = plan_batch_dispatch(targets, children, window=4)
    redelivery = plan_batch_dispatch(targets, children, window=4)

    assert first.dispatch_class_ids == ['class-4', 'class-5']
    assert redelivery.dispatch_class_ids == first.dispatch_class_ids
    assert set(first.dispatch_class_ids).isdisjoint({'class-1', 'class-2', 'class-3'})


def test_failed_child_is_terminal_and_does_not_stop_next_class():
    plan = plan_batch_dispatch(
        ['class-1', 'class-2', 'class-3'],
        [_child('class-1', 'failed'), _child('class-2', 'completed')],
        window=2,
    )

    assert plan.failed_count == 1
    assert plan.completed_count == 1
    assert plan.dispatch_class_ids == ['class-3']
    assert plan.finished is False


def test_parent_finishes_only_when_all_targets_are_terminal():
    plan = plan_batch_dispatch(
        ['class-1', 'class-2'],
        [_child('class-1', 'completed'), _child('class-2', 'failed')],
        window=4,
    )

    assert plan.dispatch_class_ids == []
    assert plan.terminal_count == 2
    assert plan.finished is True


def _batch_engine():
    engine = create_engine('sqlite+pysqlite:///:memory:')
    for model in (AcademicTerm, AcademicClass, AcademicBulkOperationJob, AcademicClassSyncJob):
        model.__table__.create(engine)
    return engine


def test_live_child_extends_stale_parent_lease():
    engine = _batch_engine()
    with Session(engine) as db:
        parent = AcademicBulkOperationJob(
            id='parent-1',
            job_type='subject_auto_map_all_sync',
            status='running',
            updated_at=NOW - timedelta(seconds=settings.academic_bulk_sync_stale_seconds + 1),
        )
        child = AcademicClassSyncJob(
            id='child-1',
            job_type='full_cms_sync',
            status='running',
            class_id='class-1',
            parent_job_id=parent.id,
            updated_at=NOW,
        )
        db.add_all([parent, child])
        db.commit()

        assert reconcile_bulk_operation_jobs(db, now=NOW) == 0
        db.refresh(parent)
        assert parent.status == 'running'
    engine.dispose()


def test_stale_child_and_parent_are_both_failed_for_retry():
    engine = _batch_engine()
    with Session(engine) as db:
        old = NOW - timedelta(seconds=settings.academic_class_sync_stale_seconds + 1)
        parent = AcademicBulkOperationJob(
            id='parent-1',
            job_type='subject_auto_map_all_sync',
            status='running',
            updated_at=old,
        )
        child = AcademicClassSyncJob(
            id='child-1',
            job_type='full_cms_sync',
            status='running',
            class_id='class-1',
            parent_job_id=parent.id,
            updated_at=old,
        )
        db.add_all([parent, child])
        db.commit()

        assert reconcile_bulk_operation_jobs(db, now=NOW) == 1
        db.refresh(parent)
        db.refresh(child)
        assert parent.status == 'failed'
        assert child.status == 'failed'
        assert parent.result_json['code'] == 'CELERY_JOB_ORPHANED'
        assert child.result_json['code'] == 'CELERY_JOB_ORPHANED'
    engine.dispose()


def test_bulk_reconciliation_does_not_expire_unrelated_long_running_job_types():
    engine = _batch_engine()
    with Session(engine) as db:
        export_job = AcademicBulkOperationJob(
            id='udemy-export-1',
            job_type='udemy_progress_export',
            status='running',
            updated_at=NOW - timedelta(hours=2),
        )
        db.add(export_job)
        db.commit()

        assert reconcile_bulk_operation_jobs(db, now=NOW) == 0
        db.refresh(export_job)
        assert export_job.status == 'running'
    engine.dispose()


def test_map_only_job_finishes_without_provisioning_children_or_legacy_parent_finish(
    monkeypatch,
):
    from app import worker

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
    frozen_scope = {
        'policy_version': 'academic-daily/v2',
        'scope_key': 'poly:term-1',
        'scope_hash': 'scope-hash-1',
        'term_id': 'term-1',
        'branch': 'poly',
        'campuses': ['hn'],
        'class_ids': [],
        'class_to_campus': {},
    }
    with factory() as db:
        db.add(AcademicTerm(
            id='term-1',
            term_code='FA26',
            term_name='Fall 2026',
            branch='poly',
            active=True,
        ))
        db.add(AcademicBulkOperationJob(
            id='scope-parent-1',
            job_type='academic_daily_provision_scope',
            status='queued',
            request_json={
                'scope_hash': frozen_scope['scope_hash'],
                'frozen_scope': frozen_scope,
            },
            result_json={},
        ))
        db.add(AcademicBulkOperationJob(
            id='map-job-1',
            parent_job_id='scope-parent-1',
            job_type='subject_auto_map_all_sync',
            status='queued',
            term_id='term-1',
            branch='poly',
            request_json={
                'operation': 'map_only',
                'scheduled': True,
                'scheduled_parent_job_id': 'scope-parent-1',
                'scheduled_scope_contract': {
                    'scope_hash': frozen_scope['scope_hash'],
                },
                'frozen_scope': frozen_scope,
                'approved_class_ids': [],
                'approved_subject_ids': [],
                'term_id': 'term-1',
                'branch': 'poly',
                'requester_context': {
                    'user_id': 'academic-daily-scheduler',
                    'username': 'academic-daily-scheduler',
                    'role': 'admin',
                    'permissions': [],
                    'authenticated_admin_claims': {'ai_system_admin': True},
                },
            },
            result_json={},
        ))
        db.commit()

    monkeypatch.setattr(worker, 'SessionLocal', factory)
    monkeypatch.setattr(
        AcademicService,
        'auto_map_subject_courses_for_snapshot',
        lambda self, *args, **kwargs: {
            'class_ids': [],
            'subject_mapped': 1,
            'subject_already_mapped': 0,
            'subject_failed': 0,
        },
    )

    result = worker.academic_subject_auto_map_all_sync_task.run('map-job-1')

    assert result['ok'] is True
    assert result['phase'] == 'finished'
    with factory() as db:
        job = db.get(AcademicBulkOperationJob, 'map-job-1')
        parent = db.get(AcademicBulkOperationJob, 'scope-parent-1')
        assert job.status == 'completed'
        assert parent.status == 'queued'
        assert db.query(AcademicClassSyncJob).count() == 0
    engine.dispose()


def test_scheduled_map_only_accepts_mapped_subset_and_persists_real_failure(monkeypatch):
    from app import worker

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
    frozen_scope = {
        'policy_version': 'academic-daily/v2',
        'scope_key': 'poly:term-1',
        'scope_hash': 'scope-hash-subset',
        'term_id': 'term-1',
        'branch': 'poly',
        'campuses': ['hn'],
        'class_ids': ['class-1', 'class-2'],
        'class_to_campus': {'class-1': 'hn', 'class-2': 'hn'},
    }
    with factory() as db:
        db.add(AcademicTerm(
            id='term-1', term_code='FA26', term_name='Fall 2026', branch='poly', active=True,
        ))
        db.add(AcademicBulkOperationJob(
            id='scope-parent-subset',
            job_type='academic_daily_provision_scope',
            status='queued',
            request_json={'scope_hash': frozen_scope['scope_hash'], 'frozen_scope': frozen_scope},
            result_json={},
        ))
        db.add(AcademicBulkOperationJob(
            id='map-job-subset',
            parent_job_id='scope-parent-subset',
            job_type='subject_auto_map_all_sync',
            status='queued',
            term_id='term-1',
            branch='poly',
            request_json={
                'operation': 'map_only',
                'scheduled': True,
                'scheduled_parent_job_id': 'scope-parent-subset',
                'scheduled_scope_contract': {'scope_hash': frozen_scope['scope_hash']},
                'frozen_scope': frozen_scope,
                'approved_class_ids': ['class-1', 'class-2'],
                'approved_subject_ids': ['subject-1', 'subject-2'],
                'term_id': 'term-1',
                'branch': 'poly',
                'requester_context': {
                    'user_id': 'academic-daily-scheduler',
                    'username': 'academic-daily-scheduler',
                    'role': 'admin',
                    'permissions': [],
                    'authenticated_admin_claims': {'ai_system_admin': True},
                },
            },
            result_json={},
        ))
        db.commit()

    monkeypatch.setattr(worker, 'SessionLocal', factory)
    monkeypatch.setattr(
        AcademicService,
        'auto_map_subject_courses_for_snapshot',
        lambda self, *args, **kwargs: {
            'approved_class_ids': ['class-1', 'class-2'],
            'mapped_class_ids': ['class-1'],
            'failed_class_ids': ['class-2'],
            'class_ids': ['class-1'],
            'subject_mapped': 1,
            'subject_already_mapped': 0,
            'subject_failed': 1,
            'subject_results': [{
                'subject_id': 'subject-2',
                'subject_code': 'SOA102',
                'class_ids': ['class-2'],
                'ok': False,
                'status': 'no_candidate',
                'message': 'No CMS course candidate',
            }],
        },
    )

    result = worker.academic_subject_auto_map_all_sync_task.run('map-job-subset')

    assert result['ok'] is False
    assert result['mapped_class_ids'] == ['class-1']
    assert result['failed_class_ids'] == ['class-2']
    with factory() as db:
        job = db.get(AcademicBulkOperationJob, 'map-job-subset')
        assert job.status == 'failed'
        assert 'SOA102' in job.error_message
        assert 'No CMS course candidate' in job.error_message
    engine.dispose()


def test_scheduled_map_only_resumes_prepared_dispatching_state(monkeypatch):
    from app import worker

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
    frozen_scope = {
        'policy_version': 'academic-daily/v2',
        'scope_key': 'poly:term-1',
        'scope_hash': 'scope-hash-resume',
        'term_id': 'term-1',
        'branch': 'poly',
        'campuses': ['hn'],
        'class_ids': ['class-1'],
        'class_to_campus': {'class-1': 'hn'},
    }
    with factory() as db:
        db.add(AcademicTerm(
            id='term-1', term_code='FA26', term_name='Fall 2026', branch='poly', active=True,
        ))
        db.add(AcademicBulkOperationJob(
            id='scope-parent-resume',
            job_type='academic_daily_provision_scope',
            status='queued',
            request_json={'scope_hash': frozen_scope['scope_hash'], 'frozen_scope': frozen_scope},
            result_json={},
        ))
        db.add(AcademicBulkOperationJob(
            id='map-job-resume',
            parent_job_id='scope-parent-resume',
            job_type='subject_auto_map_all_sync',
            status='running',
            term_id='term-1',
            branch='poly',
            request_json={
                'operation': 'map_only',
                'scheduled': True,
                'scheduled_parent_job_id': 'scope-parent-resume',
                'scheduled_scope_contract': {'scope_hash': frozen_scope['scope_hash']},
                'frozen_scope': frozen_scope,
                'approved_class_ids': ['class-1'],
                'approved_subject_ids': ['subject-1'],
                'term_id': 'term-1',
                'branch': 'poly',
            },
            result_json={
                'phase': 'dispatching',
                'target_class_ids': ['class-1'],
                'failed_class_ids': [],
                'failed_class_count': 0,
                'scope_blocked_class_count': 0,
                'approved_class_count': 1,
                'subject_failed': 0,
            },
        ))
        db.commit()

    monkeypatch.setattr(worker, 'SessionLocal', factory)
    monkeypatch.setattr(
        AcademicService,
        'auto_map_subject_courses_for_snapshot',
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError('prepared state must not remap')
        ),
    )

    result = worker.academic_subject_auto_map_all_sync_task.run('map-job-resume')

    assert result['ok'] is True
    assert result['phase'] == 'finished'
    assert result['frozen_class_ids'] == ['class-1']
    with factory() as db:
        job = db.get(AcademicBulkOperationJob, 'map-job-resume')
        assert job.status == 'completed'

    engine.dispose()


def test_auto_map_scope_validation_rejects_any_class_outside_frozen_scope():
    from app import worker

    with pytest.raises(PermissionError, match='outside its frozen parent scope'):
        worker._validated_auto_map_class_sets(
            {
                'mapped_class_ids': ['class-1', 'class-outside'],
                'failed_class_ids': [],
            },
            {'class-1', 'class-2'},
        )
