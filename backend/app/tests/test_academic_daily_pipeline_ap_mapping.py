from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.models.academic import (
    AcademicBulkOperationJob,
    AcademicCampus,
    AcademicClass,
    AcademicSyncRun,
    AcademicTerm,
)
from app.services.academic import daily_academic_pipeline as runtime


class FakeCelery:
    def __init__(self):
        self.sent = []

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
        AcademicSyncRun,
    ):
        model.__table__.create(engine)
    factory = sessionmaker(bind=engine)
    yield factory
    engine.dispose()


def _scope(branch: str) -> dict[str, object]:
    return {
        "policy_version": runtime.DAILY_POLICY_VERSION,
        "scope_key": f"{branch}:term-{branch}",
        "term_id": f"term-{branch}",
        "term_name": "Fall 2026",
        "branch": branch,
        "campuses": ["hn" if branch == "poly" else "hcm"],
        "class_ids": [],
        "class_to_campus": {},
        "scope_hash": f"hash-{branch}",
    }


def _seed_root_with_ap_attempts(session_factory, *, poly: str, ptcd: str, round_no: int):
    scopes = [_scope("poly"), _scope("ptcd")]
    with session_factory() as db:
        root = AcademicBulkOperationJob(
            id="root-1",
            job_type=runtime.DAILY_ROOT_JOB_TYPE,
            status="running",
            idempotency_key="academic-daily:v2:2026-09-24",
            requested_by=runtime.DAILY_SCHEDULER_ACTOR,
            request_json={
                "run_date_vn": "2026-09-24",
                "required_branches": ["poly", "ptcd"],
                "scopes": scopes,
            },
            result_json={
                "schema_version": runtime.DAILY_STATE_VERSION,
                "phase": "ap_sync",
                "stage_round": round_no,
                "stage_target_keys": [scope["scope_key"] for scope in scopes],
                "attempts_by_stage": {
                    "ap_sync": {
                        str(round_no): {
                            "poly:term-poly": "run-poly",
                            "ptcd:term-ptcd": "run-ptcd",
                        },
                    },
                },
                "artifacts": {},
            },
        )
        db.add(root)
        for branch, status in (("poly", poly), ("ptcd", ptcd)):
            db.add(AcademicSyncRun(
                id=f"run-{branch}",
                source="ap",
                mode="api_all_job",
                status=status,
                term_name="Fall 2026",
                branch=branch,
                idempotency_key=(
                    f"academic-daily:v2:2026-09-24:term-{branch}:{branch}:"
                    f"ap:attempt:{round_no}"
                ),
                counters_json={
                    "daily_pipeline": {
                        "root_job_id": "root-1",
                        "scope_key": f"{branch}:term-{branch}",
                        "stage": "ap_sync",
                        "round": round_no,
                        "source_run_id": f"run-{branch}",
                    },
                },
            ))
        db.commit()
        return root.id


def _fake_ap_enqueue(db, root, scope, round_no):
    branch = str(scope["branch"])
    run = AcademicSyncRun(
        id=f"run-{scope['term_id']}-{round_no}",
        source="ap",
        mode="api_all_job",
        status="queued",
        term_name=str(scope["term_name"]),
        branch=branch,
        idempotency_key=(
            f"academic-daily:v2:2026-09-24:{scope['term_id']}:{branch}:"
            f"ap:attempt:{round_no}"
        ),
        counters_json={
            "daily_pipeline": {
                "root_job_id": root.id,
                "scope_key": scope["scope_key"],
                "stage": "ap_sync",
                "round": round_no,
                "source_run_id": f"run-{scope['term_id']}-{round_no}",
            },
        },
    )
    db.add(run)
    db.commit()
    return run


def test_ap_failure_is_not_retried_until_other_branch_is_terminal(
    monkeypatch,
    session_factory,
):
    root_id = _seed_root_with_ap_attempts(
        session_factory,
        poly="failed",
        ptcd="running",
        round_no=0,
    )
    monkeypatch.setattr(runtime, "SessionLocal", session_factory)
    monkeypatch.setattr(runtime, "enqueue_ap_stage_attempt", _fake_ap_enqueue)

    result = runtime.run_daily_academic_pipeline(FakeCelery(), root_id)

    assert result["status"] == "waiting_stage"
    with session_factory() as db:
        assert db.query(AcademicSyncRun).filter(AcademicSyncRun.branch == "poly").count() == 1


def test_ap_retry_uses_new_run_id_and_same_logical_target(monkeypatch, session_factory):
    root_id = _seed_root_with_ap_attempts(
        session_factory,
        poly="failed",
        ptcd="completed",
        round_no=0,
    )
    monkeypatch.setattr(runtime, "SessionLocal", session_factory)
    monkeypatch.setattr(runtime, "enqueue_ap_stage_attempt", _fake_ap_enqueue)

    runtime.run_daily_academic_pipeline(FakeCelery(), root_id)

    with session_factory() as db:
        attempts = db.query(AcademicSyncRun).filter(
            AcademicSyncRun.branch == "poly",
        ).order_by(AcademicSyncRun.created_at.asc()).all()
        assert [item.counters_json["daily_pipeline"]["round"] for item in attempts] == [0, 1]
        assert len({item.id for item in attempts}) == 2
        assert {
            item.counters_json["daily_pipeline"]["scope_key"]
            for item in attempts
        } == {"poly:term-poly"}


def test_mapping_waits_for_every_ap_scope_to_succeed(monkeypatch, session_factory):
    root_id = _seed_root_with_ap_attempts(
        session_factory,
        poly="completed",
        ptcd="failed",
        round_no=runtime.MAX_STAGE_RETRY_ROUNDS,
    )
    monkeypatch.setattr(runtime, "SessionLocal", session_factory)

    result = runtime.run_daily_academic_pipeline(FakeCelery(), root_id)

    assert result["code"] == "stage_retry_exhausted"
    with session_factory() as db:
        assert db.query(AcademicBulkOperationJob).filter(
            AcademicBulkOperationJob.job_type == "subject_auto_map_all_sync",
        ).count() == 0


def test_ap_retry_round_still_respects_the_global_four_job_window(
    monkeypatch,
    session_factory,
):
    scopes = []
    with session_factory() as db:
        attempts = {}
        for index in range(5):
            branch = "poly" if index % 2 == 0 else "ptcd"
            term_id = f"term-{index}"
            scope = {
                **_scope(branch),
                "scope_key": f"{branch}:{term_id}",
                "term_id": term_id,
            }
            scopes.append(scope)
            run_id = f"run-initial-{index}"
            attempts[scope["scope_key"]] = run_id
            db.add(AcademicSyncRun(
                id=run_id,
                source="ap",
                mode="api_all_job",
                status="failed",
                term_name="Fall 2026",
                branch=branch,
                idempotency_key=f"initial:{index}",
                counters_json={"daily_pipeline": {"round": 0}},
            ))
        db.add(AcademicBulkOperationJob(
            id="root-many",
            job_type=runtime.DAILY_ROOT_JOB_TYPE,
            status="running",
            idempotency_key="academic-daily:v2:2026-09-24",
            request_json={"run_date_vn": "2026-09-24", "scopes": scopes},
            result_json={
                "phase": "ap_sync",
                "stage_round": 0,
                "stage_target_keys": [scope["scope_key"] for scope in scopes],
                "attempts_by_stage": {"ap_sync": {"0": attempts}},
                "artifacts": {},
            },
        ))
        db.commit()
    monkeypatch.setattr(runtime, "SessionLocal", session_factory)
    monkeypatch.setattr(runtime, "enqueue_ap_stage_attempt", _fake_ap_enqueue)

    runtime.run_daily_academic_pipeline(FakeCelery(), "root-many")

    with session_factory() as db:
        retries = [
            run
            for run in db.query(AcademicSyncRun).all()
            if (run.counters_json or {}).get("daily_pipeline", {}).get("round") == 1
        ]
        assert len(retries) == 4
