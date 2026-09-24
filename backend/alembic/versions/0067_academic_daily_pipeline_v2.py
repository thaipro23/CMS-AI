"""Add durable attempt identity for the unified academic daily pipeline.

Revision ID: 0067_academic_daily_pipeline_v2
Revises: 0066_academic_pipeline_hardening
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision = '0067_academic_daily_pipeline_v2'
down_revision = '0066_academic_pipeline_hardening'
branch_labels = None
depends_on = None


BULK_TABLE = 'academic_bulk_operation_jobs'
SYNC_RUN_TABLE = 'academic_sync_runs'
REPORT_JOB_TABLE = 'academic_teacher_report_jobs'


def _add_column_if_missing(table: str, column: sa.Column) -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    if table not in inspector.get_table_names():
        return
    columns = {item['name'] for item in inspector.get_columns(table)}
    if column.name not in columns:
        op.add_column(table, column)


def _add_index_if_missing(
    table: str,
    name: str,
    columns: list[str],
    *,
    unique: bool = False,
) -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    if table not in inspector.get_table_names():
        return
    indexes = {item['name'] for item in inspector.get_indexes(table)}
    if name not in indexes:
        op.create_index(name, table, columns, unique=unique)


def upgrade() -> None:
    _add_column_if_missing(
        BULK_TABLE,
        sa.Column('parent_job_id', sa.String(), nullable=True),
    )
    _add_index_if_missing(
        BULK_TABLE,
        'ix_academic_bulk_operation_jobs_parent_job_id',
        ['parent_job_id'],
    )

    _add_column_if_missing(
        SYNC_RUN_TABLE,
        sa.Column('idempotency_key', sa.String(length=255), nullable=True),
    )
    _add_index_if_missing(
        SYNC_RUN_TABLE,
        'ix_academic_sync_runs_idempotency_key',
        ['idempotency_key'],
        unique=True,
    )

    _add_column_if_missing(
        REPORT_JOB_TABLE,
        sa.Column('parent_job_id', sa.String(), nullable=True),
    )
    _add_column_if_missing(
        REPORT_JOB_TABLE,
        sa.Column('idempotency_key', sa.String(length=255), nullable=True),
    )
    _add_index_if_missing(
        REPORT_JOB_TABLE,
        'ix_academic_teacher_report_jobs_parent_job_id',
        ['parent_job_id'],
    )
    _add_index_if_missing(
        REPORT_JOB_TABLE,
        'ix_academic_teacher_report_jobs_idempotency_key',
        ['idempotency_key'],
        unique=True,
    )


def _drop_attempt_columns(table: str, columns: tuple[tuple[str, str], ...]) -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    if table not in inspector.get_table_names():
        return
    indexes = {item['name'] for item in inspector.get_indexes(table)}
    for column_name, index_name in columns:
        if index_name in indexes:
            op.drop_index(index_name, table_name=table)
    existing_columns = {item['name'] for item in inspect(bind).get_columns(table)}
    for column_name, _index_name in columns:
        if column_name in existing_columns:
            op.drop_column(table, column_name)


def downgrade() -> None:
    _drop_attempt_columns(
        REPORT_JOB_TABLE,
        (
            ('idempotency_key', 'ix_academic_teacher_report_jobs_idempotency_key'),
            ('parent_job_id', 'ix_academic_teacher_report_jobs_parent_job_id'),
        ),
    )
    _drop_attempt_columns(
        SYNC_RUN_TABLE,
        (('idempotency_key', 'ix_academic_sync_runs_idempotency_key'),),
    )
    _drop_attempt_columns(
        BULK_TABLE,
        (('parent_job_id', 'ix_academic_bulk_operation_jobs_parent_job_id'),),
    )
