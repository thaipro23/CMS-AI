from __future__ import annotations

import inspect

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.api.routes import academic as academic_routes
from app import worker
from app.core.rbac import UserContext
from app.models.academic import (
    AcademicBlock,
    AcademicClass,
    AcademicSubject,
    AcademicSubjectDelivery,
    AcademicTerm,
)
from app.services.academic_service import AcademicService


def test_auto_map_enqueue_ignores_student_learning_status_and_audits_enqueue_success():
    source = inspect.getsource(
        academic_routes.auto_map_all_subject_courses_and_enqueue_sync_jobs,
    )

    assert "'learning_status': None" in source
    assert "'force': False" in source
    assert "'sync_learning': False" in source
    assert 'learning_status=None' in source
    assert "candidate_request.get('learning_status')" not in source
    assert "status='success'" in source
    assert "'job_status': job.status" in source

    worker_source = inspect.getsource(worker.academic_subject_auto_map_all_sync_task.run)
    assert 'force=False' in worker_source
    assert 'sync_learning=False' in worker_source


def test_auto_map_retry_does_not_restore_legacy_learning_status_filter():
    source = inspect.getsource(academic_routes.retry_academic_bulk_operation_job)

    assert 'learning_status=None' in source
    assert "learning_status=request_json.get('learning_status')" not in source


def test_auto_map_snapshot_uses_approved_ids_without_reapplying_learning_filter(monkeypatch):
    engine = create_engine('sqlite+pysqlite:///:memory:')
    for model in (
        AcademicTerm,
        AcademicBlock,
        AcademicSubject,
        AcademicSubjectDelivery,
        AcademicClass,
    ):
        model.__table__.create(engine)

    with Session(engine) as db:
        term = AcademicTerm(
            id='term-fa26', term_code='FA26', term_name='Fall 2026', branch='poly', active=True,
        )
        block = AcademicBlock(
            id='block-1', term_id=term.id, block_code='B1', block_name='Block 1', active=True,
        )
        subject = AcademicSubject(
            id='subject-1', subject_code='SOA102', subject_name='SOA', branch='poly', active=True,
        )
        classes = [
            AcademicClass(
                id=f'class-{index}', term_id=term.id, block_id=block.id,
                subject_id=subject.id, class_code=f'SOA102.0{index}',
                class_name=f'SOA102.0{index}', campus='hn', branch='poly', active=True,
            )
            for index in (1, 2)
        ]
        db.add_all([
            term,
            block,
            subject,
            AcademicSubjectDelivery(
                id='delivery-1', subject_id=subject.id, term_id=term.id,
                block_id=block.id, branch='poly', learning_platform='cms', active=True,
            ),
            *classes,
        ])
        db.commit()

        service = AcademicService(db)
        monkeypatch.setattr(
            service,
            'auto_map_subject_course',
            lambda *_args, **_kwargs: {
                'ok': True,
                'status': 'auto_mapped',
                'message': 'mapped',
                'mapping': {'openedx_course_id': 'course-v1:FPL+SOA102+FA26'},
            },
        )
        user = UserContext(
            user_id='scheduler', role='admin', permissions=set(),
            raw_claims={'ai_system_admin': True},
        )

        result = service.auto_map_subject_courses_for_snapshot(
            user,
            term_id=term.id,
            branch='poly',
            approved_subject_ids=[subject.id],
            approved_class_ids=['class-1', 'class-2'],
        )

        assert result['class_ids'] == ['class-1', 'class-2']
        assert result['approved_class_ids'] == ['class-1', 'class-2']
        assert result['mapped_class_ids'] == ['class-1', 'class-2']
        assert result['failed_class_ids'] == []
        assert result['subject_results'][0]['class_ids'] == ['class-1', 'class-2']
        assert result['approved_class_count'] == 2
        assert result['subject_mapped'] == 1
    engine.dispose()


def test_auto_map_snapshot_partitions_failed_subject_classes(monkeypatch):
    engine = create_engine('sqlite+pysqlite:///:memory:')
    for model in (
        AcademicTerm,
        AcademicBlock,
        AcademicSubject,
        AcademicSubjectDelivery,
        AcademicClass,
    ):
        model.__table__.create(engine)

    with Session(engine) as db:
        term = AcademicTerm(
            id='term-fa26', term_code='FA26', term_name='Fall 2026', branch='poly', active=True,
        )
        block = AcademicBlock(
            id='block-1', term_id=term.id, block_code='B1', block_name='Block 1', active=True,
        )
        subjects = [
            AcademicSubject(
                id=f'subject-{index}', subject_code=f'SOA10{index}',
                subject_name=f'Subject {index}', branch='poly', active=True,
            )
            for index in (1, 2)
        ]
        classes = [
            AcademicClass(
                id=f'class-{index}', term_id=term.id, block_id=block.id,
                subject_id=f'subject-{index}', class_code=f'SOA10{index}.01',
                class_name=f'Class {index}', campus='hn', branch='poly', active=True,
            )
            for index in (1, 2)
        ]
        db.add_all([term, block, *subjects, *classes])
        db.commit()

        service = AcademicService(db)

        def auto_map(_user, *, subject_id, **_kwargs):
            if subject_id == 'subject-1':
                return {
                    'ok': True,
                    'status': 'auto_mapped',
                    'mapping': {'openedx_course_id': 'course-v1:FPL+SOA101+FA26'},
                }
            return {
                'ok': False,
                'status': 'no_candidate',
                'message': 'No CMS course candidate',
            }

        monkeypatch.setattr(service, 'auto_map_subject_course', auto_map)
        user = UserContext(
            user_id='scheduler', role='admin', permissions=set(),
            raw_claims={'ai_system_admin': True},
        )

        result = service.auto_map_subject_courses_for_snapshot(
            user,
            term_id=term.id,
            branch='poly',
            approved_subject_ids=['subject-1', 'subject-2'],
            approved_class_ids=['class-1', 'class-2'],
        )

    assert result['mapped_class_ids'] == ['class-1']
    assert result['failed_class_ids'] == ['class-2']
    assert result['subject_failed'] == 1
    failed = next(item for item in result['subject_results'] if item['subject_id'] == 'subject-2')
    assert failed['class_ids'] == ['class-2']
    assert failed['message'] == 'No CMS course candidate'
    engine.dispose()

def test_auto_map_worker_allows_explicit_empty_scope_but_rejects_missing_snapshot():
    worker_source = inspect.getsource(worker.academic_subject_auto_map_all_sync_task.run)

    assert "scope_snapshot_present = 'approved_class_ids' in request_json" in worker_source
    assert 'if not scope_snapshot_present:' in worker_source
    assert "if not approved_class_ids:\n                raise PermissionError" not in worker_source

def test_auto_map_retry_treats_explicit_empty_scope_as_valid_snapshot():
    source = inspect.getsource(academic_routes.retry_academic_bulk_operation_job)

    assert "scope_snapshot_present = 'approved_class_ids' in request_json" in source
    assert 'if not scope_snapshot_present:' in source
