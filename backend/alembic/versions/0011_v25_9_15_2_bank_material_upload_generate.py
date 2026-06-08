"""v25.9.15.2 bank material upload and generate from bank version

Revision ID: 0011_v25_9_15_2
Revises: 0010_v25_9_15_1
Create Date: 2026-06-08
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = '0011_v25_9_15_2'
down_revision = '0010_v25_9_15_1'
branch_labels = None
depends_on = None


def _table_exists(bind, table_name: str) -> bool:
    return sa.inspect(bind).has_table(table_name)


def _index_exists(bind, table_name: str, index_name: str) -> bool:
    return any(item.get('name') == index_name for item in sa.inspect(bind).get_indexes(table_name))


def _create_index_if_missing(bind, index_name: str, table_name: str, columns: list[str]) -> None:
    if _table_exists(bind, table_name) and not _index_exists(bind, table_name, index_name):
        op.create_index(index_name, table_name, columns)


def upgrade() -> None:
    bind = op.get_bind()
    if not _table_exists(bind, 'ai_material_chunks'):
        op.create_table(
            'ai_material_chunks',
            sa.Column('id', sa.String(), primary_key=True),
            sa.Column('material_version_id', sa.String(), sa.ForeignKey('ai_learning_material_versions.id'), nullable=False),
            sa.Column('bank_version_id', sa.String(), sa.ForeignKey('ai_question_bank_versions.id'), nullable=False),
            sa.Column('subject_id', sa.String(), sa.ForeignKey('ai_subjects.id'), nullable=False),
            sa.Column('chapter_id', sa.String(), sa.ForeignKey('ai_subject_chapters.id'), nullable=False),
            sa.Column('chunk_index', sa.Integer(), nullable=False, server_default='1'),
            sa.Column('content', sa.Text(), nullable=False),
            sa.Column('token_count', sa.Integer(), nullable=False, server_default='0'),
            sa.Column('source_type', sa.String(length=100), nullable=False, server_default='file'),
            sa.Column('page_number', sa.Integer(), nullable=True),
            sa.Column('source_ref', sa.String(length=1024), nullable=False, server_default=''),
            sa.Column('content_hash', sa.String(length=128), nullable=True),
            sa.Column('created_at', sa.DateTime(), nullable=False),
            sa.UniqueConstraint('material_version_id', 'chunk_index', name='uq_ai_material_chunk_index'),
        )
        op.create_index('ix_ai_material_chunks_material_version_id', 'ai_material_chunks', ['material_version_id'])
        op.create_index('ix_ai_material_chunks_bank_version_id', 'ai_material_chunks', ['bank_version_id'])
        op.create_index('ix_ai_material_chunks_subject_id', 'ai_material_chunks', ['subject_id'])
        op.create_index('ix_ai_material_chunks_chapter_id', 'ai_material_chunks', ['chapter_id'])
        op.create_index('ix_ai_material_chunks_content_hash', 'ai_material_chunks', ['content_hash'])
        op.create_index('ix_ai_material_chunks_bank_subject_chapter', 'ai_material_chunks', ['bank_version_id', 'subject_id', 'chapter_id'])
        op.create_index('ix_ai_material_chunks_bank_source', 'ai_material_chunks', ['bank_version_id', 'source_type'])
    else:
        for index_name, columns in {
            'ix_ai_material_chunks_material_version_id': ['material_version_id'],
            'ix_ai_material_chunks_bank_version_id': ['bank_version_id'],
            'ix_ai_material_chunks_subject_id': ['subject_id'],
            'ix_ai_material_chunks_chapter_id': ['chapter_id'],
            'ix_ai_material_chunks_content_hash': ['content_hash'],
            'ix_ai_material_chunks_bank_subject_chapter': ['bank_version_id', 'subject_id', 'chapter_id'],
            'ix_ai_material_chunks_bank_source': ['bank_version_id', 'source_type'],
        }.items():
            _create_index_if_missing(bind, index_name, 'ai_material_chunks', columns)


def downgrade() -> None:
    bind = op.get_bind()
    if _table_exists(bind, 'ai_material_chunks'):
        op.drop_table('ai_material_chunks')
