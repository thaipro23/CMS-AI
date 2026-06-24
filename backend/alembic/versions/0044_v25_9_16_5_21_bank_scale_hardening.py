"""v25.9.16.5.21 bank scale hardening

Revision ID: 0044_v25_9_16_5_21_scale
Revises: 0043_v25_9_16_4_5_async_jobs
Create Date: 2026-06-24
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = '0044_v25_9_16_5_21_scale'
down_revision = '0043_v25_9_16_4_5_async_jobs'
branch_labels = None
depends_on = None


def _column_exists(bind, table_name: str, column_name: str) -> bool:
    inspector = sa.inspect(bind)
    return any(col.get('name') == column_name for col in inspector.get_columns(table_name))


def upgrade() -> None:
    bind = op.get_bind()
    if not _column_exists(bind, 'ai_bank_chapter_stats', 'carry_over_count'):
        op.add_column(
            'ai_bank_chapter_stats',
            sa.Column('carry_over_count', sa.Integer(), nullable=False, server_default='0'),
        )
        op.alter_column('ai_bank_chapter_stats', 'carry_over_count', server_default=None)


def downgrade() -> None:
    bind = op.get_bind()
    if _column_exists(bind, 'ai_bank_chapter_stats', 'carry_over_count'):
        op.drop_column('ai_bank_chapter_stats', 'carry_over_count')
