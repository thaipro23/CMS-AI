"""Add exact question-type quota to Quiz Blueprint.

Revision ID: 0061_v25_9_16_7_2_64_39
Revises: 0060_v25_9_16_7_2_64_38
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect

revision = '0061_v25_9_16_7_2_64_39'
down_revision = '0060_v25_9_16_7_2_64_38'
branch_labels = None
depends_on = None

_COLUMNS = (
    'single_select_count',
    'multi_select_count',
    'text_input_count',
    'numerical_input_count',
)


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    if 'ai_quiz_blueprints' not in inspector.get_table_names():
        return
    existing = {column['name'] for column in inspector.get_columns('ai_quiz_blueprints')}
    for name in _COLUMNS:
        if name not in existing:
            op.add_column('ai_quiz_blueprints', sa.Column(name, sa.Integer(), nullable=True))


def downgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    if 'ai_quiz_blueprints' not in inspector.get_table_names():
        return
    existing = {column['name'] for column in inspector.get_columns('ai_quiz_blueprints')}
    for name in reversed(_COLUMNS):
        if name in existing:
            op.drop_column('ai_quiz_blueprints', name)
