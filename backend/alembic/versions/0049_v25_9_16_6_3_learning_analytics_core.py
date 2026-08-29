"""v25.9.16.6.3 learning analytics core phase 0-4

Revision ID: 0049_v25_9_16_6_3
Revises: 0048_v25_9_16_5_84
Create Date: 2026-07-01
"""

from alembic import op
import sqlalchemy as sa

revision = '0049_v25_9_16_6_3'
down_revision = '0048_v25_9_16_5_84_teacher_report_cache'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'analytics_ingest_checkpoints',
        sa.Column('id', sa.String(), primary_key=True),
        sa.Column('checkpoint_key', sa.String(length=255), nullable=False),
        sa.Column('file_path', sa.String(length=1024), nullable=False, server_default=''),
        sa.Column('file_inode', sa.String(length=128), nullable=True),
        sa.Column('file_size', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('last_offset', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('last_run_at', sa.DateTime(), nullable=True),
        sa.Column('last_status', sa.String(length=50), nullable=False, server_default='never_run'),
        sa.Column('last_error', sa.Text(), nullable=True),
        sa.Column('total_lines_read', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('total_events_inserted', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('total_duplicate_events', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('total_parse_errors', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('stats_json', sa.JSON(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
    )
    op.create_index('ix_analytics_ingest_checkpoints_checkpoint_key', 'analytics_ingest_checkpoints', ['checkpoint_key'], unique=True)
    op.create_index('ix_analytics_ingest_checkpoints_last_run_at', 'analytics_ingest_checkpoints', ['last_run_at'])
    op.create_index('ix_analytics_ingest_checkpoints_last_status', 'analytics_ingest_checkpoints', ['last_status'])

    op.create_table(
        'analytics_tracking_events',
        sa.Column('id', sa.String(), primary_key=True),
        sa.Column('raw_line_hash', sa.String(length=64), nullable=False),
        sa.Column('event_time', sa.DateTime(), nullable=True),
        sa.Column('event_type', sa.String(length=120), nullable=False),
        sa.Column('event_source', sa.String(length=80), nullable=False, server_default='openedx_tracking_log'),
        sa.Column('user_id', sa.String(length=64), nullable=True),
        sa.Column('username', sa.String(length=255), nullable=True),
        sa.Column('course_id', sa.String(length=255), nullable=True),
        sa.Column('org_id', sa.String(length=80), nullable=True),
        sa.Column('session_id', sa.String(length=255), nullable=True),
        sa.Column('video_id', sa.String(length=512), nullable=True),
        sa.Column('video_code', sa.String(length=512), nullable=True),
        sa.Column('video_duration_seconds', sa.Float(), nullable=True),
        sa.Column('current_time_seconds', sa.Float(), nullable=True),
        sa.Column('page_url', sa.Text(), nullable=True),
        sa.Column('referer', sa.Text(), nullable=True),
        sa.Column('raw_event', sa.JSON(), nullable=True),
        sa.Column('raw_context', sa.JSON(), nullable=True),
        sa.Column('raw_json', sa.JSON(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
    )
    op.create_index('ix_analytics_tracking_events_raw_line_hash', 'analytics_tracking_events', ['raw_line_hash'], unique=True)
    op.create_index('ix_analytics_tracking_events_event_time', 'analytics_tracking_events', ['event_time'])
    op.create_index('ix_analytics_tracking_events_event_type', 'analytics_tracking_events', ['event_type'])
    op.create_index('ix_analytics_tracking_events_username', 'analytics_tracking_events', ['username'])
    op.create_index('ix_analytics_tracking_events_course_id', 'analytics_tracking_events', ['course_id'])
    op.create_index('ix_analytics_tracking_events_session_id', 'analytics_tracking_events', ['session_id'])
    op.create_index('ix_analytics_tracking_events_video_id', 'analytics_tracking_events', ['video_id'])
    op.create_index('ix_analytics_events_course_user_time', 'analytics_tracking_events', ['course_id', 'username', 'event_time'])
    op.create_index('ix_analytics_events_course_video_time', 'analytics_tracking_events', ['course_id', 'video_id', 'event_time'])
    op.create_index('ix_analytics_events_type_time', 'analytics_tracking_events', ['event_type', 'event_time'])

    op.create_table(
        'analytics_course_sessions',
        sa.Column('id', sa.String(), primary_key=True),
        sa.Column('course_id', sa.String(length=255), nullable=False),
        sa.Column('session_key', sa.String(length=512), nullable=False),
        sa.Column('session_index', sa.Integer(), nullable=False),
        sa.Column('session_title', sa.String(length=512), nullable=False, server_default=''),
        sa.Column('week_index', sa.Integer(), nullable=True),
        sa.Column('deadline_at', sa.DateTime(), nullable=True),
        sa.Column('deadline_source', sa.String(length=50), nullable=False, server_default='INFERRED'),
        sa.Column('deadline_mapping_quality', sa.String(length=50), nullable=False, server_default='PARTIAL'),
        sa.Column('total_parts', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('total_videos', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('quiz_usage_key', sa.String(length=512), nullable=True),
        sa.Column('components_json', sa.JSON(), nullable=True),
        sa.Column('source', sa.String(length=80), nullable=False, server_default='manual_or_sync'),
        sa.Column('active', sa.Boolean(), nullable=False, server_default=sa.text('true')),
        sa.Column('rebuilt_at', sa.DateTime(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.UniqueConstraint('course_id', 'session_index', name='uq_analytics_course_session_index'),
        sa.UniqueConstraint('course_id', 'session_key', name='uq_analytics_course_session_key'),
    )
    op.create_index('ix_analytics_course_sessions_course_id', 'analytics_course_sessions', ['course_id'])
    op.create_index('ix_analytics_course_sessions_session_key', 'analytics_course_sessions', ['session_key'])
    op.create_index('ix_analytics_course_sessions_week_index', 'analytics_course_sessions', ['week_index'])
    op.create_index('ix_analytics_course_sessions_deadline_at', 'analytics_course_sessions', ['deadline_at'])
    op.create_index('ix_analytics_course_sessions_course_week', 'analytics_course_sessions', ['course_id', 'week_index'])

    op.create_table(
        'analytics_student_video_progress',
        sa.Column('id', sa.String(), primary_key=True),
        sa.Column('course_id', sa.String(length=255), nullable=False),
        sa.Column('username', sa.String(length=255), nullable=False),
        sa.Column('user_id', sa.String(length=64), nullable=True),
        sa.Column('session_key', sa.String(length=512), nullable=True),
        sa.Column('session_index', sa.Integer(), nullable=True),
        sa.Column('video_id', sa.String(length=512), nullable=False),
        sa.Column('video_code', sa.String(length=512), nullable=True),
        sa.Column('component_title', sa.String(length=512), nullable=False, server_default=''),
        sa.Column('duration_seconds', sa.Float(), nullable=True),
        sa.Column('max_position_seconds', sa.Float(), nullable=True),
        sa.Column('completion_percent', sa.Float(), nullable=True),
        sa.Column('estimated_watch_seconds', sa.Float(), nullable=False, server_default='0'),
        sa.Column('estimated_watch_percent', sa.Float(), nullable=True),
        sa.Column('play_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('pause_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('stop_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('seek_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('is_completed', sa.Boolean(), nullable=False, server_default=sa.text('false')),
        sa.Column('is_suspicious', sa.Boolean(), nullable=False, server_default=sa.text('false')),
        sa.Column('suspicious_reason', sa.Text(), nullable=False, server_default=''),
        sa.Column('evidence_json', sa.JSON(), nullable=True),
        sa.Column('first_played_at', sa.DateTime(), nullable=True),
        sa.Column('last_event_at', sa.DateTime(), nullable=True),
        sa.Column('calculated_at', sa.DateTime(), nullable=False),
        sa.UniqueConstraint('course_id', 'username', 'video_id', name='uq_analytics_student_video'),
    )
    op.create_index('ix_analytics_student_video_progress_course_id', 'analytics_student_video_progress', ['course_id'])
    op.create_index('ix_analytics_student_video_progress_username', 'analytics_student_video_progress', ['username'])
    op.create_index('ix_analytics_student_video_progress_video_id', 'analytics_student_video_progress', ['video_id'])
    op.create_index('ix_analytics_student_video_progress_is_completed', 'analytics_student_video_progress', ['is_completed'])
    op.create_index('ix_analytics_student_video_progress_is_suspicious', 'analytics_student_video_progress', ['is_suspicious'])
    op.create_index('ix_analytics_video_progress_course_user_session', 'analytics_student_video_progress', ['course_id', 'username', 'session_index'])

    op.create_table(
        'analytics_student_session_progress',
        sa.Column('id', sa.String(), primary_key=True),
        sa.Column('course_id', sa.String(length=255), nullable=False),
        sa.Column('username', sa.String(length=255), nullable=False),
        sa.Column('user_id', sa.String(length=64), nullable=True),
        sa.Column('session_key', sa.String(length=512), nullable=False),
        sa.Column('session_index', sa.Integer(), nullable=False),
        sa.Column('session_title', sa.String(length=512), nullable=False, server_default=''),
        sa.Column('week_index', sa.Integer(), nullable=True),
        sa.Column('deadline_at', sa.DateTime(), nullable=True),
        sa.Column('deadline_source', sa.String(length=50), nullable=False, server_default='INFERRED'),
        sa.Column('total_videos', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('videos_seen', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('videos_completed', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('avg_video_completion_percent', sa.Float(), nullable=True),
        sa.Column('estimated_watch_seconds', sa.Float(), nullable=False, server_default='0'),
        sa.Column('quiz_attempted', sa.Boolean(), nullable=False, server_default=sa.text('false')),
        sa.Column('quiz_completed', sa.Boolean(), nullable=False, server_default=sa.text('false')),
        sa.Column('quiz_score', sa.Float(), nullable=True),
        sa.Column('started_at', sa.DateTime(), nullable=True),
        sa.Column('last_activity_at', sa.DateTime(), nullable=True),
        sa.Column('completed_before_deadline', sa.Boolean(), nullable=True),
        sa.Column('completed_late', sa.Boolean(), nullable=True),
        sa.Column('session_learning_status', sa.String(length=50), nullable=False, server_default='INSUFFICIENT_DATA'),
        sa.Column('reason_codes', sa.JSON(), nullable=True),
        sa.Column('evidence_json', sa.JSON(), nullable=True),
        sa.Column('calculated_at', sa.DateTime(), nullable=False),
        sa.UniqueConstraint('course_id', 'username', 'session_index', name='uq_analytics_student_session'),
    )
    op.create_index('ix_analytics_session_progress_course_user_week', 'analytics_student_session_progress', ['course_id', 'username', 'week_index'])
    op.create_index('ix_analytics_student_session_progress_course_id', 'analytics_student_session_progress', ['course_id'])
    op.create_index('ix_analytics_student_session_progress_username', 'analytics_student_session_progress', ['username'])
    op.create_index('ix_analytics_student_session_progress_session_learning_status', 'analytics_student_session_progress', ['session_learning_status'])

    op.create_table(
        'analytics_learning_behavior_snapshots',
        sa.Column('id', sa.String(), primary_key=True),
        sa.Column('class_id', sa.String(), nullable=True),
        sa.Column('course_id', sa.String(length=255), nullable=False),
        sa.Column('username', sa.String(length=255), nullable=False),
        sa.Column('user_id', sa.String(length=64), nullable=True),
        sa.Column('classification', sa.String(length=50), nullable=False, server_default='INSUFFICIENT_DATA'),
        sa.Column('display_label', sa.String(length=255), nullable=False, server_default='Chưa đủ dữ liệu'),
        sa.Column('confidence_score', sa.Float(), nullable=False, server_default='0'),
        sa.Column('real_learning_score', sa.Float(), nullable=False, server_default='0'),
        sa.Column('idle_score', sa.Float(), nullable=False, server_default='0'),
        sa.Column('suspicious_score', sa.Float(), nullable=False, server_default='0'),
        sa.Column('deadline_compliance_percent', sa.Float(), nullable=True),
        sa.Column('crammed_session_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('quiz_before_video_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('reason_codes', sa.JSON(), nullable=True),
        sa.Column('human_readable_summary', sa.Text(), nullable=False, server_default=''),
        sa.Column('recommended_action', sa.String(length=80), nullable=False, server_default='INSUFFICIENT_DATA_RECHECK_LATER'),
        sa.Column('data_quality', sa.String(length=50), nullable=False, server_default='MISSING'),
        sa.Column('evidence_json', sa.JSON(), nullable=True),
        sa.Column('last_activity_at', sa.DateTime(), nullable=True),
        sa.Column('calculated_at', sa.DateTime(), nullable=False),
        sa.UniqueConstraint('class_id', 'course_id', 'username', name='uq_analytics_behavior_class_course_user'),
    )
    op.create_index('ix_analytics_learning_behavior_snapshots_class_id', 'analytics_learning_behavior_snapshots', ['class_id'])
    op.create_index('ix_analytics_learning_behavior_snapshots_course_id', 'analytics_learning_behavior_snapshots', ['course_id'])
    op.create_index('ix_analytics_learning_behavior_snapshots_username', 'analytics_learning_behavior_snapshots', ['username'])
    op.create_index('ix_analytics_learning_behavior_snapshots_classification', 'analytics_learning_behavior_snapshots', ['classification'])
    op.create_index('ix_analytics_learning_behavior_snapshots_data_quality', 'analytics_learning_behavior_snapshots', ['data_quality'])
    op.create_index('ix_analytics_behavior_class_classification', 'analytics_learning_behavior_snapshots', ['class_id', 'classification'])
    op.create_index('ix_analytics_behavior_course_classification', 'analytics_learning_behavior_snapshots', ['course_id', 'classification'])


def downgrade() -> None:
    op.drop_table('analytics_learning_behavior_snapshots')
    op.drop_table('analytics_student_session_progress')
    op.drop_table('analytics_student_video_progress')
    op.drop_table('analytics_course_sessions')
    op.drop_table('analytics_tracking_events')
    op.drop_table('analytics_ingest_checkpoints')
