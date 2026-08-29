"""Add canonical Question authoring schema and prompt media.

Revision ID: 0060_v25_9_16_7_2_64_38
Revises: 0059_v25_9_16_7_2_64_37
"""
from alembic import op
import sqlalchemy as sa

revision = '0060_v25_9_16_7_2_64_38'
down_revision = '0059_v25_9_16_7_2_64_37'
branch_labels = None
depends_on = None


def _columns(inspector: sa.Inspector, table_name: str) -> set[str]:
    return {str(column.get('name')) for column in inspector.get_columns(table_name)}


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if inspector.has_table('ai_questions'):
        cols = _columns(inspector, 'ai_questions')
        with op.batch_alter_table('ai_questions') as batch:
            if 'question_schema_version' not in cols:
                batch.add_column(sa.Column('question_schema_version', sa.Integer(), nullable=False, server_default='1'))
            if 'authoring_mode' not in cols:
                batch.add_column(sa.Column('authoring_mode', sa.String(length=50), nullable=False, server_default='ai'))
            if 'created_by' not in cols:
                batch.add_column(sa.Column('created_by', sa.String(length=255), nullable=True))
            if 'question_content_json' not in cols:
                batch.add_column(sa.Column('question_content_json', sa.JSON(), nullable=True))
        inspector = sa.inspect(bind)
        indexes = {str(item.get('name')) for item in inspector.get_indexes('ai_questions')}
        if 'ix_ai_questions_authoring_mode' not in indexes:
            op.create_index('ix_ai_questions_authoring_mode', 'ai_questions', ['authoring_mode'])
        if 'ix_ai_questions_created_by' not in indexes:
            op.create_index('ix_ai_questions_created_by', 'ai_questions', ['created_by'])

    inspector = sa.inspect(bind)
    if not inspector.has_table('ai_question_media'):
        op.create_table(
            'ai_question_media',
            sa.Column('id', sa.String(), nullable=False),
            sa.Column('question_id', sa.String(), nullable=False),
            sa.Column('bank_version_id', sa.String(), nullable=True),
            sa.Column('media_role', sa.String(length=50), nullable=False, server_default='prompt_image'),
            sa.Column('storage_reference', sa.String(length=2048), nullable=False),
            sa.Column('file_name', sa.String(length=512), nullable=False),
            sa.Column('mime_type', sa.String(length=100), nullable=False),
            sa.Column('size_bytes', sa.Integer(), nullable=False),
            sa.Column('sha256', sa.String(length=64), nullable=False),
            sa.Column('width', sa.Integer(), nullable=True),
            sa.Column('height', sa.Integer(), nullable=True),
            sa.Column('alt_text', sa.String(length=500), nullable=False),
            sa.Column('sort_order', sa.Integer(), nullable=False, server_default='0'),
            sa.Column('created_by', sa.String(length=255), nullable=True),
            sa.Column('created_at', sa.DateTime(), nullable=False),
            sa.Column('updated_at', sa.DateTime(), nullable=False),
            sa.ForeignKeyConstraint(['question_id'], ['ai_questions.id'], ondelete='CASCADE'),
            sa.ForeignKeyConstraint(['bank_version_id'], ['ai_question_bank_versions.id'], ondelete='CASCADE'),
            sa.PrimaryKeyConstraint('id'),
        )
        op.create_index('ix_ai_question_media_question_id', 'ai_question_media', ['question_id'])
        op.create_index('ix_ai_question_media_bank_version_id', 'ai_question_media', ['bank_version_id'])
        op.create_index('ix_ai_question_media_media_role', 'ai_question_media', ['media_role'])
        op.create_index('ix_ai_question_media_sha256', 'ai_question_media', ['sha256'])
        op.create_index('ix_ai_question_media_question_order', 'ai_question_media', ['question_id', 'sort_order', 'created_at'])
        op.create_index('ix_ai_question_media_bank_question', 'ai_question_media', ['bank_version_id', 'question_id'])


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if inspector.has_table('ai_question_media'):
        op.drop_table('ai_question_media')
    inspector = sa.inspect(bind)
    if inspector.has_table('ai_questions'):
        indexes = {str(item.get('name')) for item in inspector.get_indexes('ai_questions')}
        if 'ix_ai_questions_created_by' in indexes:
            op.drop_index('ix_ai_questions_created_by', table_name='ai_questions')
        if 'ix_ai_questions_authoring_mode' in indexes:
            op.drop_index('ix_ai_questions_authoring_mode', table_name='ai_questions')
        cols = _columns(sa.inspect(bind), 'ai_questions')
        with op.batch_alter_table('ai_questions') as batch:
            for name in ('question_content_json', 'created_by', 'authoring_mode', 'question_schema_version'):
                if name in cols:
                    batch.drop_column(name)
