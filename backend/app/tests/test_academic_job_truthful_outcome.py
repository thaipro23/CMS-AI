from datetime import datetime

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app import worker
from app.models.academic import AcademicClassSyncJob
from app.services.academic.job_outcome import (
    ClassSyncOutcomeError,
    automatic_retry_allowed,
    evaluate_class_sync_result,
)
from app.services.academic.subject_delivery import AcademicSubjectDeliveryService
from app.services.academic_service import AcademicService


def test_one_success_and_ninety_nine_enrollment_failures_is_not_success():
    evaluation = evaluate_class_sync_result(
        'cms_enrollment_sync',
        {
            'ok': True,
            'total': 100,
            'processed': 100,
            'updated': 1,
            'verified': 1,
            'counts': {'enrolled': 1, 'unknown': 99},
            'teachers': {
                'total': 0,
                'processed': 0,
                'updated': 0,
                'verified': 0,
                'counts': {},
            },
        },
    )

    assert evaluation.ok is False
    assert evaluation.counts == {
        'target_count': 100,
        'eligible_count': 100,
        'succeeded_count': 1,
        'skipped_count': 0,
        'failed_count': 99,
    }


def test_mapping_discovery_failure_with_zero_children_is_not_empty_success():
    evaluation = evaluate_class_sync_result(
        'full_cms_sync',
        {
            'ok': True,
            'status': 'mapping_required_no_cms_user_created',
            'mapping': {
                'ok': False,
                'status': 'course_not_found',
                'message': 'no course',
            },
            'cms_users': None,
            'enrollment': None,
            'learning': None,
            'counts': {'roster_total': 0},
        },
    )

    assert evaluation.ok is False
    assert evaluation.counts['target_count'] == 1
    assert evaluation.counts['failed_count'] == 1
    assert evaluation.failures[0]['stage'] == 'mapping'


def test_only_read_only_learning_sync_can_retry_transient_errors():
    assert automatic_retry_allowed('learning_sync', transient=True) is True
    assert automatic_retry_allowed('cms_sync_check', transient=True) is False
    assert automatic_retry_allowed('cms_enrollment_sync', transient=True) is False
    assert automatic_retry_allowed('full_cms_sync', transient=True) is False
    assert automatic_retry_allowed('learning_sync', transient=False) is False


def _factory_with_job(job_type):
    engine = create_engine('sqlite+pysqlite:///:memory:')
    AcademicClassSyncJob.__table__.create(engine)
    factory = sessionmaker(bind=engine)
    with factory() as db:
        db.add(AcademicClassSyncJob(
            id=f'job-{job_type}',
            job_type=job_type,
            status='queued',
            class_id='class-1',
            requested_by='operator-1',
            force=False,
            limit=500,
            progress_current=0,
            progress_total=100,
            request_json={
                'approved_class_id': 'class-1',
                'auto_map_course': True,
                'sync_learning': False,
                'requester_context': {
                    'user_id': 'operator-1',
                    'username': 'operator-1',
                    'role': 'admin',
                    'permissions': ['academic.manage'],
                    'authenticated_admin_claims': {'is_superuser': True},
                },
            },
            result_json={},
        ))
        db.commit()
    return engine, factory


def _allow_worker_scope(monkeypatch, factory):
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


def test_worker_marks_partial_enrollment_result_failed(monkeypatch):
    engine, factory = _factory_with_job('cms_enrollment_sync')
    _allow_worker_scope(monkeypatch, factory)
    monkeypatch.setattr(
        AcademicService,
        'sync_class_course_enrollment',
        lambda self, user, class_id, **kwargs: {
            'ok': True,
            'total': 100,
            'processed': 100,
            'updated': 1,
            'verified': 1,
            'counts': {'enrolled': 1, 'unknown': 99},
            'teachers': {'total': 0, 'updated': 0, 'counts': {}},
        },
    )

    with pytest.raises(ClassSyncOutcomeError):
        worker.academic_class_sync_task.run('job-cms_enrollment_sync')

    with factory() as db:
        job = db.get(AcademicClassSyncJob, 'job-cms_enrollment_sync')
        assert job.status == 'failed'
        assert job.result_json['code'] == 'CLASS_SYNC_INCOMPLETE'
        assert job.result_json['outcome_counts']['failed_count'] == 99
    engine.dispose()


def test_mutation_timeout_requires_reconciliation_and_is_not_retried(monkeypatch):
    engine, factory = _factory_with_job('full_cms_sync')
    _allow_worker_scope(monkeypatch, factory)
    monkeypatch.setattr(
        AcademicService,
        'sync_class_full_cms_flow',
        lambda self, user, class_id, **kwargs: (_ for _ in ()).throw(
            TimeoutError('ambiguous enrollment timeout')
        ),
    )

    with pytest.raises(TimeoutError, match='ambiguous enrollment timeout'):
        worker.academic_class_sync_task.run('job-full_cms_sync')

    with factory() as db:
        job = db.get(AcademicClassSyncJob, 'job-full_cms_sync')
        assert job.status == 'failed'
        assert job.result_json['code'] == 'CLASS_SYNC_RECONCILE_REQUIRED'
        assert job.result_json['reconcile_required'] is True
        assert job.result_json['automatic_retry_allowed'] is False
        assert job.result_json['failure_class'] == 'transient_after_mutation'
        assert job.finished_at is not None
    engine.dispose()


def test_stage_managed_learning_failure_is_terminal_without_celery_retry(monkeypatch):
    engine, factory = _factory_with_job('learning_sync')
    with factory() as db:
        job = db.get(AcademicClassSyncJob, 'job-learning_sync')
        job.request_json = {
            **job.request_json,
            'stage_managed_retries': True,
            'attempt_no': 0,
            'logical_target_key': 'score_update:poly:term-1:class-1',
        }
        db.add(job)
        db.commit()
    _allow_worker_scope(monkeypatch, factory)
    monkeypatch.setattr(
        AcademicService,
        'sync_class_learning_insight',
        lambda self, user, class_id, **kwargs: (_ for _ in ()).throw(
            TimeoutError('temporary score timeout')
        ),
    )
    retry_calls = []
    monkeypatch.setattr(
        worker.academic_class_sync_task,
        'retry',
        lambda **kwargs: retry_calls.append(kwargs),
    )

    with pytest.raises(TimeoutError, match='temporary score timeout'):
        worker.academic_class_sync_task.run('job-learning_sync')

    with factory() as db:
        job = db.get(AcademicClassSyncJob, 'job-learning_sync')
        assert job.status == 'failed'
        assert job.result_json['automatic_retry_allowed'] is False
        assert retry_calls == []
    engine.dispose()
