"""Add hot-path indexes for bounded analytics identity queries.

Revision ID: 0071_analytics_hotpath_identity_indexes
Revises: 0070_analytics_materialized_event_receipts
"""

from __future__ import annotations

from alembic import op
from sqlalchemy import inspect, text


revision = '0071_analytics_hotpath_identity_indexes'
down_revision = '0070_analytics_materialized_event_receipts'
branch_labels = None
depends_on = None


EVENT_TABLE = 'analytics_tracking_events'
USERNAME_INDEX = 'ix_analytics_events_course_username_type_time'
USER_ID_INDEX = 'ix_analytics_events_course_userid_type_time'


def _index_names() -> set[str]:
    bind = op.get_bind()
    inspector = inspect(bind)
    if EVENT_TABLE not in inspector.get_table_names():
        return set()
    return {
        str(item.get('name'))
        for item in inspector.get_indexes(EVENT_TABLE)
        if item.get('name')
    }


def upgrade() -> None:
    bind = op.get_bind()
    existing = _index_names()
    if bind.dialect.name == 'postgresql':
        # CREATE INDEX CONCURRENTLY cannot run inside Alembic's transaction.
        # Partial predicates keep NULL identities out of the hot-path indexes.
        with op.get_context().autocommit_block():
            # Runtime queries keep a 10s statement timeout, but building a
            # concurrent index on a large staging table may legitimately take
            # longer. Disable the timeout only for this migration connection.
            op.execute(text("SET statement_timeout = 0"))
            if USERNAME_INDEX not in existing:
                op.create_index(
                    USERNAME_INDEX,
                    EVENT_TABLE,
                    ['course_id', 'username', 'event_type', 'event_time'],
                    unique=False,
                    postgresql_concurrently=True,
                    postgresql_where=text('username IS NOT NULL'),
                )
            if USER_ID_INDEX not in existing:
                op.create_index(
                    USER_ID_INDEX,
                    EVENT_TABLE,
                    ['course_id', 'user_id', 'event_type', 'event_time'],
                    unique=False,
                    postgresql_concurrently=True,
                    postgresql_where=text('user_id IS NOT NULL'),
                )
    else:
        if USERNAME_INDEX not in existing:
            op.create_index(
                USERNAME_INDEX,
                EVENT_TABLE,
                ['course_id', 'username', 'event_type', 'event_time'],
                unique=False,
            )
        if USER_ID_INDEX not in existing:
            op.create_index(
                USER_ID_INDEX,
                EVENT_TABLE,
                ['course_id', 'user_id', 'event_type', 'event_time'],
                unique=False,
            )


def downgrade() -> None:
    bind = op.get_bind()
    existing = _index_names()
    names = [name for name in (USER_ID_INDEX, USERNAME_INDEX) if name in existing]
    if bind.dialect.name == 'postgresql':
        with op.get_context().autocommit_block():
            for name in names:
                op.drop_index(
                    name,
                    table_name=EVENT_TABLE,
                    postgresql_concurrently=True,
                )
    else:
        for name in names:
            op.drop_index(name, table_name=EVENT_TABLE)
