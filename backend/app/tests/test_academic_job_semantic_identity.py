from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.api.routes import academic as academic_routes
from app.core.rbac import UserContext
from app.models.academic import AcademicClass, AcademicClassSyncJob
from app.services.academic.job_identity import (
    CLASS_SYNC_POLICY_VERSION,
    ClassSyncJobBlocked,
    choose_active_class_sync_job,
    class_sync_contract,
    class_sync_idempotency_key,
)
from app.services.academic.subject_delivery import AcademicSubjectDeliveryService
from app.services.academic_service import AcademicService
from app.worker import _enqueue_academic_class_sync_child_job


def _key(**overrides):
    values = {
        'class_id': ' class-01 ',
        'job_type': 'FULL_CMS_SYNC',
        'force': False,
        'limit': 500,
        'mode': None,
        'auto_map_course': True,
        'sync_learning': False,
        'parent_job_id': None,
        'origin': 'MANUAL',
        'policy_version': CLASS_SYNC_POLICY_VERSION,
    }
    values.update(overrides)
    return class_sync_idempotency_key(**values)


def _job(job_id, key, *, parent_job_id=None):
    return SimpleNamespace(
        id=job_id,
        idempotency_key=key if parent_job_id else None,
        parent_job_id=parent_job_id,
        request_json={'request_key': key},
    )


def test_contract_is_canonical_and_key_is_stable():
    contract = class_sync_contract(
        class_id=' class-01 ',
        job_type='FULL_CMS_SYNC',
        force=False,
        limit=500,
        mode=' ',
        auto_map_course=True,
        sync_learning=False,
        parent_job_id=' ',
        origin='MANUAL',
        policy_version=CLASS_SYNC_POLICY_VERSION,
    )

    assert contract == {
        'class_id': 'class-01',
        'job_type': 'full_cms_sync',
        'force': False,
        'limit': 500,
        'mode': None,
        'auto_map_course': True,
        'sync_learning': False,
        'parent_job_id': None,
        'origin': 'manual',
        'policy_version': CLASS_SYNC_POLICY_VERSION,
    }
    assert _key() == _key()
    assert _key().startswith('class-sync:v2:')


def test_every_operation_field_participates_in_semantic_identity():
    base = _key()
    variants = (
        {'class_id': 'class-02'},
        {'job_type': 'learning_sync'},
        {'force': True},
        {'limit': 499},
        {'mode': 'missing_only'},
        {'auto_map_course': False},
        {'sync_learning': True},
        {'parent_job_id': 'parent-01', 'origin': 'scheduled'},
        {'origin': 'scheduled'},
        {'policy_version': 'class-sync/v3'},
    )

    assert all(_key(**variant) != base for variant in variants)


def test_exact_active_fingerprint_is_reused_only_without_a_blocker():
    requested = _key()
    exact = _job('job-exact', requested)

    decision = choose_active_class_sync_job([exact], requested_key=requested)

    assert decision.reusable is exact
    assert decision.blocker is None


def test_different_active_fingerprint_is_an_explicit_blocker():
    requested = _key(force=True)
    active = _job('job-active', _key(force=False))

    decision = choose_active_class_sync_job([active], requested_key=requested)

    assert decision.reusable is None
    assert decision.blocker is active


def test_scheduled_child_never_adopts_manual_or_foreign_parent_job():
    desired = _key(
        parent_job_id='parent-own',
        origin='scheduled',
    )
    manual = _job('job-manual', _key())
    foreign = _job(
        'job-foreign',
        _key(parent_job_id='parent-other', origin='scheduled'),
        parent_job_id='parent-other',
    )

    manual_decision = choose_active_class_sync_job([manual], requested_key=desired)
    foreign_decision = choose_active_class_sync_job([foreign], requested_key=desired)

    assert manual_decision.reusable is None
    assert manual_decision.blocker is manual
    assert foreign_decision.reusable is None
    assert foreign_decision.blocker is foreign


def test_inconsistent_active_set_with_exact_and_foreign_job_fails_closed():
    requested = _key()
    exact = _job('job-exact', requested)
    foreign = _job('job-foreign', _key(force=True))

    decision = choose_active_class_sync_job([exact, foreign], requested_key=requested)

    assert decision.reusable is None
    assert decision.blocker is foreign


def _engine_with_class_jobs():
    engine = create_engine('sqlite+pysqlite:///:memory:')
    AcademicClass.__table__.create(engine)
    AcademicClassSyncJob.__table__.create(engine)
    return engine


def _manual_user():
    return UserContext(
        user_id='operator-1',
        username='operator-1',
        email='operator-1@example.test',
        role='admin',
        permissions={'academic.manage'},
    )


def _allow_manual_enqueue(monkeypatch):
    monkeypatch.setattr(academic_routes, 'reconcile_class_sync_jobs', lambda db: 0)
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


def _seed_class(db):
    db.add(AcademicClass(
        id='class-01',
        term_id='term-01',
        subject_id='subject-01',
        class_code='CLASS.01',
        class_name='Class 01',
        campus='hn',
        branch='poly',
        active=True,
    ))
    db.commit()


def test_manual_enqueue_reuses_only_the_exact_active_contract(monkeypatch):
    _allow_manual_enqueue(monkeypatch)
    engine = _engine_with_class_jobs()
    with Session(engine) as db:
        _seed_class(db)
        requested = _key()
        db.add(AcademicClassSyncJob(
            id='job-exact',
            job_type='full_cms_sync',
            status='queued',
            class_id='class-01',
            requested_by='operator-1',
            force=False,
            limit=500,
            request_json={'request_key': requested},
        ))
        db.commit()

        result = academic_routes._enqueue_class_sync_job(
            db=db,
            user=_manual_user(),
            class_id='class-01',
            job_type='full_cms_sync',
            force=False,
            limit=500,
            auto_map_course=True,
            sync_learning=False,
        )

        assert result.id == 'job-exact'
        assert db.query(AcademicClassSyncJob).count() == 1
    engine.dispose()


def test_manual_enqueue_returns_409_with_blocking_job_id_for_other_contract(monkeypatch):
    _allow_manual_enqueue(monkeypatch)
    engine = _engine_with_class_jobs()
    with Session(engine) as db:
        _seed_class(db)
        db.add(AcademicClassSyncJob(
            id='job-blocker',
            job_type='full_cms_sync',
            status='running',
            class_id='class-01',
            requested_by='operator-1',
            force=True,
            limit=500,
            request_json={'request_key': _key(force=True)},
        ))
        db.commit()

        with pytest.raises(HTTPException) as caught:
            academic_routes._enqueue_class_sync_job(
                db=db,
                user=_manual_user(),
                class_id='class-01',
                job_type='full_cms_sync',
                force=False,
                limit=500,
                auto_map_course=True,
                sync_learning=False,
            )

        assert caught.value.status_code == 409
        assert caught.value.detail['blocking_job_id'] == 'job-blocker'
        assert db.query(AcademicClassSyncJob).count() == 1
    engine.dispose()


def test_scheduled_enqueue_raises_blocked_instead_of_adopting_manual_job():
    engine = _engine_with_class_jobs()
    with Session(engine) as db:
        _seed_class(db)
        db.add(AcademicClassSyncJob(
            id='job-manual',
            job_type='learning_sync',
            status='queued',
            class_id='class-01',
            requested_by='operator-1',
            force=False,
            limit=500,
            request_json={'request_key': _key(job_type='learning_sync')},
        ))
        db.commit()

        with pytest.raises(ClassSyncJobBlocked) as caught:
            _enqueue_academic_class_sync_child_job(
                db,
                requested_by='scheduler',
                class_id='class-01',
                force=True,
                limit=500,
                mode=None,
                auto_map_course=False,
                sync_learning=True,
                parent_job_id='parent-own',
                job_type='learning_sync',
                parent_job_type='learning_refresh_filter',
            )

        assert caught.value.blocking_job_id == 'job-manual'
        assert db.query(AcademicClassSyncJob).count() == 1
    engine.dispose()
