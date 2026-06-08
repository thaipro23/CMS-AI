"""v25.9.15.3 version diff carry-over retire questions

Revision ID: 0012_v25_9_15_3
Revises: 0011_v25_9_15_2
Create Date: 2026-06-08
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = '0012_v25_9_15_3'
down_revision = '0011_v25_9_15_2'
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


def _add_column_if_missing(bind, table: str, column: sa.Column) -> None:
    if _table_exists(bind, table) and column.name not in _columns(bind, table):
        op.add_column(table, column)


def _create_index_if_missing(bind, index_name: str, table_name: str, columns: list[str]) -> None:
    if _table_exists(bind, table_name) and not _index_exists(bind, table_name, index_name):
        op.create_index(index_name, table_name, columns)


def upgrade() -> None:
    bind = op.get_bind()

    _add_column_if_missing(bind, 'ai_questions', sa.Column('previous_question_id', sa.String(), sa.ForeignKey('ai_questions.id'), nullable=True))
    _add_column_if_missing(bind, 'ai_questions', sa.Column('lineage_root_question_id', sa.String(), nullable=True))
    _add_column_if_missing(bind, 'ai_questions', sa.Column('question_revision_no', sa.Integer(), nullable=False, server_default='1'))
    _add_column_if_missing(bind, 'ai_questions', sa.Column('is_carry_over', sa.Boolean(), nullable=False, server_default=sa.false()))
    _add_column_if_missing(bind, 'ai_questions', sa.Column('is_retired', sa.Boolean(), nullable=False, server_default=sa.false()))
    _add_column_if_missing(bind, 'ai_questions', sa.Column('retired_reason', sa.Text(), nullable=True))
    _add_column_if_missing(bind, 'ai_questions', sa.Column('retired_at', sa.DateTime(), nullable=True))
    for index_name, columns in {
        'ix_ai_questions_previous_question_id': ['previous_question_id'],
        'ix_ai_questions_lineage_root_question_id': ['lineage_root_question_id'],
        'ix_ai_questions_is_carry_over': ['is_carry_over'],
        'ix_ai_questions_is_retired': ['is_retired'],
        'ix_ai_questions_bank_lineage': ['bank_version_id', 'lineage_root_question_id'],
        'ix_ai_questions_bank_retired': ['bank_version_id', 'is_retired'],
    }.items():
        _create_index_if_missing(bind, index_name, 'ai_questions', columns)

    if not _table_exists(bind, 'ai_bank_version_diffs'):
        op.create_table(
            'ai_bank_version_diffs',
            sa.Column('id', sa.String(), primary_key=True),
            sa.Column('from_bank_version_id', sa.String(), sa.ForeignKey('ai_question_bank_versions.id'), nullable=False),
            sa.Column('to_bank_version_id', sa.String(), sa.ForeignKey('ai_question_bank_versions.id'), nullable=False),
            sa.Column('status', sa.String(length=50), nullable=False, server_default='preview'),
            sa.Column('material_similarity', sa.Float(), nullable=True),
            sa.Column('summary_json', sa.JSON(), nullable=True),
            sa.Column('created_by', sa.String(length=255), nullable=True),
            sa.Column('applied_by', sa.String(length=255), nullable=True),
            sa.Column('applied_at', sa.DateTime(), nullable=True),
            sa.Column('created_at', sa.DateTime(), nullable=False),
        )
        op.create_index('ix_ai_bank_version_diffs_from_bank_version_id', 'ai_bank_version_diffs', ['from_bank_version_id'])
        op.create_index('ix_ai_bank_version_diffs_to_bank_version_id', 'ai_bank_version_diffs', ['to_bank_version_id'])
        op.create_index('ix_ai_bank_version_diffs_status', 'ai_bank_version_diffs', ['status'])
        op.create_index('ix_ai_bank_version_diffs_pair_status', 'ai_bank_version_diffs', ['from_bank_version_id', 'to_bank_version_id', 'status'])

    if not _table_exists(bind, 'ai_bank_version_diff_items'):
        op.create_table(
            'ai_bank_version_diff_items',
            sa.Column('id', sa.String(), primary_key=True),
            sa.Column('diff_id', sa.String(), sa.ForeignKey('ai_bank_version_diffs.id'), nullable=False),
            sa.Column('item_type', sa.String(length=50), nullable=False),
            sa.Column('source_id', sa.String(), nullable=True),
            sa.Column('target_id', sa.String(), nullable=True),
            sa.Column('change_type', sa.String(length=50), nullable=False),
            sa.Column('confidence', sa.Float(), nullable=True),
            sa.Column('reason', sa.Text(), nullable=False, server_default=''),
            sa.Column('metadata_json', sa.JSON(), nullable=True),
            sa.Column('created_at', sa.DateTime(), nullable=False),
        )
        for index_name, columns in {
            'ix_ai_bank_version_diff_items_diff_id': ['diff_id'],
            'ix_ai_bank_version_diff_items_item_type': ['item_type'],
            'ix_ai_bank_version_diff_items_source_id': ['source_id'],
            'ix_ai_bank_version_diff_items_target_id': ['target_id'],
            'ix_ai_bank_version_diff_items_change_type': ['change_type'],
            'ix_ai_bank_diff_items_diff_type_change': ['diff_id', 'item_type', 'change_type'],
        }.items():
            op.create_index(index_name, 'ai_bank_version_diff_items', columns)


def downgrade() -> None:
    bind = op.get_bind()
    if _table_exists(bind, 'ai_bank_version_diff_items'):
        op.drop_table('ai_bank_version_diff_items')
    if _table_exists(bind, 'ai_bank_version_diffs'):
        op.drop_table('ai_bank_version_diffs')
    # Keep lineage columns in downgrade for safety in production-like test DBs.
