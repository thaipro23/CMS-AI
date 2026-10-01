from __future__ import annotations

from datetime import datetime

from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session

from app.models.learning_analytics import AnalyticsTrackingEvent
from app.services.learning_analytics.analytics_core_service import (
    LearningAnalyticsCoreService,
)


def _tracking_event(
    *,
    event_id: str,
    username: str | None,
    user_id: str | None,
    event_time: datetime | None,
    loki_ts_ns: int | None,
) -> AnalyticsTrackingEvent:
    return AnalyticsTrackingEvent(
        id=event_id,
        raw_line_hash=f"hash-{event_id}",
        event_time=event_time,
        event_type="play_video",
        username=username,
        user_id=user_id,
        course_id="course-v1:FPL+SOA102+FA26",
        video_id="video-1",
        loki_ts_ns=loki_ts_ns,
    )


def _seed_events(engine) -> None:
    AnalyticsTrackingEvent.__table__.create(engine)
    with Session(engine) as db:
        db.add_all([
            _tracking_event(
                event_id="event-dual",
                username="raw-a",
                user_id="uid-a",
                event_time=datetime(2026, 9, 29, 8, 0, 0),
                loki_ts_ns=100,
            ),
            _tracking_event(
                event_id="event-username",
                username="raw-a",
                user_id="uid-other",
                event_time=datetime(2026, 9, 29, 8, 0, 0),
                loki_ts_ns=None,
            ),
            _tracking_event(
                event_id="event-user-id",
                username="raw-other",
                user_id="uid-a",
                event_time=None,
                loki_ts_ns=50,
            ),
            _tracking_event(
                event_id="event-outside",
                username="outside",
                user_id="uid-outside",
                event_time=datetime(2026, 9, 29, 7, 0, 0),
                loki_ts_ns=10,
            ),
        ])
        db.commit()


def test_identity_loader_uses_two_queries_deduplicates_and_sorts_stably():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    _seed_events(engine)
    statements: list[str] = []

    @event.listens_for(engine, "before_cursor_execute")
    def capture_selects(_conn, _cursor, statement, _parameters, _context, _executemany):
        if statement.lstrip().upper().startswith("SELECT"):
            statements.append(statement)

    with Session(engine) as db:
        service = LearningAnalyticsCoreService(db)
        base_query = db.query(AnalyticsTrackingEvent).filter(
            AnalyticsTrackingEvent.course_id == "course-v1:FPL+SOA102+FA26",
            AnalyticsTrackingEvent.event_type == "play_video",
        )

        rows = service._tracking_events_for_identity(
            base_query,
            {
                "raw_usernames": ["raw-a"],
                "raw_user_ids": ["uid-a"],
            },
        )

    assert [row.id for row in rows] == [
        "event-dual",
        "event-username",
        "event-user-id",
    ]
    assert len(statements) == 2
    normalized = [" ".join(statement.lower().split()) for statement in statements]
    assert sum("analytics_tracking_events.username in" in statement for statement in normalized) == 1
    assert sum("analytics_tracking_events.user_id in" in statement for statement in normalized) == 1
    assert all(" or " not in statement for statement in normalized)
    engine.dispose()


def test_identity_loader_with_empty_identity_does_not_query_events():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    _seed_events(engine)
    select_count = 0

    @event.listens_for(engine, "before_cursor_execute")
    def capture_selects(_conn, _cursor, statement, _parameters, _context, _executemany):
        nonlocal select_count
        if statement.lstrip().upper().startswith("SELECT"):
            select_count += 1

    with Session(engine) as db:
        service = LearningAnalyticsCoreService(db)
        rows = service._tracking_events_for_identity(
            db.query(AnalyticsTrackingEvent),
            {"raw_usernames": [], "raw_user_ids": []},
        )

    assert rows == []
    assert select_count == 0
    engine.dispose()


def test_class_event_counts_use_canonical_identity_without_double_count(monkeypatch):
    engine = create_engine("sqlite+pysqlite:///:memory:")
    _seed_events(engine)
    with Session(engine) as db:
        service = LearningAnalyticsCoreService(db)
        identity = {
            "raw_usernames": ["raw-a"],
            "raw_user_ids": ["uid-a"],
            "username_to_ap": {"raw-a": "AP001", "raw-other": "AP001"},
            "user_id_to_ap": {"uid-a": "AP001"},
        }
        monkeypatch.setattr(
            service,
            "_class_tracking_identity_maps",
            lambda **_kwargs: identity,
        )

        counts = service._events_count_by_username(
            course_id="course-v1:FPL+SOA102+FA26",
            usernames=["AP001"],
            class_id="class-1",
        )

    assert counts == {"AP001": 3}
    engine.dispose()
