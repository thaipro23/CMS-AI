"""v25.9.15.6.35 bank search engine

Revision ID: 0018_v25_9_15_6_35
Revises: 0017_v25_9_15_6_34
Create Date: 2026-06-15

Adds lightweight search documents for Bank questions and trigram-friendly
indexes for hierarchy search. The question search table is backfilled by the
admin rebuild endpoint, not by migration, so production deploys are not forced
to scan 1.5M questions during Alembic upgrade.
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = '0018_v25_9_15_6_35'
down_revision = '0017_v25_9_15_6_34'
branch_labels = None
depends_on = None


def _table_exists(name: str) -> bool:
    return sa.inspect(op.get_bind()).has_table(name)


def _column_exists(table: str, column: str) -> bool:
    if not _table_exists(table):
        return False
    return column in {item.get('name') for item in sa.inspect(op.get_bind()).get_columns(table)}


def _index_exists(table: str, name: str) -> bool:
    if not _table_exists(table):
        return False
    return any(item.get('name') == name for item in sa.inspect(op.get_bind()).get_indexes(table))


def _create_index_if_missing(name: str, table: str, columns: list[str]) -> None:
    if not _index_exists(table, name):
        op.create_index(name, table, columns)


def _is_postgresql() -> bool:
    bind = op.get_bind()
    return bool(bind and bind.dialect.name == 'postgresql')


def upgrade() -> None:
    if not _table_exists('ai_question_search_documents'):
        op.create_table(
            'ai_question_search_documents',
            sa.Column('question_id', sa.String(), sa.ForeignKey('ai_questions.id'), primary_key=True),
            sa.Column('bank_version_id', sa.String(), sa.ForeignKey('ai_question_bank_versions.id'), nullable=True),
            sa.Column('subject_id', sa.String(), sa.ForeignKey('ai_subjects.id'), nullable=True),
            sa.Column('subject_offering_id', sa.String(), sa.ForeignKey('ai_subject_offerings.id'), nullable=True),
            sa.Column('chapter_id', sa.String(), sa.ForeignKey('ai_subject_chapters.id'), nullable=True),
            sa.Column('status', sa.String(length=50), nullable=False, server_default='draft'),
            sa.Column('difficulty', sa.String(length=50), nullable=False, server_default='easy'),
            sa.Column('question_text_preview', sa.String(length=500), nullable=False, server_default=''),
            sa.Column('concept_title', sa.String(length=512), nullable=True),
            sa.Column('question_family_id', sa.String(length=255), nullable=True),
            sa.Column('search_text', sa.Text(), nullable=False, server_default=''),
            sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        )
    _create_index_if_missing('ix_ai_question_search_bank_version', 'ai_question_search_documents', ['bank_version_id'])
    _create_index_if_missing('ix_ai_question_search_subject', 'ai_question_search_documents', ['subject_id'])
    _create_index_if_missing('ix_ai_question_search_offering', 'ai_question_search_documents', ['subject_offering_id'])
    _create_index_if_missing('ix_ai_question_search_chapter', 'ai_question_search_documents', ['chapter_id'])
    _create_index_if_missing('ix_ai_question_search_status', 'ai_question_search_documents', ['status'])
    _create_index_if_missing('ix_ai_question_search_difficulty', 'ai_question_search_documents', ['difficulty'])
    _create_index_if_missing('ix_ai_question_search_family', 'ai_question_search_documents', ['question_family_id'])
    _create_index_if_missing('ix_ai_question_search_bank_status', 'ai_question_search_documents', ['bank_version_id', 'status'])
    _create_index_if_missing('ix_ai_question_search_subject_chapter_status', 'ai_question_search_documents', ['subject_id', 'chapter_id', 'status'])
    _create_index_if_missing('ix_ai_question_search_chapter_difficulty', 'ai_question_search_documents', ['chapter_id', 'difficulty'])
    _create_index_if_missing('ix_ai_question_search_updated', 'ai_question_search_documents', ['updated_at'])

    if _is_postgresql():
        op.execute('CREATE EXTENSION IF NOT EXISTS pg_trgm')
        op.execute('CREATE EXTENSION IF NOT EXISTS unaccent')
        if not _column_exists('ai_question_search_documents', 'search_vector'):
            op.add_column(
                'ai_question_search_documents',
                sa.Column(
                    'search_vector',
                    postgresql.TSVECTOR(),
                    sa.Computed("to_tsvector('simple', coalesce(search_text, ''))", persisted=True),
                    nullable=True,
                ),
            )
        op.execute("CREATE INDEX IF NOT EXISTS ix_ai_question_search_vector ON ai_question_search_documents USING gin (search_vector)")
        op.execute("CREATE INDEX IF NOT EXISTS ix_ai_question_search_text_trgm ON ai_question_search_documents USING gin (search_text gin_trgm_ops)")
        op.execute("CREATE INDEX IF NOT EXISTS ix_ai_subjects_code_name_trgm ON ai_subjects USING gin (lower(code || ' ' || name) gin_trgm_ops)")
        op.execute("CREATE INDEX IF NOT EXISTS ix_ai_offerings_code_name_trgm ON ai_subject_offerings USING gin (lower(code || ' ' || coalesce(name, '') || ' ' || coalesce(term, '')) gin_trgm_ops)")
        op.execute("CREATE INDEX IF NOT EXISTS ix_ai_chapters_title_trgm ON ai_subject_chapters USING gin (lower(title || ' ' || coalesce(description, '')) gin_trgm_ops)")
        op.execute("CREATE INDEX IF NOT EXISTS ix_ai_departments_code_name_trgm ON ai_departments USING gin (lower(code || ' ' || name) gin_trgm_ops)")


def downgrade() -> None:
    if _is_postgresql():
        op.execute('DROP INDEX IF EXISTS ix_ai_departments_code_name_trgm')
        op.execute('DROP INDEX IF EXISTS ix_ai_chapters_title_trgm')
        op.execute('DROP INDEX IF EXISTS ix_ai_offerings_code_name_trgm')
        op.execute('DROP INDEX IF EXISTS ix_ai_subjects_code_name_trgm')
        op.execute('DROP INDEX IF EXISTS ix_ai_question_search_vector')
        op.execute('DROP INDEX IF EXISTS ix_ai_question_search_text_trgm')
    op.drop_index('ix_ai_question_search_updated', table_name='ai_question_search_documents')
    op.drop_index('ix_ai_question_search_chapter_difficulty', table_name='ai_question_search_documents')
    op.drop_index('ix_ai_question_search_subject_chapter_status', table_name='ai_question_search_documents')
    op.drop_index('ix_ai_question_search_bank_status', table_name='ai_question_search_documents')
    op.drop_index('ix_ai_question_search_family', table_name='ai_question_search_documents')
    op.drop_index('ix_ai_question_search_difficulty', table_name='ai_question_search_documents')
    op.drop_index('ix_ai_question_search_status', table_name='ai_question_search_documents')
    op.drop_index('ix_ai_question_search_chapter', table_name='ai_question_search_documents')
    op.drop_index('ix_ai_question_search_offering', table_name='ai_question_search_documents')
    op.drop_index('ix_ai_question_search_subject', table_name='ai_question_search_documents')
    op.drop_index('ix_ai_question_search_bank_version', table_name='ai_question_search_documents')
    op.drop_table('ai_question_search_documents')
