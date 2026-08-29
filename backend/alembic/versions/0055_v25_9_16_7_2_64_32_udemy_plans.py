"""Add versioned Udemy subject plans and milestones.

Revision ID: 0055_v25_9_16_7_2_64_32
Revises: 0054_v25_9_16_7_2_64_31
"""
from alembic import op
import sqlalchemy as sa

revision = '0055_v25_9_16_7_2_64_32'
down_revision = '0054_v25_9_16_7_2_64_31'
branch_labels = None
depends_on = None


def upgrade() -> None:
    if sa.inspect(op.get_bind()).has_table('udemy_subject_plans'):
        return
    op.create_table(
        'udemy_subject_plans',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('subject_delivery_id', sa.String(), nullable=False),
        sa.Column('version', sa.Integer(), nullable=False, server_default='1'),
        sa.Column('item_count', sa.Integer(), nullable=False),
        sa.Column('active', sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column('source', sa.String(length=50), nullable=False, server_default='manual'),
        sa.Column('source_file_name', sa.String(length=255), nullable=True),
        sa.Column('source_file_hash', sa.String(length=64), nullable=True),
        sa.Column('imported_by', sa.String(length=255), nullable=True),
        sa.Column('imported_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('note', sa.Text(), nullable=True),
        sa.Column('metadata_json', sa.JSON(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.ForeignKeyConstraint(['subject_delivery_id'], ['academic_subject_deliveries.id']),
        sa.CheckConstraint('version >= 1', name='ck_udemy_subject_plan_version'),
        sa.CheckConstraint('item_count > 0', name='ck_udemy_subject_plan_item_count'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('subject_delivery_id', 'version', name='uq_udemy_subject_plan_delivery_version'),
    )
    op.create_index('ix_udemy_subject_plans_subject_delivery_id', 'udemy_subject_plans', ['subject_delivery_id'])
    op.create_index('ix_udemy_subject_plans_active', 'udemy_subject_plans', ['active'])
    op.create_index('ix_udemy_subject_plans_source', 'udemy_subject_plans', ['source'])
    op.create_index('ix_udemy_subject_plans_source_file_hash', 'udemy_subject_plans', ['source_file_hash'])
    op.create_index('ix_udemy_subject_plans_imported_by', 'udemy_subject_plans', ['imported_by'])
    op.create_index('ix_udemy_subject_plans_imported_at', 'udemy_subject_plans', ['imported_at'])
    op.create_index('ix_udemy_subject_plan_delivery_active', 'udemy_subject_plans', ['subject_delivery_id', 'active'])
    op.create_index('ix_udemy_subject_plan_delivery_imported', 'udemy_subject_plans', ['subject_delivery_id', 'imported_at'])

    op.create_table(
        'udemy_subject_plan_milestones',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('plan_id', sa.String(), nullable=False),
        sa.Column('week_number', sa.Integer(), nullable=False),
        sa.Column('deadline_date', sa.Date(), nullable=False),
        sa.Column('required_progress_percent', sa.Float(), nullable=False),
        sa.Column('sort_order', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('metadata_json', sa.JSON(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.ForeignKeyConstraint(['plan_id'], ['udemy_subject_plans.id'], ondelete='CASCADE'),
        sa.CheckConstraint('week_number >= 1 AND week_number <= 52', name='ck_udemy_plan_milestone_week'),
        sa.CheckConstraint('required_progress_percent >= 0 AND required_progress_percent <= 100', name='ck_udemy_plan_milestone_progress'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('plan_id', 'week_number', name='uq_udemy_plan_milestone_week'),
    )
    op.create_index('ix_udemy_subject_plan_milestones_plan_id', 'udemy_subject_plan_milestones', ['plan_id'])
    op.create_index('ix_udemy_subject_plan_milestones_deadline_date', 'udemy_subject_plan_milestones', ['deadline_date'])
    op.create_index('ix_udemy_plan_milestone_plan_order', 'udemy_subject_plan_milestones', ['plan_id', 'sort_order'])


def downgrade() -> None:
    op.execute('DROP TABLE IF EXISTS udemy_subject_plan_milestones CASCADE')
    op.execute('DROP TABLE IF EXISTS udemy_subject_plans CASCADE')
