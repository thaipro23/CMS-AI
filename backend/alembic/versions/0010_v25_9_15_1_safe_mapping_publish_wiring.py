"""v25.9.15.1 safe mapping guard and bank release publish wiring

Revision ID: 0010_v25_9_15_1
Revises: 0009_v25_9_15_0
Create Date: 2026-06-05

Adds validation/audit metadata to Open edX course and chapter mappings. The
release publish wiring stores per-release Open edX component ids in
ai_bank_release_questions, so no additional columns are required for release
publishing itself.
"""
from alembic import op
import sqlalchemy as sa

revision = '0010_v25_9_15_1'
down_revision = '0009_v25_9_15_0'
branch_labels = None
depends_on = None


def _table_exists(bind, name: str) -> bool:
    return name in sa.inspect(bind).get_table_names()


def _column_exists(bind, table: str, column: str) -> bool:
    if not _table_exists(bind, table):
        return False
    return column in {item['name'] for item in sa.inspect(bind).get_columns(table)}


def _index_exists(bind, table: str, name: str) -> bool:
    if not _table_exists(bind, table):
        return False
    return name in {item['name'] for item in sa.inspect(bind).get_indexes(table)}


def upgrade() -> None:
    bind = op.get_bind()

    if _table_exists(bind, 'ai_edx_course_mappings'):
        if not _column_exists(bind, 'ai_edx_course_mappings', 'validation_status'):
            op.add_column('ai_edx_course_mappings', sa.Column('validation_status', sa.String(length=50), nullable=False, server_default='not_validated'))
        if not _column_exists(bind, 'ai_edx_course_mappings', 'validation_json'):
            op.add_column('ai_edx_course_mappings', sa.Column('validation_json', sa.JSON(), nullable=True))
        if not _column_exists(bind, 'ai_edx_course_mappings', 'validated_at'):
            op.add_column('ai_edx_course_mappings', sa.Column('validated_at', sa.DateTime(), nullable=True))
        if not _index_exists(bind, 'ai_edx_course_mappings', 'ix_ai_edx_course_mappings_validation_status'):
            op.create_index('ix_ai_edx_course_mappings_validation_status', 'ai_edx_course_mappings', ['validation_status'])

    if _table_exists(bind, 'ai_edx_course_chapter_mappings'):
        if not _column_exists(bind, 'ai_edx_course_chapter_mappings', 'validation_status'):
            op.add_column('ai_edx_course_chapter_mappings', sa.Column('validation_status', sa.String(length=50), nullable=False, server_default='not_validated'))
        if not _column_exists(bind, 'ai_edx_course_chapter_mappings', 'validation_json'):
            op.add_column('ai_edx_course_chapter_mappings', sa.Column('validation_json', sa.JSON(), nullable=True))
        if not _column_exists(bind, 'ai_edx_course_chapter_mappings', 'validated_at'):
            op.add_column('ai_edx_course_chapter_mappings', sa.Column('validated_at', sa.DateTime(), nullable=True))
        if not _index_exists(bind, 'ai_edx_course_chapter_mappings', 'ix_ai_edx_course_chapter_mappings_validation_status'):
            op.create_index('ix_ai_edx_course_chapter_mappings_validation_status', 'ai_edx_course_chapter_mappings', ['validation_status'])


def downgrade() -> None:
    bind = op.get_bind()
    if _table_exists(bind, 'ai_edx_course_chapter_mappings'):
        if _index_exists(bind, 'ai_edx_course_chapter_mappings', 'ix_ai_edx_course_chapter_mappings_validation_status'):
            op.drop_index('ix_ai_edx_course_chapter_mappings_validation_status', table_name='ai_edx_course_chapter_mappings')
        for column in ['validated_at', 'validation_json', 'validation_status']:
            if _column_exists(bind, 'ai_edx_course_chapter_mappings', column):
                op.drop_column('ai_edx_course_chapter_mappings', column)
    if _table_exists(bind, 'ai_edx_course_mappings'):
        if _index_exists(bind, 'ai_edx_course_mappings', 'ix_ai_edx_course_mappings_validation_status'):
            op.drop_index('ix_ai_edx_course_mappings_validation_status', table_name='ai_edx_course_mappings')
        for column in ['validated_at', 'validation_json', 'validation_status']:
            if _column_exists(bind, 'ai_edx_course_mappings', column):
                op.drop_column('ai_edx_course_mappings', column)
