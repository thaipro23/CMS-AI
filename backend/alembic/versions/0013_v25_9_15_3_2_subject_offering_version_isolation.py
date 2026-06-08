"""v25.9.15.3.2 subject offering version isolation

Revision ID: 0013_v25_9_15_3_2
Revises: 0012_v25_9_15_3
Create Date: 2026-06-08
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = '0013_v25_9_15_3_2'
down_revision = '0012_v25_9_15_3'
branch_labels = None
depends_on = None


def _table_exists(bind, table_name: str) -> bool:
    return sa.inspect(bind).has_table(table_name)


def _columns(bind, table_name: str) -> set[str]:
    if not _table_exists(bind, table_name):
        return set()
    return {item['name'] for item in sa.inspect(bind).get_columns(table_name)}


def _index_exists(bind, table_name: str, index_name: str) -> bool:
    return any(item.get('name') == index_name for item in sa.inspect(bind).get_indexes(table_name)) if _table_exists(bind, table_name) else False


def _unique_constraint_exists(bind, table_name: str, constraint_name: str) -> bool:
    if not _table_exists(bind, table_name):
        return False
    return any(
        item.get('name') == constraint_name
        for item in sa.inspect(bind).get_unique_constraints(table_name)
    )


def _drop_unique_constraint_if_exists(bind, table_name: str, constraint_name: str) -> None:
    if _unique_constraint_exists(bind, table_name, constraint_name):
        op.drop_constraint(constraint_name, table_name, type_='unique')


def _create_unique_constraint_if_missing(bind, table_name: str, constraint_name: str, columns: list[str]) -> None:
    if _table_exists(bind, table_name) and not _unique_constraint_exists(bind, table_name, constraint_name):
        op.create_unique_constraint(constraint_name, table_name, columns)


def _add_column_if_missing(bind, table: str, column: sa.Column) -> None:
    if _table_exists(bind, table) and column.name not in _columns(bind, table):
        op.add_column(table, column)


def _create_index_if_missing(bind, index_name: str, table_name: str, columns: list[str]) -> None:
    if _table_exists(bind, table_name) and not _index_exists(bind, table_name, index_name):
        op.create_index(index_name, table_name, columns)


def upgrade() -> None:
    bind = op.get_bind()

    if not _table_exists(bind, 'ai_subject_offerings'):
        op.create_table(
            'ai_subject_offerings',
            sa.Column('id', sa.String(), primary_key=True),
            sa.Column('department_id', sa.String(), sa.ForeignKey('ai_departments.id'), nullable=True),
            sa.Column('subject_id', sa.String(), sa.ForeignKey('ai_subjects.id'), nullable=False),
            sa.Column('code', sa.String(length=128), nullable=False),
            sa.Column('name', sa.String(length=255), nullable=False, server_default=''),
            sa.Column('term', sa.String(length=100), nullable=True),
            sa.Column('version_code', sa.String(length=64), nullable=False, server_default='v1.0'),
            sa.Column('based_on_offering_id', sa.String(), sa.ForeignKey('ai_subject_offerings.id'), nullable=True),
            sa.Column('status', sa.String(length=50), nullable=False, server_default='draft'),
            sa.Column('metadata_json', sa.JSON(), nullable=True),
            sa.Column('created_by', sa.String(length=255), nullable=True),
            sa.Column('approved_by', sa.String(length=255), nullable=True),
            sa.Column('published_at', sa.DateTime(), nullable=True),
            sa.Column('created_at', sa.DateTime(), nullable=False),
            sa.Column('updated_at', sa.DateTime(), nullable=False),
            sa.UniqueConstraint('subject_id', 'code', name='uq_ai_subject_offering_subject_code'),
        )
        op.create_index('ix_ai_subject_offerings_department_id', 'ai_subject_offerings', ['department_id'])
        op.create_index('ix_ai_subject_offerings_subject_id', 'ai_subject_offerings', ['subject_id'])
        op.create_index('ix_ai_subject_offerings_code', 'ai_subject_offerings', ['code'])
        op.create_index('ix_ai_subject_offerings_term', 'ai_subject_offerings', ['term'])
        op.create_index('ix_ai_subject_offerings_status', 'ai_subject_offerings', ['status'])
        op.create_index('ix_ai_subject_offerings_based_on_offering_id', 'ai_subject_offerings', ['based_on_offering_id'])
        op.create_index('ix_ai_subject_offerings_subject_status', 'ai_subject_offerings', ['subject_id', 'status'])

    nullable_tables = [
        'ai_subject_chapters',
        'ai_question_bank_versions',
        'ai_learning_material_versions',
        'ai_material_chunks',
        'ai_concept_versions',
        'ai_bank_question_families',
        'ai_question_bank_releases',
        'ai_edx_course_mappings',
        'ai_quiz_blueprints',
        'ai_course_quiz_instances',
    ]
    for table in nullable_tables:
        _add_column_if_missing(bind, table, sa.Column('subject_offering_id', sa.String(), sa.ForeignKey('ai_subject_offerings.id'), nullable=True))
        _create_index_if_missing(bind, f'ix_{table}_subject_offering_id', table, ['subject_offering_id'])

    if _table_exists(bind, 'ai_subject_chapters'):
        # Never execute DDL and swallow the exception inside a Postgres transaction.
        # A failed DROP/CREATE CONSTRAINT aborts the whole Alembic transaction and
        # later inspector calls fail with InFailedSqlTransaction. Check first.
        _drop_unique_constraint_if_exists(bind, 'ai_subject_chapters', 'uq_ai_subject_chapter_no')
        _create_unique_constraint_if_missing(
            bind,
            'ai_subject_chapters',
            'uq_ai_subject_offering_chapter_no',
            ['subject_id', 'subject_offering_id', 'chapter_no'],
        )
    _create_index_if_missing(bind, 'ix_ai_subject_chapters_offering_order', 'ai_subject_chapters', ['subject_offering_id', 'sort_order'])
    _create_index_if_missing(bind, 'ix_ai_bank_versions_offering_status', 'ai_question_bank_versions', ['subject_offering_id', 'status'])


def downgrade() -> None:
    bind = op.get_bind()
    # Keep nullable subject_offering_id columns during downgrade to avoid data loss.
    if _table_exists(bind, 'ai_subject_offerings'):
        op.drop_table('ai_subject_offerings')
