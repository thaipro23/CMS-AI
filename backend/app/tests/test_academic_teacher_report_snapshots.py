from __future__ import annotations

import hashlib
import json
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from types import SimpleNamespace
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.models.academic import (
    AcademicBulkOperationJob,
    AcademicCampus,
    AcademicTeacherReportJob,
    AcademicTeacherReportSnapshot,
    AcademicTerm,
)
from app.services.academic.report_snapshot import (
    REPORT_SNAPSHOT_POLICY_VERSION,
    ReportSnapshotError,
    create_campus_snapshot,
    create_ho_snapshot,
    load_snapshot_envelope,
)


class MemoryStorage:
    def __init__(self):
        self.objects: dict[str, bytes] = {}

    def put_bytes(self, key: str, data: bytes, *, content_type: str | None = None) -> str:
        assert content_type
        self.objects[key] = bytes(data)
        return key

    def read_bytes(self, reference: str) -> bytes:
        return self.objects[reference]


def _engine():
    engine = create_engine('sqlite+pysqlite:///:memory:')
    AcademicCampus.__table__.create(engine)
    AcademicTerm.__table__.create(engine)
    AcademicBulkOperationJob.__table__.create(engine)
    AcademicTeacherReportSnapshot.__table__.create(engine)
    AcademicTeacherReportJob.__table__.create(engine)
    return engine


def _report(campus: str = 'hcm', branch: str = 'poly') -> dict:
    return {
        'items': [{
            'teacher_id': 'teacher-1',
            'teacher_name': 'Teacher One',
            'campus': campus,
            'branch': branch,
            'classes': [{
                'class_id': 'class-1',
                'class_code': 'WEB101',
                'campus': campus,
                'branch': branch,
            }],
        }],
        'student_watch_rows': [{
            'teacher_id': 'teacher-1',
            'class_id': 'class-1',
            'student_id': 'student-1',
            'student_code': 'PS001',
        }],
        'summary': {'teacher_count': 1, 'class_count': 1, 'student_count': 1},
    }


def _seed(db: Session):
    db.add_all([
        AcademicCampus(
            id='campus-hcm-poly', campus_code='hcm', campus_name='HCM',
            branch='poly', active=True,
        ),
        AcademicCampus(
            id='campus-hn-poly', campus_code='hn', campus_name='HN',
            branch='poly', active=True,
        ),
    ])
    db.add(AcademicTerm(
        id='term-1',
        term_code='FA26',
        term_name='Fall 2026',
        branch='poly',
    ))
    db.add(AcademicBulkOperationJob(
        id='parent-1',
        job_type='daily_score_report_pipeline',
        status='running',
        term_id='term-1',
        branch='poly',
        request_json={},
        result_json={},
    ))
    db.commit()


def test_campus_snapshot_is_immutable_checksummed_and_has_stable_provenance():
    engine = _engine()
    storage = MemoryStorage()
    with Session(engine) as db:
        _seed(db)
        row = create_campus_snapshot(
            db,
            storage=storage,
            parent_id='parent-1',
            term_id='term-1',
            branch='poly',
            campus='hcm',
            scope_hash='scope-sha',
            source_child_ids=['child-2', 'child-1', 'child-1'],
            source_synced_at=datetime(2026, 9, 23, 5, 5),
            report=_report(),
            term_label='FA26-FROZEN',
            run_date_vn='2026-09-23',
        )
        db.commit()

        raw = storage.read_bytes(row.storage_key)
        assert row.sha256 == hashlib.sha256(raw).hexdigest()
        assert row.size_bytes == len(raw)
        assert row.policy_version == REPORT_SNAPSHOT_POLICY_VERSION
        assert row.counts_json == {
            'teacher_count': 1,
            'class_count': 1,
            'student_count': 1,
        }
        envelope = json.loads(raw)
        assert envelope['campus'] == 'hcm'
        assert envelope['term_label'] == 'FA26-FROZEN'
        assert envelope['run_date_vn'] == '2026-09-23'
        assert envelope['scope_type'] == 'campus'
        assert envelope['source_child_ids'] == ['child-1', 'child-2']
        assert envelope['report']['items'][0]['teacher_id'] == 'teacher-1'
        assert envelope['report']['items'][0]['classes'][0]['class_id'] == 'class-1'
        assert envelope['report']['student_watch_rows'][0]['student_id'] == 'student-1'

        loaded = load_snapshot_envelope(
            db,
            storage=storage,
            snapshot_id=row.id,
            expected_parent_id='parent-1',
            expected_term_id='term-1',
            expected_branch='poly',
            expected_campus='hcm',
        )
        assert loaded == envelope
    engine.dispose()


@pytest.mark.parametrize(
    ('mutate', 'message'),
    [
        (lambda report: report['items'][0].pop('teacher_id'), 'teacher_id'),
        (lambda report: report['items'][0]['classes'][0].pop('class_id'), 'class_id'),
        (lambda report: report['student_watch_rows'][0].pop('student_id'), 'student_id'),
        (lambda report: report['items'][0]['classes'][0].update(campus='hn'), 'scope'),
    ],
)
def test_campus_snapshot_rejects_missing_ids_and_cross_campus_rows(mutate, message):
    engine = _engine()
    storage = MemoryStorage()
    with Session(engine) as db:
        _seed(db)
        report = _report()
        mutate(report)
        with pytest.raises(ReportSnapshotError, match=message):
            create_campus_snapshot(
                db,
                storage=storage,
                parent_id='parent-1',
                term_id='term-1',
                branch='poly',
                campus='hcm',
                scope_hash='scope-sha',
                source_child_ids=['child-1'],
                source_synced_at=datetime(2026, 9, 23, 5, 5),
                report=report,
            )
    engine.dispose()


def test_snapshot_loader_detects_tampering_and_scope_mismatch():
    engine = _engine()
    storage = MemoryStorage()
    with Session(engine) as db:
        _seed(db)
        row = create_campus_snapshot(
            db,
            storage=storage,
            parent_id='parent-1',
            term_id='term-1',
            branch='poly',
            campus='hcm',
            scope_hash='scope-sha',
            source_child_ids=['child-1'],
            source_synced_at=datetime(2026, 9, 23, 5, 5),
            report=_report(),
        )
        db.commit()

        with pytest.raises(ReportSnapshotError, match='campus'):
            load_snapshot_envelope(
                db,
                storage=storage,
                snapshot_id=row.id,
                expected_parent_id='parent-1',
                expected_term_id='term-1',
                expected_branch='poly',
                expected_campus='hn',
            )

        storage.objects[row.storage_key] += b'\n'
        with pytest.raises(ReportSnapshotError, match='checksum'):
            load_snapshot_envelope(
                db,
                storage=storage,
                snapshot_id=row.id,
                expected_parent_id='parent-1',
                expected_term_id='term-1',
                expected_branch='poly',
                expected_campus='hcm',
            )
    engine.dispose()


def test_scheduled_writer_contract_uses_snapshot_not_live_report_source():
    from app.services.academic import daily_teacher_report_runtime as runtime

    source = runtime._write_teacher_report_file.__code__.co_names
    assert '_scheduled_snapshot_report' in source
    engine = _engine()
    storage = MemoryStorage()
    with Session(engine) as db:
        _seed(db)
        row = create_campus_snapshot(
            db,
            storage=storage,
            parent_id='parent-1',
            term_id='term-1',
            branch='poly',
            campus='hcm',
            scope_hash='scope-sha',
            source_child_ids=['child-1'],
            source_synced_at=datetime(2026, 9, 23, 5, 5),
            report=_report(),
        )
        job = AcademicTeacherReportJob(
            id='report-job-1',
            job_type='scheduled_export_excel',
            status='running',
            term_id='term-1',
            branch='poly',
            campus='hcm',
            request_json={
                'source_sync_parent_id': 'parent-1',
                'report_snapshot_id': row.id,
            },
            result_json={},
        )
        db.add(job)
        db.commit()

        report, envelope = runtime._scheduled_snapshot_report(db, job, storage=storage)
        assert report == _report()
        assert envelope['parent_job_id'] == 'parent-1'
    engine.dispose()


def test_all_campus_payloads_are_built_by_one_consistent_session(monkeypatch):
    from app.services.academic import daily_teacher_report_runtime as runtime

    engine = _engine()
    sessions_seen: set[int] = set()
    storage = MemoryStorage()
    factory = sessionmaker(bind=engine, autoflush=False, autocommit=False)

    class FakeAcademicService:
        def __init__(self, db):
            self.db = db

        def training_teacher_report(self, _user, **kwargs):
            sessions_seen.add(id(self.db))
            assert kwargs['student_row_limit'] is None
            assert kwargs['enforce_branch_integrity'] is True
            campus = kwargs['campus']
            assert kwargs['allowed_class_ids'] == {f'class-{campus}'}
            report = _report(campus)
            report['items'][0]['classes'][0]['class_id'] = f'class-{campus}'
            report['student_watch_rows'][0]['class_id'] = f'class-{campus}'
            report['student_watch_rows'][0]['student_id'] = f'student-{campus}'
            return report

    with Session(engine) as db:
        _seed(db)
        parent = db.get(AcademicBulkOperationJob, 'parent-1')
        monkeypatch.setattr(runtime, 'SessionLocal', factory)
        monkeypatch.setattr(runtime, 'AcademicService', FakeAcademicService)
        monkeypatch.setattr(runtime, 'get_object_storage', lambda: storage)

        snapshot_ids = runtime._build_campus_report_snapshots(
            parent,
            state={
                'frozen_scope': {
                    'campuses': ['hcm', 'hn'],
                    'class_to_campus': {'class-hcm': 'hcm', 'class-hn': 'hn'},
                    'scope_hash': 'scope-sha',
                    'run_date_vn': '2026-09-23',
                },
                'child_job_ids_by_class': {
                    'class-hcm': 'child-hcm',
                    'class-hn': 'child-hn',
                },
            },
            source_synced_at=datetime(2026, 9, 23, 5, 5),
        )

    assert set(snapshot_ids) == {'hcm', 'hn'}
    assert len(sessions_seen) == 1
    with Session(engine) as db:
        rows = db.query(AcademicTeacherReportSnapshot).all()
        assert {row.campus for row in rows} == {'hcm', 'hn'}
        assert {
            row.campus: row.metadata_json['source_child_ids']
            for row in rows
        } == {'hcm': ['child-hcm'], 'hn': ['child-hn']}

        term = db.get(AcademicTerm, 'term-1')
        term.term_code = 'RENAMED-AFTER-SNAPSHOT'
        db.commit()

    class MustNotRebuild:
        def __init__(self, _db):
            raise AssertionError('immutable snapshot retry queried live report data')

    monkeypatch.setattr(runtime, 'AcademicService', MustNotRebuild)
    retried_ids = runtime._build_campus_report_snapshots(
        parent,
        state={
            'frozen_scope': {
                'campuses': ['hcm', 'hn'],
                'class_to_campus': {'class-hcm': 'hcm', 'class-hn': 'hn'},
                'scope_hash': 'scope-sha',
                'run_date_vn': '2026-09-23',
            },
            'child_job_ids_by_class': {
                'class-hcm': 'child-hcm',
                'class-hn': 'child-hn',
            },
        },
        source_synced_at=datetime(2026, 9, 23, 5, 5),
    )
    assert retried_ids == snapshot_ids
    engine.dispose()


def test_ho_snapshot_aggregates_only_matching_campus_snapshots_and_deduplicates_ids():
    engine = _engine()
    storage = MemoryStorage()
    with Session(engine) as db:
        _seed(db)
        hcm_report = _report('hcm')
        hn_report = _report('hn')
        hn_report['items'][0]['classes'][0]['class_id'] = 'class-2'
        hn_report['student_watch_rows'][0]['class_id'] = 'class-2'
        # Same stable teacher/student appear in both campuses.
        hcm = create_campus_snapshot(
            db,
            storage=storage,
            parent_id='parent-1',
            term_id='term-1',
            branch='poly',
            campus='hcm',
            scope_hash='scope-sha',
            source_child_ids=['child-1'],
            source_synced_at=datetime(2026, 9, 23, 5, 5),
            report=hcm_report,
        )
        hn = create_campus_snapshot(
            db,
            storage=storage,
            parent_id='parent-1',
            term_id='term-1',
            branch='poly',
            campus='hn',
            scope_hash='scope-sha',
            source_child_ids=['child-2'],
            source_synced_at=datetime(2026, 9, 23, 5, 5),
            report=hn_report,
        )
        ho = create_ho_snapshot(
            db,
            storage=storage,
            parent_id='parent-1',
            term_id='term-1',
            branch='poly',
            scope_hash='scope-sha',
            expected_campuses=['hcm', 'hn'],
            campus_snapshots=[hcm, hn],
            source_synced_at=datetime(2026, 9, 23, 5, 5),
        )
        db.commit()

        envelope = load_snapshot_envelope(
            db,
            storage=storage,
            snapshot_id=ho.id,
            expected_parent_id='parent-1',
            expected_term_id='term-1',
            expected_branch='poly',
            expected_campus=None,
        )
        report = envelope['report']
        assert report['summary']['teacher_count'] == 1
        assert report['summary']['class_count'] == 2
        assert report['summary']['student_count'] == 2
        assert report['summary']['unique_student_count'] == 1
        assert len(report['items']) == 1
        assert {item['class_id'] for item in report['items'][0]['classes']} == {'class-1', 'class-2'}
        assert envelope['campuses'] == ['hcm', 'hn']
        assert envelope['source_child_ids'] == ['child-1', 'child-2']
        assert envelope['source_campus_snapshot_ids'] == [hcm.id, hn.id]
        assert envelope['source_campus_checksums'] == {hcm.id: hcm.sha256, hn.id: hn.sha256}
    engine.dispose()


def test_ho_snapshot_rejects_missing_duplicate_or_scope_mismatched_campus_snapshot():
    engine = _engine()
    storage = MemoryStorage()
    with Session(engine) as db:
        _seed(db)
        hcm = create_campus_snapshot(
            db,
            storage=storage,
            parent_id='parent-1',
            term_id='term-1',
            branch='poly',
            campus='hcm',
            scope_hash='scope-sha',
            source_child_ids=['child-1'],
            source_synced_at=datetime(2026, 9, 23, 5, 5),
            report=_report('hcm'),
        )

        with pytest.raises(ReportSnapshotError, match='campus set'):
            create_ho_snapshot(
                db,
                storage=storage,
                parent_id='parent-1',
                term_id='term-1',
                branch='poly',
                scope_hash='scope-sha',
                expected_campuses=['hcm', 'hn'],
                campus_snapshots=[hcm],
                source_synced_at=datetime(2026, 9, 23, 5, 5),
            )

        with pytest.raises(ReportSnapshotError, match='duplicate'):
            create_ho_snapshot(
                db,
                storage=storage,
                parent_id='parent-1',
                term_id='term-1',
                branch='poly',
                scope_hash='scope-sha',
                expected_campuses=['hcm'],
                campus_snapshots=[hcm, hcm],
                source_synced_at=datetime(2026, 9, 23, 5, 5),
            )
    engine.dispose()


def test_ho_snapshot_rejects_campus_owned_by_other_branch():
    engine = _engine()
    storage = MemoryStorage()
    with Session(engine) as db:
        _seed(db)
        hcm = create_campus_snapshot(
            db,
            storage=storage,
            parent_id='parent-1',
            term_id='term-1',
            branch='poly',
            campus='hcm',
            scope_hash='scope-sha',
            source_child_ids=['child-1'],
            source_synced_at=datetime(2026, 9, 23, 5, 5),
            report=_report('hcm'),
        )
        campus = db.get(AcademicCampus, 'campus-hcm-poly')
        campus.branch = 'ptcd'
        db.flush()

        with pytest.raises(ReportSnapshotError, match='campus ownership'):
            create_ho_snapshot(
                db,
                storage=storage,
                parent_id='parent-1',
                term_id='term-1',
                branch='poly',
                scope_hash='scope-sha',
                expected_campuses=['hcm'],
                campus_snapshots=[hcm],
                source_synced_at=datetime(2026, 9, 23, 5, 5),
            )
    engine.dispose()


def test_scheduled_export_job_is_reused_by_immutable_snapshot_identity():
    from app.services.academic import daily_teacher_report_runtime as runtime

    engine = _engine()
    sent: list[tuple[str, list[str], str]] = []

    class FakeCelery:
        def send_task(self, name, *, args, queue, **_kwargs):
            sent.append((name, args, queue))
            return SimpleNamespace(id=f'task-{len(sent)}')

    with Session(engine) as db:
        _seed(db)
        parent = db.get(AcademicBulkOperationJob, 'parent-1')
        first = runtime._create_scheduled_export_job(
            db,
            FakeCelery(),
            parent=parent,
            campus='hcm',
            source_synced_at=datetime(2026, 9, 23, 5, 5),
            request_overrides={'report_snapshot_id': 'snapshot-1'},
        )
        second = runtime._create_scheduled_export_job(
            db,
            FakeCelery(),
            parent=parent,
            campus='hcm',
            source_synced_at=datetime(2026, 9, 23, 5, 5),
            request_overrides={'report_snapshot_id': 'snapshot-1'},
        )

        assert second.id == first.id
        assert db.query(AcademicTeacherReportJob).count() == 1
        assert sent == [('academic_teacher_report_job_task', [first.id], 'exports')]
    engine.dispose()


def test_daily_snapshot_attempt_persists_campus_snapshot_result(monkeypatch):
    from app.services.academic import daily_teacher_report_runtime as runtime

    engine = _engine()
    factory = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    captured: dict[str, object] = {}
    with Session(engine) as db:
        _seed(db)
        db.add(AcademicBulkOperationJob(
            id='daily-root-1',
            job_type='academic_daily_pipeline_v2',
            status='running',
            request_json={'run_date_vn': '2026-09-24'},
            result_json={},
        ))
        db.add(AcademicBulkOperationJob(
            id='snapshot-attempt-1',
            parent_job_id='daily-root-1',
            job_type='daily_report_snapshot_attempt',
            status='queued',
            term_id='term-1',
            branch='poly',
            request_json={
                'daily_root_job_id': 'daily-root-1',
                'scope_parent_id': 'parent-1',
                'snapshot_type': 'campus_set',
                'source_synced_at': '2026-09-24T01:45:00+07:00',
                'scope': {
                    'scope_key': 'poly:term-1',
                    'term_id': 'term-1',
                    'branch': 'poly',
                    'campuses': ['hcm'],
                    'class_ids': ['class-1'],
                    'class_to_campus': {'class-1': 'hcm'},
                    'scope_hash': 'scope-sha',
                },
                'score_job_ids_by_class': {'class-1': 'score-class-1'},
            },
            result_json={},
        ))
        db.commit()

    def fake_build(scope_parent, state, source_synced_at):
        captured['scope_parent_id'] = scope_parent.id
        captured['state'] = state
        captured['source_synced_at'] = source_synced_at
        return {'hcm': 'snapshot-hcm'}

    monkeypatch.setattr(runtime, 'SessionLocal', factory)
    monkeypatch.setattr(runtime, 'build_scope_campus_snapshots', fake_build)

    result = runtime.run_daily_snapshot_attempt('snapshot-attempt-1')

    assert result['snapshot_ids_by_campus'] == {'hcm': 'snapshot-hcm'}
    assert captured['scope_parent_id'] == 'parent-1'
    assert captured['state']['frozen_scope']['run_date_vn'] == '2026-09-24'
    assert captured['state']['child_job_ids_by_class'] == {'class-1': 'score-class-1'}
    with Session(engine) as db:
        job = db.get(AcademicBulkOperationJob, 'snapshot-attempt-1')
        assert job.status == 'completed'
        assert job.result_json['snapshot_type'] == 'campus_set'
    engine.dispose()


def test_duplicate_parent_delivery_serializes_snapshot_construction(monkeypatch, tmp_path):
    from app.services.academic import daily_teacher_report_runtime as runtime

    engine = create_engine(
        f"sqlite+pysqlite:///{tmp_path / 'snapshot-race.sqlite'}",
        connect_args={'check_same_thread': False, 'timeout': 10},
    )
    AcademicCampus.__table__.create(engine)
    AcademicTerm.__table__.create(engine)
    AcademicBulkOperationJob.__table__.create(engine)
    AcademicTeacherReportSnapshot.__table__.create(engine)
    with Session(engine) as db:
        _seed(db)

    factory = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    storage = MemoryStorage()
    build_calls = 0
    build_calls_guard = threading.Lock()

    class SlowAcademicService:
        def __init__(self, db):
            self.db = db

        def training_teacher_report(self, _user, **_kwargs):
            nonlocal build_calls
            with build_calls_guard:
                build_calls += 1
            return _report('hcm')

    monkeypatch.setattr(runtime, 'SessionLocal', factory)
    monkeypatch.setattr(runtime, 'AcademicService', SlowAcademicService)
    monkeypatch.setattr(runtime, 'get_object_storage', lambda: storage)
    parent = SimpleNamespace(id='parent-1', term_id='term-1', branch='poly')
    state = {
        'frozen_scope': {
            'campuses': ['hcm'],
            'class_to_campus': {'class-1': 'hcm'},
            'scope_hash': 'scope-sha',
            'run_date_vn': '2026-09-23',
        },
        'child_job_ids_by_class': {'class-1': 'child-1'},
    }

    def build():
        return runtime._build_campus_report_snapshots(
            parent,
            state=state,
            source_synced_at=datetime(2026, 9, 23, 5, 5),
        )

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _index: build(), range(2)))

    assert results[0] == results[1]
    assert build_calls == 1
    def build_ho():
        return runtime._build_ho_report_snapshot(
            parent,
            state=state,
            campus_snapshot_ids=results[0],
            source_synced_at=datetime(2026, 9, 23, 5, 5),
        )

    with ThreadPoolExecutor(max_workers=2) as pool:
        ho_results = list(pool.map(lambda _index: build_ho(), range(2)))

    assert ho_results[0] == ho_results[1]
    with Session(engine) as db:
        assert db.query(AcademicTeacherReportSnapshot).count() == 2
    engine.dispose()


def test_replayed_parent_republishes_unconfirmed_export_intent():
    from app.services.academic import daily_teacher_report_runtime as runtime

    engine = _engine()
    sent: list[tuple[str, list[str], str]] = []

    class FakeCelery:
        def send_task(self, name, *, args, queue, **_kwargs):
            sent.append((name, args, queue))
            return SimpleNamespace(id='task-recovered')

    with Session(engine) as db:
        _seed(db)
        parent = db.get(AcademicBulkOperationJob, 'parent-1')
        db.add(AcademicTeacherReportJob(
            id='stranded-report',
            job_type='scheduled_export_excel',
            status='queued',
            term_id='term-1',
            branch='poly',
            campus='hcm',
            requested_by=runtime.SCHEDULER_ACTOR,
            request_json={
                'source_sync_parent_id': 'parent-1',
                'report_snapshot_id': 'snapshot-1',
            },
            result_json={
                'dispatch': {
                    'state': 'pending',
                    'task_name': 'academic_teacher_report_job_task',
                    'queue': 'exports',
                },
            },
        ))
        db.commit()

        recovered = runtime._create_scheduled_export_job(
            db,
            FakeCelery(),
            parent=parent,
            campus='hcm',
            source_synced_at=datetime(2026, 9, 23, 5, 5),
            request_overrides={'report_snapshot_id': 'snapshot-1'},
        )
        db.refresh(recovered)

        assert recovered.id == 'stranded-report'
        assert recovered.result_json['dispatch']['state'] == 'confirmed'
        assert recovered.result_json['dispatch']['celery_task_id'] == 'task-recovered'
        assert sent == [('academic_teacher_report_job_task', ['stranded-report'], 'exports')]
    engine.dispose()


def test_duplicate_export_task_does_not_reenter_a_running_job(monkeypatch):
    from app.services.academic import daily_teacher_report_runtime as runtime

    engine = _engine()
    factory = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    with Session(engine) as db:
        _seed(db)
        db.add(AcademicTeacherReportJob(
            id='running-report',
            job_type='scheduled_export_excel',
            status='running',
            term_id='term-1',
            branch='poly',
            campus='hcm',
            request_json={'report_snapshot_id': 'snapshot-1'},
            result_json={'dispatch': {'state': 'confirmed'}},
        ))
        db.commit()
    monkeypatch.setattr(runtime, 'SessionLocal', factory)

    result = runtime.run_teacher_report_job('running-report')

    assert result == {'ok': True, 'status': 'running', 'duplicate_delivery': True}
    with Session(engine) as db:
        assert db.get(AcademicTeacherReportJob, 'running-report').status == 'running'
    engine.dispose()


def test_scheduled_artifact_filename_uses_frozen_snapshot_metadata(monkeypatch):
    from app.api.routes import academic as academic_routes
    from app.services.academic import daily_teacher_report_runtime as runtime

    engine = _engine()
    storage = MemoryStorage()
    with Session(engine) as db:
        _seed(db)
        row = create_campus_snapshot(
            db,
            storage=storage,
            parent_id='parent-1',
            term_id='term-1',
            branch='poly',
            campus='hcm',
            scope_hash='scope-sha',
            source_child_ids=['child-1'],
            source_synced_at=datetime(2026, 9, 23, 5, 5),
            report=_report(),
            term_label='FA26-FROZEN',
            run_date_vn='2026-09-23',
        )
        job = AcademicTeacherReportJob(
            id='scheduled-file-job',
            job_type='scheduled_export_excel',
            status='running',
            term_id='term-1',
            branch='poly',
            campus='hcm',
            request_json={
                'scheduled': True,
                'management_scope': True,
                'source_sync_parent_id': 'parent-1',
                'source_synced_at': '2026-09-23T05:05:00+07:00',
                'report_snapshot_id': row.id,
                'scope': 'campus',
            },
            result_json={},
        )
        db.add(job)
        db.commit()

        # Mutable live metadata changes after the immutable run snapshot.
        term = db.get(AcademicTerm, 'term-1')
        term.term_code = 'RENAMED-LIVE'
        term.term_name = 'Renamed live term'
        db.commit()

        monkeypatch.setattr(runtime, 'get_object_storage', lambda: storage)
        monkeypatch.setattr(
            academic_routes,
            '_write_training_teacher_report_xlsx',
            lambda _report_payload, path: path.write_bytes(b'xlsx'),
        )
        live_service = SimpleNamespace(
            training_teacher_report=lambda *_args, **_kwargs: (_ for _ in ()).throw(
                AssertionError('scheduled artifact queried live report data')
            ),
            rebuild_training_teacher_report_cache=lambda *_args, **_kwargs: (_ for _ in ()).throw(
                AssertionError('scheduled artifact used mutable UI cache')
            ),
        )

        result = runtime._write_teacher_report_file(
            db,
            job,
            service=live_service,
            user=SimpleNamespace(),
            scheduled=True,
        )

        assert result['file_name'] == 'teacher-report-FA26-FROZEN-poly-HCM-20260923.xlsx'
        assert 'RENAMED-LIVE' not in result['storage_ref']
    engine.dispose()
