from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.models.academic import (
    AcademicBulkOperationJob,
    AcademicTeacherReportJob,
    AcademicTerm,
)
from app.services.academic import daily_academic_pipeline as runtime


class FakeCelery:
    def __init__(self):
        self.sent: list[tuple[str, list[str], dict]] = []

    def send_task(self, name, args=None, **options):
        self.sent.append((name, list(args or []), options))
        return SimpleNamespace(id=f"task-{len(self.sent)}")


@pytest.fixture
def session_factory():
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    for model in (AcademicTerm, AcademicBulkOperationJob, AcademicTeacherReportJob):
        model.__table__.create(engine)
    factory = sessionmaker(bind=engine)
    yield factory
    engine.dispose()


def _scope(branch: str, campus_count: int) -> dict[str, object]:
    campuses = [f"{branch}-campus-{index}" for index in range(campus_count)]
    class_ids = [f"class-{branch}-{index}" for index in range(campus_count)]
    return {
        "policy_version": runtime.DAILY_POLICY_VERSION,
        "scope_key": f"{branch}:term-{branch}",
        "scope_hash": f"hash-{branch}",
        "term_id": f"term-{branch}",
        "term_name": "Fall 2026",
        "branch": branch,
        "campuses": campuses,
        "class_ids": class_ids,
        "class_to_campus": dict(zip(class_ids, campuses, strict=True)),
    }


def _campus_targets(scopes: list[dict[str, object]]) -> list[str]:
    rows = [
        [f'{scope["scope_key"]}:{campus}' for campus in scope["campuses"]]
        for scope in scopes
    ]
    return [
        target
        for index in range(max((len(row) for row in rows), default=0))
        for row in rows
        for target in row[index:index + 1]
    ]


def _seed_root(session_factory, *, phase: str, poly: int = 2, ptcd: int = 1):
    scopes = [_scope("poly", poly), _scope("ptcd", ptcd)]
    with session_factory() as db:
        db.add_all([
            AcademicTerm(id="term-poly", term_code="FA26", term_name="Fall", branch="poly"),
            AcademicTerm(id="term-ptcd", term_code="FA26", term_name="Fall", branch="ptcd"),
        ])
        state = {
            "phase": phase,
            "stage_round": 0,
            "stage_target_keys": (
                [scope["scope_key"] for scope in scopes]
                if phase == "campus_snapshots"
                else _campus_targets(scopes)
            ),
            "attempts_by_stage": {},
            "frozen_scopes_after_ap": {scope["scope_key"]: scope for scope in scopes},
            "source_synced_at": "2026-09-24T01:45:00+07:00",
            "score_job_ids_by_class": {
                class_id: f"score-{class_id}"
                for scope in scopes
                for class_id in scope["class_ids"]
            },
            "campus_snapshot_ids_by_target": {
                f'{scope["scope_key"]}:{campus}': f"snapshot-{scope['branch']}-{campus}"
                for scope in scopes
                for campus in scope["campuses"]
            },
            "artifacts": {},
        }
        root = AcademicBulkOperationJob(
            id="root-1",
            job_type=runtime.DAILY_ROOT_JOB_TYPE,
            status="running",
            idempotency_key="academic-daily:v2:2026-09-24",
            request_json={"run_date_vn": "2026-09-24", "scopes": scopes},
            result_json=state,
        )
        db.add(root)
        db.commit()
        runtime.ensure_scope_parents(db, root, scopes)
    return "root-1", scopes


def test_campus_exports_share_one_four_job_window_across_branches(
    monkeypatch,
    session_factory,
):
    root_id, _scopes = _seed_root(
        session_factory,
        phase="campus_reports",
        poly=5,
        ptcd=4,
    )
    monkeypatch.setattr(runtime, "SessionLocal", session_factory)

    runtime.run_daily_academic_pipeline(FakeCelery(), root_id)

    with session_factory() as db:
        active = db.query(AcademicTeacherReportJob).filter(
            AcademicTeacherReportJob.status.in_(["queued", "running"]),
        ).all()
        assert len(active) == 4
        assert {job.branch for job in active} == {"poly", "ptcd"}
        assert all(job.request_json["daily_stage"] == "campus_reports" for job in active)


def test_failed_campus_retries_only_after_every_campus_attempt_is_terminal(
    monkeypatch,
    session_factory,
):
    root_id, scopes = _seed_root(session_factory, phase="campus_reports")
    targets = _campus_targets(scopes)
    with session_factory() as db:
        root = db.get(AcademicBulkOperationJob, root_id)
        attempts = {}
        for index, (target, status) in enumerate(zip(targets, ["failed", "completed", "running"], strict=True)):
            scope_key, campus = target.rsplit(":", 1)
            scope = next(item for item in scopes if item["scope_key"] == scope_key)
            job = AcademicTeacherReportJob(
                id=f"report-{index}",
                parent_job_id=root_id,
                idempotency_key=f"report-attempt-{index}",
                job_type="scheduled_export_excel",
                status=status,
                term_id=scope["term_id"],
                branch=scope["branch"],
                campus=campus,
                request_json={"daily_stage": "campus_reports", "logical_target_key": target},
                result_json={},
            )
            db.add(job)
            attempts[target] = job.id
        state = dict(root.result_json)
        state["attempts_by_stage"] = {"campus_reports": {"0": attempts}}
        root.result_json = state
        db.commit()
    monkeypatch.setattr(runtime, "SessionLocal", session_factory)

    runtime.run_daily_academic_pipeline(FakeCelery(), root_id)
    with session_factory() as db:
        root = db.get(AcademicBulkOperationJob, root_id)
        assert root.result_json["stage_round"] == 0
        assert db.query(AcademicTeacherReportJob).count() == 3
        db.get(AcademicTeacherReportJob, "report-2").status = "completed"
        db.commit()

    runtime.run_daily_academic_pipeline(FakeCelery(), root_id)
    with session_factory() as db:
        root = db.get(AcademicBulkOperationJob, root_id)
        assert root.result_json["stage_round"] == 1
        retry = root.result_json["attempts_by_stage"]["campus_reports"]["1"]
        assert list(retry) == [targets[0]]
        assert db.query(AcademicTeacherReportJob).count() == 4


def test_ho_is_not_created_until_every_campus_in_both_branches_succeeds(
    monkeypatch,
    session_factory,
):
    root_id, scopes = _seed_root(session_factory, phase="campus_reports", poly=1, ptcd=1)
    targets = _campus_targets(scopes)
    with session_factory() as db:
        root = db.get(AcademicBulkOperationJob, root_id)
        attempts = {}
        for index, (target, status) in enumerate(zip(targets, ["completed", "failed"], strict=True)):
            scope_key, campus = target.rsplit(":", 1)
            scope = next(item for item in scopes if item["scope_key"] == scope_key)
            job = AcademicTeacherReportJob(
                id=f"report-final-{index}",
                parent_job_id=root_id,
                idempotency_key=f"report-final-key-{index}",
                job_type="scheduled_export_excel",
                status=status,
                term_id=scope["term_id"],
                branch=scope["branch"],
                campus=campus,
                request_json={"daily_stage": "campus_reports", "logical_target_key": target},
                result_json={},
            )
            db.add(job)
            attempts[target] = job.id
        state = dict(root.result_json)
        state["stage_round"] = 3
        state["attempts_by_stage"] = {"campus_reports": {"3": attempts}}
        root.result_json = state
        db.commit()
    monkeypatch.setattr(runtime, "SessionLocal", session_factory)

    result = runtime.run_daily_academic_pipeline(FakeCelery(), root_id)

    with session_factory() as db:
        assert result["code"] == "stage_retry_exhausted"
        assert db.query(AcademicBulkOperationJob).filter(
            AcademicBulkOperationJob.job_type == "daily_report_snapshot_attempt",
        ).count() == 0


def test_failed_snapshot_scope_retries_without_rebuilding_successful_scope(
    monkeypatch,
    session_factory,
):
    root_id, scopes = _seed_root(session_factory, phase="campus_snapshots")
    targets = [scope["scope_key"] for scope in scopes]
    with session_factory() as db:
        root = db.get(AcademicBulkOperationJob, root_id)
        attempts = {}
        for index, (target, status) in enumerate(zip(targets, ["completed", "failed"], strict=True)):
            scope = next(item for item in scopes if item["scope_key"] == target)
            job = AcademicBulkOperationJob(
                id=f"snapshot-attempt-{index}",
                parent_job_id=root_id,
                idempotency_key=f"snapshot-attempt-key-{index}",
                job_type="daily_report_snapshot_attempt",
                status=status,
                term_id=scope["term_id"],
                branch=scope["branch"],
                request_json={"snapshot_type": "campus_set", "logical_target_key": target},
                result_json={"snapshot_ids_by_campus": {scope["campuses"][0]: f"snapshot-{index}"}},
            )
            db.add(job)
            attempts[target] = job.id
        state = dict(root.result_json)
        state["attempts_by_stage"] = {"campus_snapshots": {"0": attempts}}
        root.result_json = state
        db.commit()
    monkeypatch.setattr(runtime, "SessionLocal", session_factory)

    runtime.run_daily_academic_pipeline(FakeCelery(), root_id)

    with session_factory() as db:
        root = db.get(AcademicBulkOperationJob, root_id)
        retry = root.result_json["attempts_by_stage"]["campus_snapshots"]["1"]
        assert list(retry) == [targets[1]]
        rows = db.query(AcademicBulkOperationJob).filter(
            AcademicBulkOperationJob.job_type == "daily_report_snapshot_attempt",
        ).all()
        assert len(rows) == 3
        assert sum(row.request_json["logical_target_key"] == targets[0] for row in rows) == 1


def test_ho_snapshot_attempts_start_only_after_all_campus_workbooks_complete(
    monkeypatch,
    session_factory,
):
    root_id, scopes = _seed_root(session_factory, phase="campus_reports", poly=1, ptcd=1)
    targets = _campus_targets(scopes)
    with session_factory() as db:
        root = db.get(AcademicBulkOperationJob, root_id)
        attempts = {}
        for index, target in enumerate(targets):
            scope_key, campus = target.rsplit(":", 1)
            scope = next(item for item in scopes if item["scope_key"] == scope_key)
            job = AcademicTeacherReportJob(
                id=f"campus-complete-{index}",
                parent_job_id=root_id,
                idempotency_key=f"campus-complete-key-{index}",
                job_type="scheduled_export_excel",
                status="completed",
                term_id=scope["term_id"],
                branch=scope["branch"],
                campus=campus,
                request_json={"daily_stage": "campus_reports", "logical_target_key": target},
                result_json={},
            )
            db.add(job)
            attempts[target] = job.id
        state = dict(root.result_json)
        state["attempts_by_stage"] = {"campus_reports": {"0": attempts}}
        root.result_json = state
        db.commit()
    monkeypatch.setattr(runtime, "SessionLocal", session_factory)

    result = runtime.run_daily_academic_pipeline(FakeCelery(), root_id)

    with session_factory() as db:
        root = db.get(AcademicBulkOperationJob, root_id)
        snapshot_jobs = db.query(AcademicBulkOperationJob).filter(
            AcademicBulkOperationJob.job_type == "daily_report_snapshot_attempt",
        ).all()
        assert result["phase"] == "ho_snapshots"
        assert root.result_json["phase"] == "ho_snapshots"
        assert len(snapshot_jobs) == 2
        assert {job.request_json["snapshot_type"] for job in snapshot_jobs} == {"ho"}
        assert db.query(AcademicTeacherReportJob).filter(
            AcademicTeacherReportJob.campus.is_(None),
        ).count() == 0
