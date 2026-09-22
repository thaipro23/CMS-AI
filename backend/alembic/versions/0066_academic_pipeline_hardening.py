"""Add durable scheduled-parent identity and immutable report snapshots.

Revision ID: 0066_academic_pipeline_hardening
Revises: 0065_academic_job_batch_recovery
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision = '0066_academic_pipeline_hardening'
down_revision = '0065_academic_job_batch_recovery'
branch_labels = None
depends_on = None


BULK_TABLE = 'academic_bulk_operation_jobs'
SNAPSHOT_TABLE = 'academic_teacher_report_snapshots'


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    tables = set(inspector.get_table_names())

    if BULK_TABLE in tables:
        columns = {
            column['name']
            for column in inspector.get_columns(BULK_TABLE)
        }
        if 'idempotency_key' not in columns:
            op.add_column(
                BULK_TABLE,
                sa.Column('idempotency_key', sa.String(length=255), nullable=True),
            )
        indexes = {
            index['name']
            for index in inspect(bind).get_indexes(BULK_TABLE)
        }
        if 'ix_academic_bulk_operation_jobs_idempotency_key' not in indexes:
            op.create_index(
                'ix_academic_bulk_operation_jobs_idempotency_key',
                BULK_TABLE,
                ['idempotency_key'],
                unique=True,
            )

    if SNAPSHOT_TABLE not in tables:
        op.create_table(
            SNAPSHOT_TABLE,
            sa.Column('id', sa.String(), nullable=False),
            sa.Column('parent_job_id', sa.String(), nullable=False),
            sa.Column('term_id', sa.String(), nullable=False),
            sa.Column('branch', sa.String(length=64), nullable=False),
            sa.Column('scope_type', sa.String(length=32), nullable=False),
            sa.Column('campus', sa.String(length=64), nullable=True),
            sa.Column('policy_version', sa.String(length=128), nullable=False),
            sa.Column('storage_key', sa.String(length=1024), nullable=False),
            sa.Column('sha256', sa.String(length=64), nullable=False),
            sa.Column('size_bytes', sa.Integer(), nullable=False, server_default='0'),
            sa.Column('counts_json', sa.JSON(), nullable=True),
            sa.Column('metadata_json', sa.JSON(), nullable=True),
            sa.Column('created_at', sa.DateTime(), nullable=False),
            sa.Column('updated_at', sa.DateTime(), nullable=False),
            sa.ForeignKeyConstraint(
                ['parent_job_id'],
                ['academic_bulk_operation_jobs.id'],
            ),
            sa.ForeignKeyConstraint(['term_id'], ['academic_terms.id']),
            sa.PrimaryKeyConstraint('id'),
        )
        op.create_index(
            'ix_academic_teacher_report_snapshots_parent_job_id',
            SNAPSHOT_TABLE,
            ['parent_job_id'],
        )
        op.create_index(
            'ix_academic_teacher_report_snapshots_term_id',
            SNAPSHOT_TABLE,
            ['term_id'],
        )
        op.create_index(
            'ix_academic_teacher_report_snapshots_branch',
            SNAPSHOT_TABLE,
            ['branch'],
        )
        op.create_index(
            'ix_academic_teacher_report_snapshots_scope_type',
            SNAPSHOT_TABLE,
            ['scope_type'],
        )
        op.create_index(
            'ix_academic_teacher_report_snapshots_campus',
            SNAPSHOT_TABLE,
            ['campus'],
        )
        op.create_index(
            'ix_academic_teacher_report_snapshots_sha256',
            SNAPSHOT_TABLE,
            ['sha256'],
        )
        op.create_index(
            'ix_academic_teacher_report_snapshots_created_at',
            SNAPSHOT_TABLE,
            ['created_at'],
        )
        op.create_index(
            'ix_academic_teacher_report_snapshot_scope',
            SNAPSHOT_TABLE,
            ['term_id', 'branch', 'scope_type', 'campus'],
        )
        op.create_index(
            'uq_academic_teacher_report_snapshot_parent_scope_campus',
            SNAPSHOT_TABLE,
            [
                'parent_job_id',
                'scope_type',
                sa.text("COALESCE(campus, '')"),
            ],
            unique=True,
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    tables = set(inspector.get_table_names())
    if SNAPSHOT_TABLE in tables:
        op.drop_table(SNAPSHOT_TABLE)
    if BULK_TABLE not in tables:
        return
    indexes = {
        index['name']
        for index in inspect(bind).get_indexes(BULK_TABLE)
    }
    if 'ix_academic_bulk_operation_jobs_idempotency_key' in indexes:
        op.drop_index(
            'ix_academic_bulk_operation_jobs_idempotency_key',
            table_name=BULK_TABLE,
        )
    columns = {
        column['name']
        for column in inspect(bind).get_columns(BULK_TABLE)
    }
    if 'idempotency_key' in columns:
        op.drop_column(BULK_TABLE, 'idempotency_key')
