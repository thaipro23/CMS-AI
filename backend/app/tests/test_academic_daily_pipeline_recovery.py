from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from types import SimpleNamespace
import threading

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.models.academic import (
    AcademicBulkOperationJob,
    AcademicClassSyncJob,
)
from app.services.academic import daily_academic_pipeline as runtime


class FakeCelery:
    def __init__(self):
        self.sent = []
        self._guard = threading.Lock()

    def send_task(self, name, args=None, **options):
        with self._guard:
            self.sent.append((name, list(args or []), options))
            return SimpleNamespace(id=f"task-{len(self.sent)}")


@pytest.fixture
def session_factory():
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    AcademicBulkOperationJob.__table__.create(engine)
    AcademicClassSyncJob.__table__.create(engine)
    factory = sessionmaker(bind=engine)
    yield factory
    engine.dispose()


def test_recovery_republishes_same_attempt_without_consuming_retry_round(
    monkeypatch,
    session_factory,
):
    due = (datetime.utcnow() - timedelta(seconds=1)).isoformat()
    with session_factory() as db:
        db.add(AcademicBulkOperationJob(
            id="root-recovery",
            job_type=runtime.DAILY_ROOT_JOB_TYPE,
            status="running",
            idempotency_key="academic-daily:v2:2026-09-24",
            request_json={"run_date_vn": "2026-09-24", "scopes": []},
            result_json={
                "phase": "score_update",
                "stage_round": 2,
                "stage_target_keys": ["class-1"],
                "attempts_by_stage": {
                    "score_update": {"2": {"class-1": "score-job-2"}},
                },
                "continuation": {
                    "status": "dispatch_pending",
                    "attempt_count": 1,
                    "due_at": due,
                    "task_name": runtime.DAILY_ROOT_TASK,
                    "args": ["root-recovery"],
                    "queue": "sync-bulk",
                    "countdown": 15,
                },
            },
        ))
        db.add(AcademicClassSyncJob(
            id="score-job-2",
            job_type="learning_sync",
            status="running",
            class_id="class-1",
            parent_job_id="scope-parent-1",
            idempotency_key="score-job-2-key",
            request_json={
                "daily_root_job_id": "root-recovery",
                "logical_target_key": "score_update:poly:term-1:class-1",
                "attempt_no": 2,
            },
            result_json={},
        ))
        db.commit()
    monkeypatch.setattr(runtime, "SessionLocal", session_factory)

    result = runtime.recover_daily_academic_pipeline(FakeCelery())

    assert result["republished"] == 1
    with session_factory() as db:
        root = db.get(AcademicBulkOperationJob, "root-recovery")
        assert root.result_json["stage_round"] == 2
        assert db.query(AcademicClassSyncJob).filter(
            AcademicClassSyncJob.request_json["logical_target_key"].as_string()
            == "score_update:poly:term-1:class-1",
        ).count() == 1


def test_runtime_exhaustion_preserves_stage_diagnostics(
    monkeypatch,
    session_factory,
):
    created_at = datetime.utcnow() - timedelta(hours=25)
    with session_factory() as db:
        db.add(AcademicBulkOperationJob(
            id="root-expired",
            job_type=runtime.DAILY_ROOT_JOB_TYPE,
            status="running",
            idempotency_key="academic-daily:v2:2026-09-23",
            created_at=created_at,
            request_json={"run_date_vn": "2026-09-23", "scopes": []},
            result_json={
                "phase": "campus_reports",
                "stage_round": 3,
                "stage_target_keys": ["ptcd:term-1:hn"],
                "last_child_error": "export worker lost",
                "continuation": {
                    "status": "dispatch_pending",
                    "attempt_count": 1,
                    "due_at": created_at.isoformat(),
                    "task_name": runtime.DAILY_ROOT_TASK,
                    "args": ["root-expired"],
                    "queue": "sync-bulk",
                    "countdown": 15,
                },
            },
        ))
        db.commit()
    monkeypatch.setattr(runtime, "SessionLocal", session_factory)

    result = runtime.recover_daily_academic_pipeline(FakeCelery())

    assert result["failed"] == 1
    with session_factory() as db:
        root = db.get(AcademicBulkOperationJob, "root-expired")
        assert root.status == "failed"
        assert root.result_json["code"] == "pipeline_runtime_exceeded"
        assert root.result_json["phase"] == "campus_reports"
        assert root.result_json["stage_round"] == 3
        assert root.result_json["failed_target_key"] == "ptcd:term-1:hn"
        assert root.result_json["last_child_error"] == "export worker lost"


def test_duplicate_root_delivery_cannot_publish_five_active_jobs(
    monkeypatch,
    tmp_path,
):
    engine = create_engine(
        f"sqlite+pysqlite:///{tmp_path / 'daily-recovery.sqlite'}",
        connect_args={"check_same_thread": False, "timeout": 10},
    )
    AcademicBulkOperationJob.__table__.create(engine)
    AcademicClassSyncJob.__table__.create(engine)
    factory = sessionmaker(bind=engine)
    scopes = []
    for branch in ("poly", "ptcd"):
        class_ids = [f"class-{branch}-{index}" for index in range(6)]
        scopes.append({
            "policy_version": runtime.DAILY_POLICY_VERSION,
            "scope_key": f"{branch}:term-{branch}",
            "scope_hash": f"hash-{branch}",
            "term_id": f"term-{branch}",
            "term_name": "Fall 2026",
            "branch": branch,
            "campuses": [f"campus-{branch}"],
            "class_ids": class_ids,
            "class_to_campus": {class_id: f"campus-{branch}" for class_id in class_ids},
        })
    targets = [
        class_id
        for index in range(6)
        for scope in scopes
        for class_id in scope["class_ids"][index:index + 1]
    ]
    with factory() as db:
        root = AcademicBulkOperationJob(
            id="root-concurrent",
            job_type=runtime.DAILY_ROOT_JOB_TYPE,
            status="running",
            idempotency_key="academic-daily:v2:2026-09-24",
            request_json={"run_date_vn": "2026-09-24", "scopes": scopes},
            result_json={
                "phase": "account_enrollment",
                "stage_round": 0,
                "stage_target_keys": targets,
                "attempts_by_stage": {},
                "frozen_scopes_after_ap": {scope["scope_key"]: scope for scope in scopes},
                "artifacts": {},
            },
        )
        db.add(root)
        db.commit()
        runtime.ensure_scope_parents(db, root, scopes)
    monkeypatch.setattr(runtime, "SessionLocal", factory)
    celery = FakeCelery()

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(
            lambda _index: runtime.run_daily_academic_pipeline(celery, "root-concurrent"),
            range(2),
        ))

    assert all(result["ok"] for result in results)
    with factory() as db:
        assert db.query(AcademicClassSyncJob).filter(
            AcademicClassSyncJob.status.in_(["queued", "running"]),
        ).count() <= 4
    engine.dispose()
