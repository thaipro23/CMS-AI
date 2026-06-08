"""v25.9.14.1 question family id

Revision ID: 0007_v25_9_14_1
Revises: 0006_v25_9_14_0
Create Date: 2026-06-04

Idempotent for fresh test DBs where 0001 created current SQLAlchemy metadata.
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = '0007_v25_9_14_1'
down_revision = '0006_v25_9_14_0'
branch_labels = None
depends_on = None


def _table_exists(bind, table_name: str) -> bool:
    return sa.inspect(bind).has_table(table_name)


def _columns(bind, table_name: str) -> set[str]:
    if not _table_exists(bind, table_name):
        return set()
    return {item['name'] for item in sa.inspect(bind).get_columns(table_name)}


def _index_exists(bind, table_name: str, index_name: str) -> bool:
    if not _table_exists(bind, table_name):
        return False
    return any(item.get('name') == index_name for item in sa.inspect(bind).get_indexes(table_name))


def _add_column_if_missing(bind, table_name: str, column: sa.Column) -> None:
    if _table_exists(bind, table_name) and column.name not in _columns(bind, table_name):
        op.add_column(table_name, column)


def upgrade() -> None:
    bind = op.get_bind()
    _add_column_if_missing(bind, 'ai_questions', sa.Column('question_family_id', sa.String(length=255), nullable=True))
    _add_column_if_missing(bind, 'ai_questions', sa.Column('variant_no', sa.Integer(), nullable=True))
    _add_column_if_missing(bind, 'ai_questions', sa.Column('source_evidence', sa.Text(), server_default='', nullable=True))
    if _table_exists(bind, 'ai_questions') and not _index_exists(bind, 'ai_questions', 'ix_ai_questions_course_family_status'):
        op.create_index('ix_ai_questions_course_family_status', 'ai_questions', ['course_id', 'question_family_id', 'status'])


def downgrade() -> None:
    bind = op.get_bind()
    if _index_exists(bind, 'ai_questions', 'ix_ai_questions_course_family_status'):
        op.drop_index('ix_ai_questions_course_family_status', table_name='ai_questions')
    for column_name in ('source_evidence', 'variant_no', 'question_family_id'):
        if column_name in _columns(bind, 'ai_questions'):
            op.drop_column('ai_questions', column_name)
