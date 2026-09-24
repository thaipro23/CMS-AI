from datetime import datetime
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.models.academic import (
    AcademicBulkOperationJob,
    AcademicCampus,
    AcademicClass,
    AcademicTerm,
)
from app.services.academic import daily_academic_pipeline as runtime


VN_NOW = datetime(2026, 9, 24, 1, 0, tzinfo=ZoneInfo("Asia/Ho_Chi_Minh"))


class FakeCelery:
    def __init__(self):
        self.sent = []
        self.registered = {}
        self.conf = SimpleNamespace(
            beat_schedule={
                "academic-ap-sync-and-auto-map-03-vn": {"task": "legacy-ap"},
                "academic-score-sync-all-students": {"task": "legacy-score"},
            },
            task_routes={},
            task_annotations={},
        )

    def task(self, *, name):
        def decorate(function):
            self.registered[name] = function
            return function

        return decorate

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
    for model in (
        AcademicTerm,
        AcademicCampus,
        AcademicClass,
        AcademicBulkOperationJob,
    ):
        model.__table__.create(engine)
    factory = sessionmaker(bind=engine)
    yield factory
    engine.dispose()


def _seed_scope(session_factory, *, branch: str, term_id: str, campus: str):
    with session_factory() as db:
        db.add(AcademicTerm(
            id=term_id,
            term_code=f"FA26-{branch}",
            term_name="Fall 2026",
            branch=branch,
            active=True,
        ))
        db.add(AcademicCampus(
            id=f"campus-{branch}-{campus}",
            campus_code=campus,
            campus_name=campus.upper(),
            branch=branch,
            active=True,
        ))
        db.commit()


def test_beat_has_one_0100_pipeline_and_no_legacy_daily_publishers():
    celery_app = FakeCelery()

    runtime.register_daily_academic_pipeline_tasks(celery_app)

    schedule = celery_app.conf.beat_schedule
    assert schedule["academic-daily-pipeline-01-vn"]["task"] == runtime.DAILY_START_TASK
    assert "academic-ap-sync-and-auto-map-03-vn" not in schedule
    assert "academic-score-sync-all-students" not in schedule
    assert set(celery_app.registered) == {runtime.DAILY_START_TASK, runtime.DAILY_ROOT_TASK}
    assert celery_app.conf.task_routes[runtime.DAILY_START_TASK] == {"queue": "sync-bulk"}
    assert celery_app.conf.task_routes[runtime.DAILY_ROOT_TASK] == {"queue": "sync-bulk"}


def test_duplicate_start_reuses_one_root(monkeypatch, session_factory):
    _seed_scope(session_factory, branch="poly", term_id="term-poly", campus="hn")
    _seed_scope(session_factory, branch="ptcd", term_id="term-ptcd", campus="hcm")
    monkeypatch.setattr(runtime, "SessionLocal", session_factory)
    celery_app = FakeCelery()

    first = runtime.start_daily_academic_pipeline(celery_app, now=VN_NOW)
    second = runtime.start_daily_academic_pipeline(celery_app, now=VN_NOW)

    assert first["root_job_id"] == second["root_job_id"]
    assert len(celery_app.sent) == 1
    with session_factory() as db:
        roots = db.query(AcademicBulkOperationJob).filter(
            AcademicBulkOperationJob.job_type == runtime.DAILY_ROOT_JOB_TYPE,
        ).all()
        children = db.query(AcademicBulkOperationJob).filter(
            AcademicBulkOperationJob.parent_job_id == first["root_job_id"],
        ).all()
        assert len(roots) == 1
        assert len(children) == 4
        assert roots[0].request_json["required_branches"] == ["poly", "ptcd"]
        assert roots[0].result_json["phase"] == "ap_sync"


def test_duplicate_start_uses_frozen_scope_after_source_configuration_changes(
    monkeypatch,
    session_factory,
):
    _seed_scope(session_factory, branch="poly", term_id="term-poly", campus="hn")
    _seed_scope(session_factory, branch="ptcd", term_id="term-ptcd", campus="hcm")
    monkeypatch.setattr(runtime, "SessionLocal", session_factory)
    celery_app = FakeCelery()
    first = runtime.start_daily_academic_pipeline(celery_app, now=VN_NOW)

    with session_factory() as db:
        ptcd_campus = db.query(AcademicCampus).filter(
            AcademicCampus.branch == "ptcd",
        ).one()
        ptcd_campus.active = False
        db.commit()

    second = runtime.start_daily_academic_pipeline(celery_app, now=VN_NOW)

    assert second["ok"] is True
    assert second["root_job_id"] == first["root_job_id"]
    assert second["scope_count"] == 2


def test_missing_ptcd_scope_fails_before_ap_dispatch(monkeypatch, session_factory):
    _seed_scope(session_factory, branch="poly", term_id="term-poly", campus="hn")
    monkeypatch.setattr(runtime, "SessionLocal", session_factory)
    celery_app = FakeCelery()

    result = runtime.start_daily_academic_pipeline(celery_app, now=VN_NOW)

    assert result["ok"] is False
    assert result["code"] == "mandatory_branch_scope_missing"
    assert celery_app.sent == []
    with session_factory() as db:
        root = db.query(AcademicBulkOperationJob).one()
        assert root.status == "failed"
        assert root.idempotency_key == "academic-daily:v2:2026-09-24"
        assert db.query(AcademicBulkOperationJob).filter(
            AcademicBulkOperationJob.parent_job_id == root.id,
        ).count() == 0


def test_scope_discovery_is_sorted_and_rejects_unknown_active_branches(session_factory):
    _seed_scope(session_factory, branch="ptcd", term_id="term-z", campus="dn")
    _seed_scope(session_factory, branch="poly", term_id="term-a", campus="hn")
    with session_factory() as db:
        scopes = runtime.discover_daily_scopes(db)

        assert [(item["branch"], item["term_id"]) for item in scopes] == [
            ("poly", "term-a"),
            ("ptcd", "term-z"),
        ]

        db.add(AcademicTerm(
            id="term-unknown",
            term_code="FA26-UNKNOWN",
            term_name="Fall 2026",
            branch="other",
            active=True,
        ))
        db.commit()

        with pytest.raises(runtime.DailyScopeError) as caught:
            runtime.discover_daily_scopes(db)
        assert caught.value.code == "invalid_branch_scope"
