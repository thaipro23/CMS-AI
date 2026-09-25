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


def test_retention_defaults_are_bounded_for_production():
    assert settings.analytics_raw_event_retention_days == 7
    assert 100 <= settings.analytics_raw_event_cleanup_batch_size <= 50000
    assert settings.analytics_raw_event_cleanup_max_batches_per_run >= 1
    assert settings.analytics_raw_event_cleanup_interval_seconds >= 3600


def test_worker_registers_cleanup_route_and_schedule():
    worker_source = Path("app/worker.py")
    if not worker_source.exists():
        worker_source = Path("backend/app/worker.py")
    source = worker_source.read_text(encoding="utf-8")

    assert "'analytics_tracking_cleanup_task': {'queue': 'analytics'}" in source
    assert "_beat_schedule['analytics-tracking-retention-cleanup']" in source
    assert "@celery_app.task(name='analytics_tracking_cleanup_task')" in source
