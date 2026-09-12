"""Add durable identity for batched academic class jobs.

Revision ID: 0065_academic_job_batch_recovery
Revises: 0064_rbac_identity_login
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision = '0065_academic_job_batch_recovery'
down_revision = '0064_rbac_identity_login'
branch_labels = None
depends_on = None


TABLE = 'academic_class_sync_jobs'


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    columns = {column['name'] for column in inspector.get_columns(TABLE)}
    if 'parent_job_id' not in columns:
        op.add_column(TABLE, sa.Column('parent_job_id', sa.String(), nullable=True))
    if 'idempotency_key' not in columns:
        op.add_column(TABLE, sa.Column('idempotency_key', sa.String(length=255), nullable=True))

    indexes = {index['name'] for index in inspect(bind).get_indexes(TABLE)}
    if 'ix_academic_class_sync_jobs_parent_job_id' not in indexes:
        op.create_index('ix_academic_class_sync_jobs_parent_job_id', TABLE, ['parent_job_id'])
    if 'ix_academic_class_sync_jobs_idempotency_key' not in indexes:
        op.create_index(
            'ix_academic_class_sync_jobs_idempotency_key',
            TABLE,
            ['idempotency_key'],
            unique=True,
        )


def downgrade() -> None:
    bind = op.get_bind()
    if TABLE not in inspect(bind).get_table_names():
        return
    indexes = {index['name'] for index in inspect(bind).get_indexes(TABLE)}
    if 'ix_academic_class_sync_jobs_idempotency_key' in indexes:
        op.drop_index('ix_academic_class_sync_jobs_idempotency_key', table_name=TABLE)
    if 'ix_academic_class_sync_jobs_parent_job_id' in indexes:
        op.drop_index('ix_academic_class_sync_jobs_parent_job_id', table_name=TABLE)
    columns = {column['name'] for column in inspect(bind).get_columns(TABLE)}
    if 'idempotency_key' in columns:
        op.drop_column(TABLE, 'idempotency_key')
    if 'parent_job_id' in columns:
        op.drop_column(TABLE, 'parent_job_id')

