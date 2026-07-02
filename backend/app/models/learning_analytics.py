from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any
from sqlalchemy import Boolean, DateTime, Float, Index, Integer, JSON, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


def _uuid() -> str:
    return str(uuid.uuid4())


class AnalyticsIngestCheckpoint(Base):
    """Incremental tracking.log checkpoint.

    This is intentionally small and independent from Open edX. It prevents
    request-time reads of the full tracking log and lets one ingest run resume
    from the last verified offset.
    """

    __tablename__ = 'analytics_ingest_checkpoints'

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    checkpoint_key: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    file_path: Mapped[str] = mapped_column(String(1024), default='')
    file_inode: Mapped[str | None] = mapped_column(String(128), nullable=True)
    file_size: Mapped[int] = mapped_column(Integer, default=0)
    last_offset: Mapped[int] = mapped_column(Integer, default=0)
    last_run_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, index=True)
    last_status: Mapped[str] = mapped_column(String(50), default='never_run', index=True)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    total_lines_read: Mapped[int] = mapped_column(Integer, default=0)
    total_events_inserted: Mapped[int] = mapped_column(Integer, default=0)
    total_duplicate_events: Mapped[int] = mapped_column(Integer, default=0)
    total_parse_errors: Mapped[int] = mapped_column(Integer, default=0)
    stats_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class AnalyticsTrackingEvent(Base):
    """Normalized Open edX tracking events used by Aspects-lite analytics."""

    __tablename__ = 'analytics_tracking_events'

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    raw_line_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    event_time: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, index=True)
    event_type: Mapped[str] = mapped_column(String(120), index=True)
    event_source: Mapped[str] = mapped_column(String(80), default='openedx_tracking_log', index=True)
    user_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    username: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    course_id: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    org_id: Mapped[str | None] = mapped_column(String(80), nullable=True, index=True)
    session_id: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    video_id: Mapped[str | None] = mapped_column(String(512), nullable=True, index=True)
    video_code: Mapped[str | None] = mapped_column(String(512), nullable=True, index=True)
    video_duration_seconds: Mapped[float | None] = mapped_column(Float, nullable=True)
    current_time_seconds: Mapped[float | None] = mapped_column(Float, nullable=True)
    page_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    referer: Mapped[str | None] = mapped_column(Text, nullable=True)
    raw_event: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True, default=dict)
    raw_context: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True, default=dict)
    raw_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)

    __table_args__ = (
        Index('ix_analytics_events_course_user_time', 'course_id', 'username', 'event_time'),
        Index('ix_analytics_events_course_video_time', 'course_id', 'video_id', 'event_time'),
        Index('ix_analytics_events_type_time', 'event_type', 'event_time'),
    )


class AnalyticsCourseSession(Base):
    """Course -> Bài/Session -> videos/quizzes/deadline mapping snapshot."""

    __tablename__ = 'analytics_course_sessions'

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    course_id: Mapped[str] = mapped_column(String(255), index=True)
    session_key: Mapped[str] = mapped_column(String(512), index=True)
    session_index: Mapped[int] = mapped_column(Integer, index=True)
    session_title: Mapped[str] = mapped_column(String(512), default='')
    week_index: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    deadline_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, index=True)
    deadline_source: Mapped[str] = mapped_column(String(50), default='INFERRED', index=True)
    deadline_mapping_quality: Mapped[str] = mapped_column(String(50), default='PARTIAL', index=True)
    total_parts: Mapped[int] = mapped_column(Integer, default=0)
    total_videos: Mapped[int] = mapped_column(Integer, default=0)
    quiz_usage_key: Mapped[str | None] = mapped_column(String(512), nullable=True, index=True)
    components_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True, default=dict)
    source: Mapped[str] = mapped_column(String(80), default='manual_or_sync', index=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    rebuilt_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint('course_id', 'session_index', name='uq_analytics_course_session_index'),
        UniqueConstraint('course_id', 'session_key', name='uq_analytics_course_session_key'),
        Index('ix_analytics_course_sessions_course_week', 'course_id', 'week_index'),
    )


class AnalyticsStudentVideoProgress(Base):
    __tablename__ = 'analytics_student_video_progress'

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    course_id: Mapped[str] = mapped_column(String(255), index=True)
    username: Mapped[str] = mapped_column(String(255), index=True)
    user_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    session_key: Mapped[str | None] = mapped_column(String(512), nullable=True, index=True)
    session_index: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    video_id: Mapped[str] = mapped_column(String(512), index=True)
    video_code: Mapped[str | None] = mapped_column(String(512), nullable=True)
    component_title: Mapped[str] = mapped_column(String(512), default='')
    duration_seconds: Mapped[float | None] = mapped_column(Float, nullable=True)
    max_position_seconds: Mapped[float | None] = mapped_column(Float, nullable=True)
    completion_percent: Mapped[float | None] = mapped_column(Float, nullable=True)
    estimated_watch_seconds: Mapped[float] = mapped_column(Float, default=0.0)
    estimated_watch_percent: Mapped[float | None] = mapped_column(Float, nullable=True)
    play_count: Mapped[int] = mapped_column(Integer, default=0)
    pause_count: Mapped[int] = mapped_column(Integer, default=0)
    stop_count: Mapped[int] = mapped_column(Integer, default=0)
    seek_count: Mapped[int] = mapped_column(Integer, default=0)
    is_completed: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    is_suspicious: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    suspicious_reason: Mapped[str] = mapped_column(Text, default='')
    evidence_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True, default=dict)
    first_played_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, index=True)
    last_event_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, index=True)
    calculated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)

    __table_args__ = (
        UniqueConstraint('course_id', 'username', 'video_id', name='uq_analytics_student_video'),
        Index('ix_analytics_video_progress_course_user_session', 'course_id', 'username', 'session_index'),
    )


class AnalyticsStudentSessionProgress(Base):
    __tablename__ = 'analytics_student_session_progress'

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    course_id: Mapped[str] = mapped_column(String(255), index=True)
    username: Mapped[str] = mapped_column(String(255), index=True)
    user_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    session_key: Mapped[str] = mapped_column(String(512), index=True)
    session_index: Mapped[int] = mapped_column(Integer, index=True)
    session_title: Mapped[str] = mapped_column(String(512), default='')
    week_index: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    deadline_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, index=True)
    deadline_source: Mapped[str] = mapped_column(String(50), default='INFERRED')
    total_videos: Mapped[int] = mapped_column(Integer, default=0)
    videos_seen: Mapped[int] = mapped_column(Integer, default=0)
    videos_completed: Mapped[int] = mapped_column(Integer, default=0)
    avg_video_completion_percent: Mapped[float | None] = mapped_column(Float, nullable=True)
    estimated_watch_seconds: Mapped[float] = mapped_column(Float, default=0.0)
    quiz_attempted: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    quiz_completed: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    quiz_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, index=True)
    last_activity_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, index=True)
    completed_before_deadline: Mapped[bool | None] = mapped_column(Boolean, nullable=True, index=True)
    completed_late: Mapped[bool | None] = mapped_column(Boolean, nullable=True, index=True)
    session_learning_status: Mapped[str] = mapped_column(String(50), default='INSUFFICIENT_DATA', index=True)
    reason_codes: Mapped[list[str] | None] = mapped_column(JSON, nullable=True, default=list)
    evidence_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True, default=dict)
    calculated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)

    __table_args__ = (
        UniqueConstraint('course_id', 'username', 'session_index', name='uq_analytics_student_session'),
        Index('ix_analytics_session_progress_course_user_week', 'course_id', 'username', 'week_index'),
    )


class AnalyticsLearningBehaviorSnapshot(Base):
    __tablename__ = 'analytics_learning_behavior_snapshots'

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    class_id: Mapped[str | None] = mapped_column(String, nullable=True, index=True)
    course_id: Mapped[str] = mapped_column(String(255), index=True)
    username: Mapped[str] = mapped_column(String(255), index=True)
    user_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    classification: Mapped[str] = mapped_column(String(50), default='INSUFFICIENT_DATA', index=True)
    display_label: Mapped[str] = mapped_column(String(255), default='Chưa đủ dữ liệu')
    confidence_score: Mapped[float] = mapped_column(Float, default=0.0)
    real_learning_score: Mapped[float] = mapped_column(Float, default=0.0)
    idle_score: Mapped[float] = mapped_column(Float, default=0.0)
    suspicious_score: Mapped[float] = mapped_column(Float, default=0.0)
    deadline_compliance_percent: Mapped[float | None] = mapped_column(Float, nullable=True)
    crammed_session_count: Mapped[int] = mapped_column(Integer, default=0)
    quiz_before_video_count: Mapped[int] = mapped_column(Integer, default=0)
    reason_codes: Mapped[list[str] | None] = mapped_column(JSON, nullable=True, default=list)
    human_readable_summary: Mapped[str] = mapped_column(Text, default='')
    recommended_action: Mapped[str] = mapped_column(String(80), default='INSUFFICIENT_DATA_RECHECK_LATER')
    data_quality: Mapped[str] = mapped_column(String(50), default='MISSING', index=True)
    evidence_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True, default=dict)
    last_activity_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, index=True)
    calculated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)

    __table_args__ = (
        UniqueConstraint('class_id', 'course_id', 'username', name='uq_analytics_behavior_class_course_user'),
        Index('ix_analytics_behavior_class_classification', 'class_id', 'classification'),
        Index('ix_analytics_behavior_course_classification', 'course_id', 'classification'),
    )
