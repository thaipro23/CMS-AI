"""v25.9.16.1 AP username mapping

Revision ID: 0028_v25_9_16_1_ap_user_map
Revises: 0027_v25_9_16_0_academic_ap_core
Create Date: 2026-06-16
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = '0028_v25_9_16_1_ap_user_map'
down_revision = '0027_v25_9_16_0_academic_ap_core'
branch_labels = None
depends_on = None


def upgrade() -> None:
    if sa.inspect(op.get_bind()).has_table('openedx_user_mappings'):
        return
    op.create_table(
        'openedx_user_mappings',
        sa.Column('id', sa.String(), primary_key=True),
        sa.Column('student_id', sa.String(), sa.ForeignKey('academic_students.id'), nullable=False),
        sa.Column('ap_student_code', sa.String(length=64), nullable=True),
        sa.Column('ap_username', sa.String(length=255), nullable=False),
        sa.Column('ap_email', sa.String(length=255), nullable=True),
        sa.Column('openedx_user_id', sa.String(length=64), nullable=True),
        sa.Column('openedx_username', sa.String(length=255), nullable=True),
        sa.Column('openedx_email', sa.String(length=255), nullable=True),
        sa.Column('openedx_is_active', sa.Boolean(), nullable=True),
        sa.Column('match_method', sa.String(length=50), nullable=False, server_default='not_checked'),
        sa.Column('match_status', sa.String(length=50), nullable=False, server_default='not_checked'),
        sa.Column('confidence', sa.Float(), nullable=False, server_default='0'),
        sa.Column('note', sa.Text(), nullable=False, server_default=''),
        sa.Column('raw_json', sa.JSON(), nullable=True),
        sa.Column('last_resolved_at', sa.DateTime(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.UniqueConstraint('student_id', name='uq_openedx_user_mappings_student_id'),
    )
    op.create_index('ix_openedx_user_mappings_student_id', 'openedx_user_mappings', ['student_id'])
    op.create_index('ix_openedx_user_mappings_ap_student_code', 'openedx_user_mappings', ['ap_student_code'])
    op.create_index('ix_openedx_user_mappings_ap_username', 'openedx_user_mappings', ['ap_username'])
    op.create_index('ix_openedx_user_mappings_openedx_user_id', 'openedx_user_mappings', ['openedx_user_id'])
    op.create_index('ix_openedx_user_mappings_openedx_username', 'openedx_user_mappings', ['openedx_username'])
    op.create_index('ix_openedx_user_mappings_match_method', 'openedx_user_mappings', ['match_method'])
    op.create_index('ix_openedx_user_mappings_match_status', 'openedx_user_mappings', ['match_status'])
    op.create_index('ix_openedx_user_mappings_last_resolved_at', 'openedx_user_mappings', ['last_resolved_at'])
    op.create_index('ix_openedx_user_mappings_ap_username_status', 'openedx_user_mappings', ['ap_username', 'match_status'])
    op.create_index('ix_openedx_user_mappings_student_status', 'openedx_user_mappings', ['student_id', 'match_status'])


def downgrade() -> None:
    op.drop_table('openedx_user_mappings')
