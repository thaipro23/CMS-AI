"""Add indexes for analytics identity lookup and retention scanning.

Revision ID: 0069_analytics_tracking_query_indexes
Revises: 0068_analytics_loki_ingest
"""

from __future__ import annotations

from alembic import op
from sqlalchemy import inspect


revision = '0069_analytics_tracking_query_indexes'
down_revision = '0068_analytics_loki_ingest'
branch_labels = None
depends_on = None


EVENT_TABLE = 'analytics_tracking_events'
COURSE_USER_ID_TIME_INDEX = 'ix_analytics_events_course_user_id_time'
CREATED_ID_INDEX = 'ix_analytics_tracking_events_created_id'


def _index_names(table_name: str) -> set[str]:
    bind = op.get_bind()
    inspector = inspect(bind)
    if table_name not in inspector.get_table_names():
        return set()
    return {
        str(item.get('name'))
        for item in inspector.get_indexes(table_name)
        if item.get('name')
    }


def _create_indexes(*, concurrent: bool) -> None:
    existing = _index_names(EVENT_TABLE)
    if COURSE_USER_ID_TIME_INDEX not in existing:
        op.create_index(
            COURSE_USER_ID_TIME_INDEX,
            EVENT_TABLE,
            ['course_id', 'user_id', 'event_time'],
            unique=False,
            postgresql_concurrently=concurrent,
        )
    if CREATED_ID_INDEX not in existing:
        op.create_index(
            CREATED_ID_INDEX,
            EVENT_TABLE,
            ['created_at', 'id'],
            unique=False,
            postgresql_concurrently=concurrent,
        )


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == 'postgresql':
        with op.get_context().autocommit_block():
            _create_indexes(concurrent=True)
    else:
        _create_indexes(concurrent=False)


def _drop_indexes(*, concurrent: bool) -> None:
    existing = _index_names(EVENT_TABLE)
    for index_name in (CREATED_ID_INDEX, COURSE_USER_ID_TIME_INDEX):
        if index_name in existing:
            op.drop_index(
                index_name,
                table_name=EVENT_TABLE,
                postgresql_concurrently=concurrent,
            )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == 'postgresql':
        with op.get_context().autocommit_block():
            _drop_indexes(concurrent=True)
    else:
        _drop_indexes(concurrent=False)
