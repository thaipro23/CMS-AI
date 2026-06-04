"""v25.9.14.1 question family id

Revision ID: 0007_v25_9_14_1
Revises: 0006_v25_9_14_0
Create Date: 2026-06-04
"""
from alembic import op
import sqlalchemy as sa

revision = '0007_v25_9_14_1'
down_revision = '0006_v25_9_14_0'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('ai_questions', sa.Column('question_family_id', sa.String(length=255), nullable=True))
    op.add_column('ai_questions', sa.Column('variant_no', sa.Integer(), nullable=True))
    op.add_column('ai_questions', sa.Column('source_evidence', sa.Text(), server_default='', nullable=True))
    op.create_index('ix_ai_questions_course_family_status', 'ai_questions', ['course_id', 'question_family_id', 'status'])


def downgrade() -> None:
    op.drop_index('ix_ai_questions_course_family_status', table_name='ai_questions')
    op.drop_column('ai_questions', 'source_evidence')
    op.drop_column('ai_questions', 'variant_no')
    op.drop_column('ai_questions', 'question_family_id')
