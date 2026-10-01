from __future__ import annotations

from datetime import datetime
import importlib.util
from pathlib import Path

from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import create_engine, inspect
from sqlalchemy.orm import Session


MIGRATION_PATH = (
    Path(__file__).resolve().parents[2]
    / "alembic"
    / "versions"
    / "0070_analytics_materialized_event_receipts.py"
)


def test_materialized_event_receipt_migration_exists_after_tracking_indexes():
    assert MIGRATION_PATH.exists()
    spec = importlib.util.spec_from_file_location(
        "migration_0070_analytics_materialized_event_receipts",
        MIGRATION_PATH,
    )
    assert spec is not None and spec.loader is not None
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)

    assert migration.revision == "0070_analytics_materialized_event_receipts"
    assert migration.down_revision == "0069_analytics_tracking_query_indexes"

    from app.models.learning_analytics import AnalyticsTrackingEvent

    engine = create_engine("sqlite+pysqlite:///:memory:")
    AnalyticsTrackingEvent.__table__.create(engine)
    with engine.begin() as connection:
        migration.op = Operations(MigrationContext.configure(connection))
        migration.upgrade()

        inspector = inspect(connection)
        assert "analytics_materialized_event_receipts" in inspector.get_table_names()
        assert inspector.get_pk_constraint(
            "analytics_materialized_event_receipts"
        )["constrained_columns"] == ["event_id"]
        assert inspector.get_foreign_keys(
            "analytics_materialized_event_receipts"
        )[0]["referred_table"] == "analytics_tracking_events"

        migration.downgrade()
        assert "analytics_materialized_event_receipts" not in inspect(
            connection
        ).get_table_names()
    engine.dispose()


def test_receipt_records_the_canonical_identity_that_recalculation_used():
    from app.models.learning_analytics import (
        AnalyticsMaterializedEventReceipt,
        AnalyticsTrackingEvent,
    )
    from app.services.learning_analytics.analytics_core_service import (
        LearningAnalyticsCoreService,
    )

    engine = create_engine("sqlite+pysqlite:///:memory:")
    AnalyticsTrackingEvent.__table__.create(engine)
    AnalyticsMaterializedEventReceipt.__table__.create(engine)

    with Session(engine) as db:
        event = AnalyticsTrackingEvent(
            id="event-1",
            raw_line_hash="hash-event-1",
            event_time=datetime(2026, 9, 29, 8, 0, 0),
            event_type="play_video",
            username="openedx-alice",
            user_id="42",
            course_id="course-1",
            video_id="video-1",
        )
        db.add(event)
        db.commit()

        service = LearningAnalyticsCoreService(db)
        service._record_materialized_event_receipts(
            [(event, "ap-bob")],
            family="video",
        )
        db.commit()

        receipt = db.get(AnalyticsMaterializedEventReceipt, "event-1")
        assert receipt is not None
        assert receipt.canonical_username == "ap-bob"
        assert receipt.raw_username == "openedx-alice"
        assert receipt.raw_user_id == "42"
        assert receipt.family == "video"

    engine.dispose()


def test_video_recalculation_receipts_only_after_advancing_the_watermark(monkeypatch):
    from app.models.learning_analytics import (
        AnalyticsMaterializedEventReceipt,
        AnalyticsStudentVideoProgress,
        AnalyticsTrackingEvent,
    )
    from app.services.learning_analytics.analytics_core_service import (
        LearningAnalyticsCoreService,
    )

    engine = create_engine("sqlite+pysqlite:///:memory:")
    for model in (
        AnalyticsTrackingEvent,
        AnalyticsMaterializedEventReceipt,
        AnalyticsStudentVideoProgress,
    ):
        model.__table__.create(engine)

    with Session(engine) as db:
        db.add_all([
            AnalyticsStudentVideoProgress(
                id="progress-1",
                course_id="course-1",
                username="ap-bob",
                video_id="video-1",
                last_event_at=datetime(2026, 9, 29, 8, 0, 0),
                evidence_json={"last_loki_ts_ns": 100},
            ),
            AnalyticsTrackingEvent(
                id="video-covered",
                raw_line_hash="hash-video-covered",
                event_time=datetime(2026, 9, 29, 8, 0, 0),
                event_type="play_video",
                username="ap-bob",
                user_id="42",
                course_id="course-1",
                video_id="video-1",
                loki_ts_ns=100,
                current_time_seconds=1,
                video_duration_seconds=100,
            ),
            AnalyticsTrackingEvent(
                id="video-new",
                raw_line_hash="hash-video-new",
                event_time=datetime(2026, 9, 29, 8, 1, 0),
                event_type="pause_video",
                username="ap-bob",
                user_id="42",
                course_id="course-1",
                video_id="video-1",
                loki_ts_ns=200,
                current_time_seconds=10,
                video_duration_seconds=100,
            ),
        ])
        db.commit()

        service = LearningAnalyticsCoreService(db)
        monkeypatch.setattr(service, "_video_session_lookup", lambda **_kwargs: {})
        result = service.recalculate_course_video_progress(
            course_id="course-1",
            username="ap-bob",
        )

        assert result["video_progress_rows"] == 1
        receipts = db.query(AnalyticsMaterializedEventReceipt).order_by(
            AnalyticsMaterializedEventReceipt.event_id,
        ).all()
        assert [row.event_id for row in receipts] == ["video-covered", "video-new"]
        assert {row.canonical_username for row in receipts} == {"ap-bob"}
        progress = db.get(AnalyticsStudentVideoProgress, "progress-1")
        assert progress.evidence_json["last_loki_ts_ns"] == 200

    engine.dispose()


def test_quiz_recalculation_receipts_each_normalized_raw_event():
    from app.models.learning_analytics import (
        AnalyticsMaterializedEventReceipt,
        AnalyticsQuizAttempt,
        AnalyticsTrackingEvent,
    )
    from app.services.learning_analytics.analytics_core_service import (
        LearningAnalyticsCoreService,
    )

    engine = create_engine("sqlite+pysqlite:///:memory:")
    for model in (
        AnalyticsTrackingEvent,
        AnalyticsMaterializedEventReceipt,
        AnalyticsQuizAttempt,
    ):
        model.__table__.create(engine)

    with Session(engine) as db:
        db.add(AnalyticsTrackingEvent(
            id="quiz-event",
            raw_line_hash="hash-quiz-event",
            event_time=datetime(2026, 9, 29, 9, 0, 0),
            event_type="problem_check",
            event_source="server",
            username="ap-bob",
            user_id="42",
            course_id="course-1",
            raw_event={"problem_id": "block-v1:org+course+run+type@problem+block@p1"},
            page_url="/courses/course-1/xblock/block-v1:org+course+run+type@vertical+block@u1",
        ))
        db.commit()

        service = LearningAnalyticsCoreService(db)
        result = service.recalculate_course_quiz_attempts(
            course_id="course-1",
            username="ap-bob",
        )

        assert result["quiz_attempt_rows"] == 1
        receipt = db.get(AnalyticsMaterializedEventReceipt, "quiz-event")
        assert receipt is not None
        assert receipt.family == "quiz"
        assert receipt.canonical_username == "ap-bob"

    engine.dispose()
