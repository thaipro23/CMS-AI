"""v25.9.14.0 concept-aware generation

Revision ID: 0006_v25_9_14_0
Revises: 0005_v25_9_13_42
Create Date: 2026-06-04
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = '0006_v25_9_14_0'
down_revision = '0005_v25_9_13_42'
branch_labels = None
depends_on = None


def _json_type():
    return postgresql.JSON(astext_type=sa.Text())


def upgrade() -> None:
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
    op.create_index('ix_ai_concepts_course_node_status', 'ai_concepts', ['course_id', 'source_node_id', 'status'])
    op.create_index('ix_ai_concepts_course_chapter_difficulty', 'ai_concepts', ['course_id', 'chapter_node_id', 'difficulty_hint'])
    op.add_column('ai_questions', sa.Column('concept_id', sa.String(), nullable=True))
    op.add_column('ai_questions', sa.Column('concept_title', sa.String(length=512), nullable=True))
    op.add_column('ai_questions', sa.Column('concept_key', sa.String(length=255), nullable=True))
    op.create_index('ix_ai_questions_course_concept_status', 'ai_questions', ['course_id', 'concept_id', 'status'])


def downgrade() -> None:
    op.drop_index('ix_ai_questions_course_concept_status', table_name='ai_questions')
    op.drop_column('ai_questions', 'concept_key')
    op.drop_column('ai_questions', 'concept_title')
    op.drop_column('ai_questions', 'concept_id')
    op.drop_index('ix_ai_concepts_course_chapter_difficulty', table_name='ai_concepts')
    op.drop_index('ix_ai_concepts_course_node_status', table_name='ai_concepts')
    op.drop_table('ai_concepts')
