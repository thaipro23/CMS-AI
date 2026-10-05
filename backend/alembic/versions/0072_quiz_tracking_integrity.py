"""Durable quiz item evidence and class-scoped integrity results."""
from alembic import op
import sqlalchemy as sa

revision = '0072_quiz_tracking_integrity'
down_revision = '0071_analytics_hotpath_identity_indexes'
branch_labels = None
depends_on = None


def upgrade():
    # Freeze schema here: future model changes must not rewrite this migration.
    op.create_table(
        'analytics_quiz_item_submissions',
        sa.Column('id', sa.String(), primary_key=True),
        sa.Column('event_fingerprint', sa.String(64), nullable=False),
        sa.Column('attempt_id', sa.String(), nullable=False),
        sa.Column('course_id', sa.String(255), nullable=False),
        sa.Column('username', sa.String(255), nullable=False),
        sa.Column('unit_usage_key', sa.String(512), nullable=False),
        sa.Column('problem_usage_key', sa.String(512), nullable=False),
        sa.Column('input_id', sa.String(512), nullable=False),
        sa.Column('input_slot', sa.String(128), nullable=False),
        sa.Column('variant', sa.String(128), nullable=False),
        sa.Column('content_version', sa.String(255), nullable=True),
        sa.Column('question_hash', sa.String(64), nullable=False),
        sa.Column('answer_json', sa.JSON(), nullable=True),
        sa.Column('correct', sa.Boolean(), nullable=True),
        sa.Column('response_type', sa.String(80), nullable=False),
        sa.Column('attempt_index', sa.Integer(), nullable=True),
        sa.Column('submitted_at', sa.DateTime(), nullable=False),
        sa.Column('reveal_requested_before', sa.Boolean(), nullable=False),
        sa.UniqueConstraint('event_fingerprint', 'input_id', name='uq_quiz_item_event_input'),
    )
    op.create_index('ix_analytics_quiz_item_submissions_attempt_id', 'analytics_quiz_item_submissions', ['attempt_id'])
    op.create_index('ix_quiz_items_course_user_unit_time', 'analytics_quiz_item_submissions',
                    ['course_id', 'username', 'unit_usage_key', 'submitted_at'])
    op.create_table(
        'analytics_quiz_item_receipts',
        sa.Column('event_id', sa.String(), primary_key=True),
        sa.Column('materialized_at', sa.DateTime(), nullable=False),
    )
    op.create_table(
        'analytics_quiz_integrity_results',
        sa.Column('id', sa.String(), primary_key=True),
        sa.Column('class_id', sa.String(), nullable=False),
        sa.Column('course_id', sa.String(255), nullable=False),
        sa.Column('username', sa.String(255), nullable=False),
        sa.Column('unit_usage_key', sa.String(512), nullable=False),
        sa.Column('status', sa.String(50), nullable=False),
        sa.Column('rule_version', sa.String(80), nullable=False),
        sa.Column('evidence_json', sa.JSON(), nullable=False),
        sa.Column('calculated_at', sa.DateTime(), nullable=False),
        sa.UniqueConstraint('class_id', 'course_id', 'username', 'unit_usage_key',
                            name='uq_quiz_integrity_class_user_unit'),
    )
    op.create_index('ix_quiz_integrity_class_course_user', 'analytics_quiz_integrity_results',
                    ['class_id', 'course_id', 'username'])


def downgrade():
    op.drop_table('analytics_quiz_integrity_results')
    op.drop_table('analytics_quiz_item_receipts')
    op.drop_table('analytics_quiz_item_submissions')
