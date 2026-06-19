"""v25.9.16.4.5 academic async class sync jobs

Revision ID: 0043_v25_9_16_4_5_async_jobs
Revises: 0042_v25_9_16_4_4_hardening
Create Date: 2026-06-19
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = '0043_v25_9_16_4_5_async_jobs'
down_revision = '0042_v25_9_16_4_4_hardening'
branch_labels = None
depends_on = None


def _has_table(table: str) -> bool:
    bind = op.get_bind()
    return table in sa.inspect(bind).get_table_names()


def upgrade() -> None:
    bind = op.get_bind()
    bind.exec_driver_sql(
        'ALTER TABLE IF EXISTS alembic_version ALTER COLUMN version_num TYPE VARCHAR(255)'
    )
    if _has_table('academic_class_sync_jobs'):
        return
    op.create_table(
        'academic_class_sync_jobs',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('job_type', sa.String(length=80), nullable=False),
        sa.Column('status', sa.String(length=50), nullable=False, server_default='queued'),
        sa.Column('class_id', sa.String(), nullable=False),
        sa.Column('requested_by', sa.String(length=255), nullable=True),
        sa.Column('force', sa.Boolean(), nullable=False, server_default=sa.text('false')),
        sa.Column('limit', sa.Integer(), nullable=False, server_default='500'),
        sa.Column('mode', sa.String(length=50), nullable=True),
        sa.Column('progress_current', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('progress_total', sa.Integer(), nullable=False, server_default='100'),
        sa.Column('progress_label', sa.String(length=255), nullable=False, server_default='Đang chờ xử lý'),
        sa.Column('request_json', sa.JSON(), nullable=True),
        sa.Column('result_json', sa.JSON(), nullable=True),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('started_at', sa.DateTime(), nullable=True),
        sa.Column('finished_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['class_id'], ['academic_classes.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_academic_class_sync_jobs_class_status_created', 'academic_class_sync_jobs', ['class_id', 'status', 'created_at'])
    op.create_index('ix_academic_class_sync_jobs_actor_created', 'academic_class_sync_jobs', ['requested_by', 'created_at'])
    op.create_index('ix_academic_class_sync_jobs_type_status_created', 'academic_class_sync_jobs', ['job_type', 'status', 'created_at'])
    op.create_index(op.f('ix_academic_class_sync_jobs_class_id'), 'academic_class_sync_jobs', ['class_id'])
    op.create_index(op.f('ix_academic_class_sync_jobs_job_type'), 'academic_class_sync_jobs', ['job_type'])
    op.create_index(op.f('ix_academic_class_sync_jobs_status'), 'academic_class_sync_jobs', ['status'])
    op.create_index(op.f('ix_academic_class_sync_jobs_requested_by'), 'academic_class_sync_jobs', ['requested_by'])


def downgrade() -> None:
    if not _has_table('academic_class_sync_jobs'):
        return
    op.drop_index(op.f('ix_academic_class_sync_jobs_requested_by'), table_name='academic_class_sync_jobs')
    op.drop_index(op.f('ix_academic_class_sync_jobs_status'), table_name='academic_class_sync_jobs')
    op.drop_index(op.f('ix_academic_class_sync_jobs_job_type'), table_name='academic_class_sync_jobs')
    op.drop_index(op.f('ix_academic_class_sync_jobs_class_id'), table_name='academic_class_sync_jobs')
    op.drop_index('ix_academic_class_sync_jobs_type_status_created', table_name='academic_class_sync_jobs')
    op.drop_index('ix_academic_class_sync_jobs_actor_created', table_name='academic_class_sync_jobs')
    op.drop_index('ix_academic_class_sync_jobs_class_status_created', table_name='academic_class_sync_jobs')
    op.drop_table('academic_class_sync_jobs')
