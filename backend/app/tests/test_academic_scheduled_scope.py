from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app import worker
from app.models.academic import (
    AcademicBulkOperationJob,
    AcademicClass,
    AcademicTerm,
)
from app.services.academic import student_management_runtime
from app.services.academic.scheduled_scope import (
    SCHEDULED_SCOPE_POLICY_VERSION,
    ScheduledScopeError,
    freeze_scheduled_scope,
    scheduled_auto_map_contract,
    scheduled_auto_map_key,
)
from app.services.academic.subject_delivery import AcademicSubjectDeliveryService
from app.services.academic_service import AcademicService


ROOT = Path(__file__).resolve().parents[3]


def _read(relative_path: str) -> str:
    return (ROOT / relative_path).read_text(encoding='utf-8')


def test_frozen_scope_is_complete_deterministic_and_order_independent():
    first = freeze_scheduled_scope(
        term_id='term-1',
        branch='POLY',
        run_date_vn='2026-09-23',
        class_to_campus={'class-2': 'HCM', 'class-1': 'HN'},
        requested_maximum={'students_per_class': 5000},
    )
    second = freeze_scheduled_scope(
        term_id='term-1',
        branch='poly',
        run_date_vn='2026-09-23',
        class_to_campus={'class-1': 'hn', 'class-2': 'hcm'},
        requested_maximum={'students_per_class': 5000},
    )

    assert first == second
    assert first['policy_version'] == SCHEDULED_SCOPE_POLICY_VERSION
    assert first['class_ids'] == ['class-1', 'class-2']
    assert first['class_to_campus'] == {'class-1': 'hn', 'class-2': 'hcm'}
    assert first['campuses'] == ['hcm', 'hn']
    assert len(first['scope_hash']) == 64


def test_frozen_scope_hash_includes_requested_maximum():
    base = dict(
        term_id='term-1',
        branch='poly',
        run_date_vn='2026-09-23',
        class_to_campus={'class-1': 'hn'},
    )

    first = freeze_scheduled_scope(
        **base,
        requested_maximum={'students_per_class': 5000},
    )
    second = freeze_scheduled_scope(
        **base,
        requested_maximum={'students_per_class': 4000},
    )

    assert first['scope_hash'] != second['scope_hash']


def test_frozen_scope_rejects_a_target_class_without_campus():
    with pytest.raises(ScheduledScopeError, match='class-2') as raised:
        freeze_scheduled_scope(
            term_id='term-1',
            branch='poly',
            run_date_vn='2026-09-23',
            class_to_campus={'class-1': 'hn', 'class-2': None},
            requested_maximum={'classes': 5000},
        )

    assert raised.value.code == 'scope_missing_campus'


def test_frozen_scope_rejects_ho_as_a_campus():
    with pytest.raises(ScheduledScopeError, match='reserved campus HO') as raised:
        freeze_scheduled_scope(
            term_id='term-1',
            branch='poly',
            run_date_vn='2026-09-23',
            class_to_campus={'class-1': 'HO'},
            requested_maximum={'classes': 5000},
        )

    assert raised.value.code == 'scope_reserved_campus'


def test_scheduled_auto_map_identity_contains_ap_run_and_scope_contract():
    scope = freeze_scheduled_scope(
        term_id='term-1',
        branch='poly',
        run_date_vn='2026-09-23',
        class_to_campus={'class-1': 'hn'},
        requested_maximum={'classes': 5000},
    )
    contract = scheduled_auto_map_contract(
        scheduled_parent_job_id='parent-1',
        ap_sync_run_id='ap-run-1',
        frozen_scope=scope,
    )

    assert contract == {
        'scheduled_parent_job_id': 'parent-1',
        'ap_sync_run_id': 'ap-run-1',
        'term_id': 'term-1',
        'branch': 'poly',
        'run_date_vn': '2026-09-23',
        'scope_hash': scope['scope_hash'],
        'policy_version': SCHEDULED_SCOPE_POLICY_VERSION,
    }
    assert scheduled_auto_map_key(contract).startswith('ap-auto-map:v1:')


def test_subject_discovery_safety_cap_is_an_explicit_truncation(monkeypatch):
    class FakeQuery:
        def outerjoin(self, *args, **kwargs):
            return self

        def filter(self, *args, **kwargs):
            return self

        def count(self):
            return 1

        def order_by(self, *args, **kwargs):
            return self

        def limit(self, value):
            return self

        def all(self):
            return [SimpleNamespace(id='class-1')]

    class FakeDb:
        def get(self, model, object_id):
            return SimpleNamespace(id=object_id, branch='poly')

        def query(self, *args, **kwargs):
            return FakeQuery()

    service = AcademicService(FakeDb())
    monkeypatch.setattr(
        service,
        'list_teacher_subjects',
        lambda *args, page, **kwargs: {
            'items': [{'id': f'subject-{page}', 'subject_code': f'S{page}'}],
            'has_next': True,
        },
    )
    monkeypatch.setattr(service, 'access_decision', lambda user: SimpleNamespace())
    monkeypatch.setattr(
        service,
        '_apply_academic_access_filter',
        lambda query, user, decision: query,
    )
    monkeypatch.setattr(
        AcademicSubjectDeliveryService,
        'is_subject_udemy_only',
        lambda self, **kwargs: False,
    )

    result = service.auto_map_subject_courses_for_filter(
        SimpleNamespace(),
        term_id='term-1',
        branch='poly',
        max_classes=5000,
        dry_run=True,
    )

    assert result['subject_total'] == 50
    assert result['scope_truncated'] is True
    assert result['scope_truncated_reason'] == 'subject_page_safety_cap'


def test_scheduled_parent_fails_when_any_mandatory_auto_map_target_fails():
    engine = create_engine('sqlite+pysqlite:///:memory:')
    AcademicBulkOperationJob.__table__.create(engine)
    with Session(engine) as db:
        parent = AcademicBulkOperationJob(
            id='parent-1',
            job_type='ap_daily_pipeline',
            status='running',
            request_json={'frozen_scope': {'scope_hash': 'scope-1'}},
            result_json={'phase': 'auto_map_queued'},
        )
        auto_map = AcademicBulkOperationJob(
            id='auto-map-1',
            job_type='subject_auto_map_all_sync',
            status='failed',
            request_json={},
            result_json={},
        )
        db.add_all([parent, auto_map])
        db.commit()

        worker._finish_scheduled_auto_map_parent(
            db,
            auto_map_job=auto_map,
            request_json={
                'scheduled_parent_job_id': parent.id,
                'scheduled_scope_hash': 'scope-1',
            },
            state={
                'class_target_count': 2,
                'class_completed_count': 1,
                'class_failed_count': 1,
            },
            ok=False,
            message='one mandatory class failed',
        )
        db.commit()

        db.refresh(parent)
        assert parent.status == 'failed'
        assert parent.result_json['phase'] == 'failed'
        assert parent.result_json['auto_map_outcome']['class_failed_count'] == 1
        assert parent.error_message == 'one mandatory class failed'
    engine.dispose()


def test_0300_scope_is_discovered_once_and_replayed_from_parent(monkeypatch):
    engine = create_engine('sqlite+pysqlite:///:memory:')
    for model in (AcademicTerm, AcademicClass, AcademicBulkOperationJob):
        model.__table__.create(engine)
    calls = []
    with Session(engine) as db:
        term = AcademicTerm(
            id='term-1',
            term_code='FA26',
            term_name='Fall 2026',
            branch='poly',
            active=True,
        )
        class_1 = AcademicClass(
            id='class-1',
            term_id=term.id,
            subject_id='subject-1',
            class_code='SOA102.01',
            class_name='SOA102.01',
            campus='hn',
            branch='poly',
            active=True,
        )
        parent = AcademicBulkOperationJob(
            id='parent-1',
            job_type='ap_daily_pipeline',
            status='running',
            term_id=term.id,
            branch='poly',
            request_json={'run_date_vn': '2026-09-23'},
            result_json={},
        )
        db.add_all([term, class_1, parent])
        db.commit()

        def discover(service, *args, **kwargs):
            calls.append('called')
            return {
                'class_ids': ['class-1'],
                'scope_truncated': False,
            }

        monkeypatch.setattr(
            AcademicService,
            'auto_map_subject_courses_for_filter',
            discover,
        )
        first, first_classes, first_subjects = (
            student_management_runtime._load_or_freeze_ap_scope(
                db,
                parent=parent,
                term=term,
                branch='poly',
            )
        )

        db.add(AcademicClass(
            id='class-2',
            term_id=term.id,
            subject_id='subject-2',
            class_code='SOA103.01',
            class_name='SOA103.01',
            campus='hcm',
            branch='poly',
            active=True,
        ))
        db.commit()
        second, second_classes, second_subjects = (
            student_management_runtime._load_or_freeze_ap_scope(
                db,
                parent=parent,
                term=term,
                branch='poly',
            )
        )

        assert calls == ['called']
        assert second == first
        assert second_classes == first_classes == ['class-1']
        assert second_subjects == first_subjects == ['subject-1']
    engine.dispose()


def test_0300_explicitly_empty_frozen_scope_is_not_success():
    parent = SimpleNamespace(
        request_json={
            'frozen_scope': {
                'class_ids': [],
                'scope_hash': 'empty-scope',
            },
            'approved_subject_ids': [],
        },
    )

    with pytest.raises(ScheduledScopeError) as raised:
        student_management_runtime._load_or_freeze_ap_scope(
            SimpleNamespace(),
            parent=parent,
            term=SimpleNamespace(id='term-1'),
            branch='poly',
        )

    assert raised.value.code == 'scope_empty'


def test_scheduled_runtimes_persist_and_enforce_frozen_contracts():
    daily = _read('backend/app/services/academic/daily_teacher_report_runtime.py')
    student = _read('backend/app/services/academic/student_management_runtime.py')

    assert 'freeze_scheduled_scope(' in daily
    assert "'frozen_scope': frozen_scope" in daily
    assert "state.get('frozen_scope')" in daily
    assert 'class_to_campus' in daily
    assert 'choose_active_class_sync_job(' in daily
    assert 'idempotency_key=request_key' in daily

    followup = student.split('def _create_scheduled_auto_map_after_ap(', 1)[1]
    assert '_load_or_freeze_ap_scope(' in followup
    assert 'scheduled_auto_map_contract(' in followup
    assert 'scheduled_auto_map_key(' in followup
    assert 'foreign_active' in followup
    assert "request.get('sync_learning') is False" not in followup
    assert '_publish_auto_map_job(' in followup

    worker = _read('backend/app/worker.py')
    finisher = worker.split(
        'def _finish_scheduled_auto_map_parent(',
        1,
    )[1].split('def academic_learning_refresh_filter_task', 1)[0]
    assert "parent.status = 'completed' if ok else 'failed'" in finisher
    assert "'scheduled_scope_hash'" in finisher
    assert "'class_failed_count'" in finisher
