"""v25.9.16.7.2.21 bulk academic jobs

Revision ID: 0051_v25_9_16_7_2_21
Revises: 0050_v25_9_16_7_2_12
Create Date: 2026-07-02 09:10:00
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = '0051_v25_9_16_7_2_21'
down_revision = '0050_v25_9_16_7_2_12'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'academic_bulk_operation_jobs',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('job_type', sa.String(length=80), nullable=False),
        sa.Column('status', sa.String(length=50), nullable=False, server_default='queued'),
        sa.Column('term_id', sa.String(), nullable=True),
        sa.Column('branch', sa.String(length=64), nullable=True),
        sa.Column('campus', sa.String(length=64), nullable=True),
        sa.Column('requested_by', sa.String(length=255), nullable=True),
        sa.Column('progress_current', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('progress_total', sa.Integer(), nullable=False, server_default='100'),
        sa.Column('progress_label', sa.String(length=255), nullable=False, server_default='Đang chờ xử lý'),
        sa.Column('request_json', sa.JSON(), nullable=True),
        sa.Column('result_json', sa.JSON(), nullable=True),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('started_at', sa.DateTime(), nullable=True),
        sa.Column('finished_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.ForeignKeyConstraint(['term_id'], ['academic_terms.id'], name='fk_academic_bulk_operation_term'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_academic_bulk_operation_jobs_job_type', 'academic_bulk_operation_jobs', ['job_type'])
    op.create_index('ix_academic_bulk_operation_jobs_status', 'academic_bulk_operation_jobs', ['status'])
    op.create_index('ix_academic_bulk_operation_jobs_term_id', 'academic_bulk_operation_jobs', ['term_id'])
    op.create_index('ix_academic_bulk_operation_jobs_branch', 'academic_bulk_operation_jobs', ['branch'])
    op.create_index('ix_academic_bulk_operation_jobs_campus', 'academic_bulk_operation_jobs', ['campus'])
    op.create_index('ix_academic_bulk_operation_jobs_requested_by', 'academic_bulk_operation_jobs', ['requested_by'])
    op.create_index('ix_academic_bulk_operation_jobs_created_at', 'academic_bulk_operation_jobs', ['created_at'])
    op.create_index('ix_academic_bulk_operation_scope_status', 'academic_bulk_operation_jobs', ['job_type', 'term_id', 'branch', 'campus', 'status'])
    op.create_index('ix_academic_bulk_operation_actor_created', 'academic_bulk_operation_jobs', ['requested_by', 'created_at'])
    op.create_index('ix_academic_bulk_operation_type_created', 'academic_bulk_operation_jobs', ['job_type', 'created_at'])


def downgrade() -> None:
    op.drop_index('ix_academic_bulk_operation_type_created', table_name='academic_bulk_operation_jobs')
    op.drop_index('ix_academic_bulk_operation_actor_created', table_name='academic_bulk_operation_jobs')
    op.drop_index('ix_academic_bulk_operation_scope_status', table_name='academic_bulk_operation_jobs')
    op.drop_index('ix_academic_bulk_operation_jobs_created_at', table_name='academic_bulk_operation_jobs')
    op.drop_index('ix_academic_bulk_operation_jobs_requested_by', table_name='academic_bulk_operation_jobs')
    op.drop_index('ix_academic_bulk_operation_jobs_campus', table_name='academic_bulk_operation_jobs')
    op.drop_index('ix_academic_bulk_operation_jobs_branch', table_name='academic_bulk_operation_jobs')
    op.drop_index('ix_academic_bulk_operation_jobs_term_id', table_name='academic_bulk_operation_jobs')
    op.drop_index('ix_academic_bulk_operation_jobs_status', table_name='academic_bulk_operation_jobs')
    op.drop_index('ix_academic_bulk_operation_jobs_job_type', table_name='academic_bulk_operation_jobs')
    op.drop_table('academic_bulk_operation_jobs')
