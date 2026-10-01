from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

from app.core.config import settings
from app.services.learning_analytics.analytics_core_service import LearningAnalyticsCoreService


def _service_without_db() -> LearningAnalyticsCoreService:
    return object.__new__(LearningAnalyticsCoreService)


def test_canonical_tracking_identity_prefers_openedx_user_id_mapping():
    event = SimpleNamespace(user_id="13668", username="TH09593")
    identity = {
        "user_id_to_ap": {"13668": "PS00001"},
        "username_to_ap": {"th09593": "PS99999"},
    }

    assert LearningAnalyticsCoreService._canonical_event_username(event, identity) == "PS00001"


def test_canonical_tracking_identity_falls_back_to_openedx_username():
    event = SimpleNamespace(user_id=None, username="TH09593")
    identity = {
        "user_id_to_ap": {},
        "username_to_ap": {"th09593": "PS00001"},
    }

    assert LearningAnalyticsCoreService._canonical_event_username(event, identity) == "PS00001"


def test_video_watermark_accepts_only_new_loki_events():
    old = SimpleNamespace(
        loki_ts_ns=100,
        event_time=datetime(2026, 9, 25, 1, 0, 0),
    )
    new = SimpleNamespace(
        loki_ts_ns=101,
        event_time=datetime(2026, 9, 25, 1, 0, 1),
    )

    assert LearningAnalyticsCoreService._video_event_is_new(
        old,
        last_loki_ts_ns=100,
        last_event_at=datetime(2026, 9, 25, 1, 0, 0),
    ) is False
    assert LearningAnalyticsCoreService._video_event_is_new(
        new,
        last_loki_ts_ns=100,
        last_event_at=datetime(2026, 9, 25, 1, 0, 0),
    ) is True


def test_video_watermark_falls_back_to_event_time_without_loki_timestamp():
    last = datetime(2026, 9, 25, 1, 0, 0)
    event = SimpleNamespace(
        loki_ts_ns=None,
        event_time=last + timedelta(seconds=1),
    )

    assert LearningAnalyticsCoreService._video_event_is_new(
        event,
        last_loki_ts_ns=0,
        last_event_at=last,
    ) is True


def test_cleanup_never_runs_on_non_postgres():
    service = _service_without_db()
    service.db = MagicMock()
    service._is_postgres = MagicMock(return_value=False)

    result = service.cleanup_tracking_events()

    assert result == {
        "status": "skipped_non_postgres",
        "deleted": 0,
    }


class _ExecuteResult:
    def __init__(self, *, scalar_value=None, rows=None):
        self._scalar_value = scalar_value
        self._rows = list(rows or [])

    def scalar(self):
        return self._scalar_value

    def scalars(self):
        return self

    def all(self):
        return list(self._rows)


class _CountQuery:
    def __init__(self, db):
        self.db = db

    def filter(self, *_args, **_kwargs):
        return self

    def count(self):
        return self.db.counts.pop(0)


class _CleanupDB:
    def __init__(self, *, candidates, proven, deleted, remaining_old):
        self.counts = [0, 1, 1, remaining_old]
        self.candidate_batches = [list(batch) for batch in candidates]
        self.proven_batches = [list(batch) for batch in proven]
        self.deleted_batches = [list(batch) for batch in deleted]
        self.executions: list[tuple[str, dict | None]] = []
        self.commits = 0
        self.rollbacks = 0

    def query(self, *_args, **_kwargs):
        return _CountQuery(self)

    def execute(self, statement, params=None):
        sql = " ".join(str(statement).split())
        self.executions.append((sql, params))
        lowered = sql.lower()
        if "pg_try_advisory_xact_lock" in lowered:
            return _ExecuteResult(scalar_value=True)
        if "set_config('statement_timeout'" in lowered:
            return _ExecuteResult(scalar_value="60000ms")
        if (
            lowered.startswith("select e.id")
            and "order by e.created_at asc, e.id asc" in lowered
            and "for update skip locked" in lowered
        ):
            return _ExecuteResult(rows=self.candidate_batches.pop(0))
        if (
            lowered.startswith("select e.id")
            and "analytics_materialized_event_receipts" in lowered
        ):
            return _ExecuteResult(rows=self.proven_batches.pop(0))
        if lowered.startswith("delete from analytics_tracking_events"):
            return _ExecuteResult(rows=self.deleted_batches.pop(0))
        raise AssertionError(f"Unexpected cleanup SQL: {sql}")

    def commit(self):
        self.commits += 1

    def rollback(self):
        self.rollbacks += 1


def test_cleanup_uses_bounded_candidate_proof_and_delete_phases(monkeypatch):
    service = _service_without_db()
    service.db = _CleanupDB(
        candidates=[["event-safe", "event-blocked"], []],
        proven=[["event-safe"]],
        deleted=[["event-safe"]],
        remaining_old=7,
    )
    service._is_postgres = MagicMock(return_value=True)
    monkeypatch.setattr(settings, "analytics_raw_event_cleanup_max_batches_per_run", 2)

    result = service.cleanup_tracking_events()

    assert result["status"] == "completed"
    assert result["candidate_rows_scanned"] == 2
    assert result["proven_materialized"] == 1
    assert result["deleted"] == 1
    assert result["blocked_unmaterialized"] == 1
    assert result["batches"] == 1
    assert result["remaining_old_rows_all_types"] == 7

    executions = service.db.executions
    timeout_calls = [item for item in executions if "set_config('statement_timeout'" in item[0].lower()]
    assert len(timeout_calls) == 2
    assert all(item[1]["statement_timeout"] == "60000ms" for item in timeout_calls)

    candidate_sql = next(
        sql for sql, _params in executions
        if sql.lower().startswith("select e.id")
    )
    assert "JOIN" not in candidate_sql.upper()
    assert "ORDER BY e.created_at ASC, e.id ASC" in candidate_sql
    assert "LIMIT" in candidate_sql

    proof_sql = next(
        sql for sql, _params in executions
        if (
            sql.lower().startswith("select e.id")
            and "analytics_materialized_event_receipts" in sql.lower()
        )
    )
    assert "ANALYTICS_MATERIALIZED_EVENT_RECEIPTS" in proof_sql.upper()
    assert "ANALYTICS_STUDENT_VIDEO_PROGRESS" not in proof_sql.upper()
    assert "ANALYTICS_QUIZ_ATTEMPTS" not in proof_sql.upper()
    assert " OR " not in proof_sql.upper()

    delete_call = next(
        (sql, params) for sql, params in executions
        if sql.lower().startswith("delete from analytics_tracking_events")
    )
    assert delete_call[1]["safe_ids"] == ["event-safe"]


def test_cleanup_reports_oldest_window_blocked_when_nothing_is_materialized(monkeypatch):
    service = _service_without_db()
    service.db = _CleanupDB(
        candidates=[["event-blocked"]],
        proven=[[]],
        deleted=[],
        remaining_old=11,
    )
    service._is_postgres = MagicMock(return_value=True)
    monkeypatch.setattr(settings, "analytics_raw_event_cleanup_max_batches_per_run", 10)

    result = service.cleanup_tracking_events()

    assert result["status"] == "blocked_unmaterialized"
    assert result["candidate_rows_scanned"] == 1
    assert result["proven_materialized"] == 0
    assert result["deleted"] == 0
    assert result["blocked_unmaterialized"] == 1
    assert result["remaining_old_rows_all_types"] == 11
    assert not any(
        sql.lower().startswith("delete from analytics_tracking_events")
        for sql, _params in service.db.executions
    )


def test_cleanup_skips_before_sql_when_recalculate_job_is_active():
    service = _service_without_db()
    db = _CleanupDB(candidates=[], proven=[], deleted=[], remaining_old=0)
    db.counts = [2]
    service.db = db
    service._is_postgres = MagicMock(return_value=True)

    result = service.cleanup_tracking_events()

    assert result == {
        "status": "skipped_active_recalculate_jobs",
        "active_jobs": 2,
        "deleted": 0,
    }
    assert db.executions == []


def test_retention_defaults_are_bounded_for_production():
    assert settings.analytics_raw_event_retention_days == 3
    assert settings.analytics_raw_event_cleanup_batch_size == 5000
    assert settings.analytics_raw_event_cleanup_max_batches_per_run == 10
    assert settings.analytics_raw_event_cleanup_interval_seconds == 3600
    assert settings.analytics_raw_event_cleanup_statement_timeout_ms == 60000


def test_worker_registers_cleanup_route_and_schedule():
    worker_source = Path("app/worker.py")
    if not worker_source.exists():
        worker_source = Path("backend/app/worker.py")
    source = worker_source.read_text(encoding="utf-8")

    assert "'analytics_tracking_cleanup_task': {'queue': 'analytics'}" in source
    assert "_beat_schedule['analytics-tracking-retention-cleanup']" in source
    assert "@celery_app.task(name='analytics_tracking_cleanup_task')" in source
