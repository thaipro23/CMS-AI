"""Use Loki nanosecond cursors for learning analytics ingest.

Revision ID: 0068_analytics_loki_ingest
Revises: 0067_academic_daily_pipeline_v2
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision = '0068_analytics_loki_ingest'
down_revision = '0067_academic_daily_pipeline_v2'
branch_labels = None
depends_on = None


CHECKPOINT_TABLE = 'analytics_ingest_checkpoints'
EVENT_TABLE = 'analytics_tracking_events'


def _column_names(table: str) -> set[str]:
    bind = op.get_bind()
    inspector = inspect(bind)
    if table not in inspector.get_table_names():
        return set()
    return {item['name'] for item in inspector.get_columns(table)}


def _index_names(table: str) -> set[str]:
    bind = op.get_bind()
    inspector = inspect(bind)
    if table not in inspector.get_table_names():
        return set()
    return {item['name'] for item in inspector.get_indexes(table)}


def upgrade() -> None:
    checkpoint_columns = _column_names(CHECKPOINT_TABLE)
    if 'last_offset' in checkpoint_columns:
        op.alter_column(
            CHECKPOINT_TABLE,
            'last_offset',
            existing_type=sa.Integer(),
            type_=sa.BigInteger(),
            existing_nullable=False,
        )

    event_columns = _column_names(EVENT_TABLE)
    if EVENT_TABLE and event_columns:
        if 'loki_ts_ns' not in event_columns:
            op.add_column(EVENT_TABLE, sa.Column('loki_ts_ns', sa.BigInteger(), nullable=True))
        if 'source_pod' not in event_columns:
            op.add_column(EVENT_TABLE, sa.Column('source_pod', sa.String(length=255), nullable=True))
        if 'source_app' not in event_columns:
            op.add_column(EVENT_TABLE, sa.Column('source_app', sa.String(length=80), nullable=True))

        indexes = _index_names(EVENT_TABLE)
        if 'ix_analytics_tracking_events_loki_ts_ns' not in indexes:
            op.create_index('ix_analytics_tracking_events_loki_ts_ns', EVENT_TABLE, ['loki_ts_ns'])
        if 'ix_analytics_tracking_events_source_pod' not in indexes:
            op.create_index('ix_analytics_tracking_events_source_pod', EVENT_TABLE, ['source_pod'])
        if 'ix_analytics_tracking_events_source_app' not in indexes:
            op.create_index('ix_analytics_tracking_events_source_app', EVENT_TABLE, ['source_app'])


def downgrade() -> None:
    event_columns = _column_names(EVENT_TABLE)
    if event_columns:
        indexes = _index_names(EVENT_TABLE)
        for name in (
            'ix_analytics_tracking_events_source_app',
            'ix_analytics_tracking_events_source_pod',
            'ix_analytics_tracking_events_loki_ts_ns',
        ):
            if name in indexes:
                op.drop_index(name, table_name=EVENT_TABLE)
        for column in ('source_app', 'source_pod', 'loki_ts_ns'):
            if column in event_columns:
                op.drop_column(EVENT_TABLE, column)

    checkpoint_columns = _column_names(CHECKPOINT_TABLE)
    if 'last_offset' in checkpoint_columns:
        op.alter_column(
            CHECKPOINT_TABLE,
            'last_offset',
            existing_type=sa.BigInteger(),
            type_=sa.Integer(),
            existing_nullable=False,
        )
