"""v25.9.16.2.11 academic campuses master data

Revision ID: 0037_v25_9_16_2_11_campus
Revises: 0030_v25_9_16_2_1_safety
Create Date: 2026-06-17
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = '0037_v25_9_16_2_11_campus'
down_revision = '0030_v25_9_16_2_1_safety'
branch_labels = None
depends_on = None


def upgrade() -> None:
    if sa.inspect(op.get_bind()).has_table('academic_campuses'):
        return
    op.create_table(
        'academic_campuses',
        sa.Column('id', sa.String(), primary_key=True),
        sa.Column('campus_code', sa.String(length=64), nullable=False),
        sa.Column('campus_name', sa.String(length=255), nullable=False, server_default=''),
        sa.Column('branch', sa.String(length=64), nullable=True),
        sa.Column('active', sa.Boolean(), nullable=False, server_default=sa.text('true')),
        sa.Column('sort_order', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('metadata_json', sa.JSON(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
    )
    op.create_unique_constraint('uq_academic_campuses_code_branch', 'academic_campuses', ['campus_code', 'branch'])
    op.create_index('ix_academic_campuses_campus_code', 'academic_campuses', ['campus_code'])
    op.create_index('ix_academic_campuses_branch', 'academic_campuses', ['branch'])
    op.create_index('ix_academic_campuses_active', 'academic_campuses', ['active'])
    op.create_index('ix_academic_campuses_sort_order', 'academic_campuses', ['sort_order'])
    op.create_index('ix_academic_campuses_branch_active_order', 'academic_campuses', ['branch', 'active', 'sort_order'])


def downgrade() -> None:
    op.drop_index('ix_academic_campuses_branch_active_order', table_name='academic_campuses')
    op.drop_index('ix_academic_campuses_sort_order', table_name='academic_campuses')
    op.drop_index('ix_academic_campuses_active', table_name='academic_campuses')
    op.drop_index('ix_academic_campuses_branch', table_name='academic_campuses')
    op.drop_index('ix_academic_campuses_campus_code', table_name='academic_campuses')
    op.drop_constraint('uq_academic_campuses_code_branch', 'academic_campuses', type_='unique')
    op.drop_table('academic_campuses')
