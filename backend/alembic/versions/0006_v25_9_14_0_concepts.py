"""v25.9.14.0 concept-aware generation

Revision ID: 0006_v25_9_14_0
Revises: 0005_v25_9_13_42
Create Date: 2026-06-04

This migration is intentionally idempotent because the project legacy
0001 migration creates tables from current SQLAlchemy metadata on fresh DBs.
On a clean test database, ai_questions may already contain concept columns
before Alembic reaches this historical migration.
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = '0006_v25_9_14_0'
down_revision = '0005_v25_9_13_42'
branch_labels = None
depends_on = None


def _json_type():
    return postgresql.JSON(astext_type=sa.Text())


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


def _create_index_if_missing(bind, index_name: str, table_name: str, columns: list[str]) -> None:
    if _table_exists(bind, table_name) and not _index_exists(bind, table_name, index_name):
        op.create_index(index_name, table_name, columns)


def upgrade() -> None:
    bind = op.get_bind()

    if not _table_exists(bind, 'ai_concepts'):
        op.create_table(
            'ai_concepts',
            sa.Column('id', sa.String(), primary_key=True),
            sa.Column('course_id', sa.String(length=255), nullable=True),
            sa.Column('chapter_node_id', sa.String(length=512), nullable=True),
            sa.Column('source_node_id', sa.String(length=512), nullable=True),
            sa.Column('source_node_title', sa.String(length=512), nullable=True),
            sa.Column('concept_key', sa.String(length=255), nullable=True),
            sa.Column('title', sa.String(length=512), server_default='', nullable=True),
            sa.Column('summary', sa.Text(), server_default='', nullable=True),
            sa.Column('learning_objective', sa.Text(), server_default='', nullable=True),
            sa.Column('difficulty_hint', sa.String(length=50), server_default='easy', nullable=True),
            sa.Column('importance_score', sa.Float(), server_default='0.5', nullable=True),
            sa.Column('source_chunk_ids', _json_type(), nullable=True),
            sa.Column('source_evidence', sa.Text(), server_default='', nullable=True),
            sa.Column('token_count', sa.Integer(), server_default='0', nullable=True),
            sa.Column('status', sa.String(length=50), server_default='active', nullable=True),
            sa.Column('metadata_json', _json_type(), nullable=True),
            sa.Column('created_at', sa.DateTime(), nullable=True),
            sa.Column('updated_at', sa.DateTime(), nullable=True),
            sa.UniqueConstraint('course_id', 'source_node_id', 'concept_key', name='uq_ai_concepts_course_node_key'),
        )

    _create_index_if_missing(bind, 'ix_ai_concepts_course_node_status', 'ai_concepts', ['course_id', 'source_node_id', 'status'])
    _create_index_if_missing(bind, 'ix_ai_concepts_course_chapter_difficulty', 'ai_concepts', ['course_id', 'chapter_node_id', 'difficulty_hint'])

    _add_column_if_missing(bind, 'ai_questions', sa.Column('concept_id', sa.String(), nullable=True))
    _add_column_if_missing(bind, 'ai_questions', sa.Column('concept_title', sa.String(length=512), nullable=True))
    _add_column_if_missing(bind, 'ai_questions', sa.Column('concept_key', sa.String(length=255), nullable=True))
    _create_index_if_missing(bind, 'ix_ai_questions_course_concept_status', 'ai_questions', ['course_id', 'concept_id', 'status'])


def downgrade() -> None:
    bind = op.get_bind()
    if _index_exists(bind, 'ai_questions', 'ix_ai_questions_course_concept_status'):
        op.drop_index('ix_ai_questions_course_concept_status', table_name='ai_questions')
    for column_name in ('concept_key', 'concept_title', 'concept_id'):
        if column_name in _columns(bind, 'ai_questions'):
            op.drop_column('ai_questions', column_name)
    if _index_exists(bind, 'ai_concepts', 'ix_ai_concepts_course_chapter_difficulty'):
        op.drop_index('ix_ai_concepts_course_chapter_difficulty', table_name='ai_concepts')
    if _index_exists(bind, 'ai_concepts', 'ix_ai_concepts_course_node_status'):
        op.drop_index('ix_ai_concepts_course_node_status', table_name='ai_concepts')
    if _table_exists(bind, 'ai_concepts'):
        op.drop_table('ai_concepts')
