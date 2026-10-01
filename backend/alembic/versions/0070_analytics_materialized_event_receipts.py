"""Add durable per-event analytics materialization receipts.

Revision ID: 0070_analytics_materialized_event_receipts
Revises: 0069_analytics_tracking_query_indexes
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision = '0070_analytics_materialized_event_receipts'
down_revision = '0069_analytics_tracking_query_indexes'
branch_labels = None
depends_on = None


TABLE_NAME = 'analytics_materialized_event_receipts'


def upgrade() -> None:
    bind = op.get_bind()
    if TABLE_NAME in inspect(bind).get_table_names():
        return
    op.create_table(
        TABLE_NAME,
        sa.Column('event_id', sa.String(), nullable=False),
        sa.Column('family', sa.String(length=32), nullable=False),
        sa.Column('course_id', sa.String(length=255), nullable=False),
        sa.Column('canonical_username', sa.String(length=255), nullable=False),
        sa.Column('raw_username', sa.String(length=255), nullable=True),
        sa.Column('raw_user_id', sa.String(length=64), nullable=True),
        sa.Column('event_time', sa.DateTime(), nullable=True),
        sa.Column('loki_ts_ns', sa.BigInteger(), nullable=True),
        sa.Column('materialized_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(
            ['event_id'],
            ['analytics_tracking_events.id'],
            ondelete='CASCADE',
        ),
        sa.PrimaryKeyConstraint('event_id'),
    )


def downgrade() -> None:
    bind = op.get_bind()
    if TABLE_NAME in inspect(bind).get_table_names():
        op.drop_table(TABLE_NAME)
