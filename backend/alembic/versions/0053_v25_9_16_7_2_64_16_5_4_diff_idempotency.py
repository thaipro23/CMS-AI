"""v25.9.16.7.2.64.16.5.4 diff preview permission and idempotency hardening

Revision ID: 0053_v25_9_16_7_2_64_16_5_4
Revises: 0052_v25_9_16_7_2_27
Create Date: 2026-07-14
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = '0053_v25_9_16_7_2_64_16_5_4'
down_revision = '0052_v25_9_16_7_2_27'
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    columns = {column['name'] for column in inspector.get_columns('ai_bank_version_diffs')}
    if 'idempotency_key' not in columns:
        op.add_column('ai_bank_version_diffs', sa.Column('idempotency_key', sa.String(length=64), nullable=True))
    constraints = {row.get('name') for row in inspector.get_unique_constraints('ai_bank_version_diffs')}
    if 'uq_ai_bank_version_diff_idempotency' not in constraints:
        op.create_unique_constraint(
            'uq_ai_bank_version_diff_idempotency',
            'ai_bank_version_diffs',
            ['from_bank_version_id', 'to_bank_version_id', 'idempotency_key'],
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    constraints = {row.get('name') for row in inspector.get_unique_constraints('ai_bank_version_diffs')}
    if 'uq_ai_bank_version_diff_idempotency' in constraints:
        op.drop_constraint('uq_ai_bank_version_diff_idempotency', 'ai_bank_version_diffs', type_='unique')
    columns = {column['name'] for column in inspector.get_columns('ai_bank_version_diffs')}
    if 'idempotency_key' in columns:
        op.drop_column('ai_bank_version_diffs', 'idempotency_key')
