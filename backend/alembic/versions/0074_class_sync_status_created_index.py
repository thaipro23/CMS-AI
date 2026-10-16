"""Global job-status feed index, created without blocking production writers.

Revision ID: 0074_class_sync_status_created_index
Revises: 0073_assessment_average_grade
"""
from __future__ import annotations

from alembic import op
from sqlalchemy import inspect, text

revision = '0074_class_sync_status_created_index'
down_revision = '0073_assessment_average_grade'
branch_labels = None
depends_on = None

TABLE = 'academic_class_sync_jobs'
INDEX = 'ix_academic_class_sync_jobs_status_created'


def _exists(bind) -> bool:
    return INDEX in {item['name'] for item in inspect(bind).get_indexes(TABLE)}


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != 'postgresql':
        if not _exists(bind):
            op.create_index(INDEX, TABLE, ['status', 'created_at'])
        return

    # CREATE INDEX CONCURRENTLY requires an autocommit block. Raise the
    # statement timeout on this migration connection only; avoid long locks.
    with op.get_context().autocommit_block():
        bind = op.get_bind()
        original_statement = bind.exec_driver_sql('SHOW statement_timeout').scalar()
        original_lock = bind.exec_driver_sql('SHOW lock_timeout').scalar()
        try:
            bind.execute(text("SELECT set_config('statement_timeout', '120s', false)"))
            bind.execute(text("SELECT set_config('lock_timeout', '5s', false)"))
            valid = bind.execute(text("""
                SELECT i.indisvalid
                FROM pg_index i JOIN pg_class c ON c.oid = i.indexrelid
                WHERE c.relname = :name
                  AND i.indrelid = to_regclass(:table)
            """), {'name': INDEX, 'table': TABLE}).scalar()
            # An interrupted concurrent build can leave an INVALID index.
            if valid is False:
                op.drop_index(INDEX, table_name=TABLE, postgresql_concurrently=True)
            if valid is not True:
                op.create_index(INDEX, TABLE, ['status', 'created_at'],
                                postgresql_concurrently=True)
        finally:
            bind.execute(text("SELECT set_config('statement_timeout', :v, false)"),
                         {'v': original_statement})
            bind.execute(text("SELECT set_config('lock_timeout', :v, false)"),
                         {'v': original_lock})


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != 'postgresql':
        if _exists(bind):
            op.drop_index(INDEX, table_name=TABLE)
        return
    with op.get_context().autocommit_block():
        if _exists(op.get_bind()):
            op.drop_index(INDEX, table_name=TABLE, postgresql_concurrently=True)
