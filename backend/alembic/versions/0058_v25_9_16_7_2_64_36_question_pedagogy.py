"""Add compact pedagogical metadata for native Open edX hints/feedback.

Revision ID: 0058_v25_9_16_7_2_64_36
Revises: 0057_v25_9_16_7_2_64_35

No Open edX core changes. Existing questions remain valid with null/empty metadata;
the exporter provides deterministic fallbacks for them.
"""
from alembic import op
import sqlalchemy as sa

revision = '0058_v25_9_16_7_2_64_36'
down_revision = '0057_v25_9_16_7_2_64_35'
branch_labels = None
depends_on = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if not inspector.has_table('ai_questions'):
        return
    columns = {column.get('name') for column in inspector.get_columns('ai_questions')}
    if 'pedagogy_json' not in columns:
        op.add_column('ai_questions', sa.Column('pedagogy_json', sa.JSON(), nullable=True))


def downgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if not inspector.has_table('ai_questions'):
        return
    columns = {column.get('name') for column in inspector.get_columns('ai_questions')}
    if 'pedagogy_json' in columns:
        op.drop_column('ai_questions', 'pedagogy_json')
