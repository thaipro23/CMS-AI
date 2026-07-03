"""v25.9.16.7.2.27 learning behavior logic calibration

Revision ID: 0052_v25_9_16_7_2_27
Revises: 0051_v25_9_16_7_2_21
Create Date: 2026-07-02
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = '0052_v25_9_16_7_2_27'
down_revision = '0051_v25_9_16_7_2_21'
branch_labels = None
depends_on = None


def _add_column_if_missing(table: str, column: sa.Column) -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing = {c['name'] for c in inspector.get_columns(table)}
    if column.name not in existing:
        op.add_column(table, column)


def upgrade() -> None:
    _add_column_if_missing('analytics_course_sessions', sa.Column('session_type', sa.String(length=50), nullable=False, server_default='LEARNING_SESSION'))
    _add_column_if_missing('analytics_student_video_progress', sa.Column('consistency_percent', sa.Float(), nullable=True))
    _add_column_if_missing('analytics_student_video_progress', sa.Column('video_quality_percent', sa.Float(), nullable=True))
    _add_column_if_missing('analytics_student_video_progress', sa.Column('long_passive_segment_count', sa.Integer(), nullable=False, server_default='0'))
    _add_column_if_missing('analytics_student_video_progress', sa.Column('long_passive_seconds', sa.Float(), nullable=False, server_default='0'))
    _add_column_if_missing('analytics_student_video_progress', sa.Column('passive_watch_seconds', sa.Float(), nullable=False, server_default='0'))
    _add_column_if_missing('analytics_student_session_progress', sa.Column('session_type', sa.String(length=50), nullable=False, server_default='LEARNING_SESSION'))
    _add_column_if_missing('analytics_student_session_progress', sa.Column('avg_video_quality_percent', sa.Float(), nullable=True))
    _add_column_if_missing('analytics_student_session_progress', sa.Column('passive_watch_seconds', sa.Float(), nullable=False, server_default='0'))
    _add_column_if_missing('analytics_student_session_progress', sa.Column('long_passive_video_count', sa.Integer(), nullable=False, server_default='0'))

    op.create_table(
        'analytics_quiz_attempts',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('course_id', sa.String(length=255), nullable=False),
        sa.Column('username', sa.String(length=255), nullable=False),
        sa.Column('user_id', sa.String(length=64), nullable=True),
        sa.Column('sequence_usage_key', sa.String(length=512), nullable=True),
        sa.Column('unit_usage_key', sa.String(length=512), nullable=False),
        sa.Column('attempt_no', sa.Integer(), nullable=False, server_default='1'),
        sa.Column('unit_reset_nonce', sa.String(length=255), nullable=True),
        sa.Column('started_at', sa.DateTime(), nullable=True),
        sa.Column('ended_at', sa.DateTime(), nullable=True),
        sa.Column('reset_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('submission_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('assigned_problem_usage_keys_json', sa.JSON(), nullable=True),
        sa.Column('itembank_locations_json', sa.JSON(), nullable=True),
        sa.Column('score_earned', sa.Float(), nullable=True),
        sa.Column('score_possible', sa.Float(), nullable=True),
        sa.Column('median_time_per_question_seconds', sa.Float(), nullable=True),
        sa.Column('repeat_rate', sa.Float(), nullable=True),
        sa.Column('suspicious_quiz_speed', sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column('fishing_pattern', sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column('showanswer_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('first_submission_at', sa.DateTime(), nullable=True),
        sa.Column('last_submission_at', sa.DateTime(), nullable=True),
        sa.Column('low_confidence_reason', sa.Text(), nullable=True),
        sa.Column('evidence_json', sa.JSON(), nullable=True),
        sa.Column('calculated_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('course_id', 'username', 'unit_usage_key', 'attempt_no', name='uq_analytics_quiz_attempt_user_unit_no'),
    )
    op.create_index('ix_analytics_quiz_attempt_course_id', 'analytics_quiz_attempts', ['course_id'])
    op.create_index('ix_analytics_quiz_attempt_username', 'analytics_quiz_attempts', ['username'])
    op.create_index('ix_analytics_quiz_attempt_course_user_time', 'analytics_quiz_attempts', ['course_id', 'username', 'started_at'])
    op.create_index('ix_analytics_quiz_attempt_unit_usage_key', 'analytics_quiz_attempts', ['unit_usage_key'])
    op.create_index('ix_analytics_quiz_attempt_suspicious_quiz_speed', 'analytics_quiz_attempts', ['suspicious_quiz_speed'])
    op.create_index('ix_analytics_quiz_attempt_fishing_pattern', 'analytics_quiz_attempts', ['fishing_pattern'])

    op.create_table(
        'analytics_session_overrides',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('course_id', sa.String(length=255), nullable=False),
        sa.Column('block_usage_key', sa.String(length=512), nullable=False),
        sa.Column('forced_session_type', sa.String(length=50), nullable=False, server_default='LEARNING_SESSION'),
        sa.Column('forced_session_name', sa.String(length=512), nullable=True),
        sa.Column('active', sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('course_id', 'block_usage_key', name='uq_analytics_session_override_course_block'),
    )
    op.create_index('ix_analytics_session_overrides_course_id', 'analytics_session_overrides', ['course_id'])
    op.create_index('ix_analytics_session_overrides_block_usage_key', 'analytics_session_overrides', ['block_usage_key'])
    op.create_index('ix_analytics_session_overrides_forced_session_type', 'analytics_session_overrides', ['forced_session_type'])
    op.create_index('ix_analytics_session_overrides_active', 'analytics_session_overrides', ['active'])

    bind = op.get_bind()
    bind.execute(sa.text("UPDATE analytics_learning_behavior_snapshots SET classification='POSSIBLE_ANOMALY' WHERE classification='POSSIBLE_CHEATING'"))


def downgrade() -> None:
    bind = op.get_bind()
    bind.execute(sa.text("UPDATE analytics_learning_behavior_snapshots SET classification='POSSIBLE_CHEATING' WHERE classification='POSSIBLE_ANOMALY'"))
    op.drop_table('analytics_session_overrides')
    op.drop_table('analytics_quiz_attempts')
    for table, cols in {
        'analytics_student_session_progress': ['long_passive_video_count', 'passive_watch_seconds', 'avg_video_quality_percent', 'session_type'],
        'analytics_student_video_progress': ['passive_watch_seconds', 'long_passive_seconds', 'long_passive_segment_count', 'video_quality_percent', 'consistency_percent'],
        'analytics_course_sessions': ['session_type'],
    }.items():
        bind = op.get_bind()
        inspector = sa.inspect(bind)
        existing = {c['name'] for c in inspector.get_columns(table)}
        for col in cols:
            if col in existing:
                op.drop_column(table, col)
