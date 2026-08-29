"""v25.9.16.3.6 material hard delete and cleanup policy

Revision ID: 0041_v25_9_16_3_6_cleanup
Revises: 0040_v25_9_16_3_0_learning
Create Date: 2026-06-19
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = '0041_v25_9_16_3_6_cleanup'
down_revision = '0040_v25_9_16_3_0_learning'
branch_labels = None
depends_on = None


def _has_column(table: str, column: str) -> bool:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    return any(col.get('name') == column for col in inspector.get_columns(table))


def _has_index(table: str, index_name: str) -> bool:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    return any(idx.get('name') == index_name for idx in inspector.get_indexes(table))


def upgrade() -> None:
    table = 'ai_learning_material_versions'
    if not _has_column(table, 'deleted_at'):
        op.add_column(table, sa.Column('deleted_at', sa.DateTime(), nullable=True))
    if not _has_column(table, 'deleted_by'):
        op.add_column(table, sa.Column('deleted_by', sa.String(length=255), nullable=True))
    if not _has_index(table, 'ix_ai_learning_material_versions_deleted_at'):
        op.create_index(op.f('ix_ai_learning_material_versions_deleted_at'), table, ['deleted_at'])
    if not _has_index(table, 'ix_ai_material_versions_status_deleted'):
        op.create_index('ix_ai_material_versions_status_deleted', table, ['status', 'deleted_at'])


def downgrade() -> None:
    table = 'ai_learning_material_versions'
    if _has_index(table, 'ix_ai_material_versions_status_deleted'):
        op.drop_index('ix_ai_material_versions_status_deleted', table_name=table)
    if _has_index(table, 'ix_ai_learning_material_versions_deleted_at'):
        op.drop_index(op.f('ix_ai_learning_material_versions_deleted_at'), table_name=table)
    if _has_column(table, 'deleted_by'):
        op.drop_column(table, 'deleted_by')
    if _has_column(table, 'deleted_at'):
        op.drop_column(table, 'deleted_at')
