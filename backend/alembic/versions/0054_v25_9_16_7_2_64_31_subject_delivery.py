"""Add term/block subject delivery platform selection.

Revision ID: 0054_v25_9_16_7_2_64_31
Revises: 0053_v25_9_16_7_2_64_16_5_4
"""
from alembic import op
import sqlalchemy as sa

revision = '0054_v25_9_16_7_2_64_31'
down_revision = '0053_v25_9_16_7_2_64_16_5_4'
branch_labels = None
depends_on = None


def upgrade() -> None:
    if sa.inspect(op.get_bind()).has_table('academic_subject_deliveries'):
        return
    op.create_table(
        'academic_subject_deliveries',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('subject_id', sa.String(), nullable=False),
        sa.Column('term_id', sa.String(), nullable=False),
        sa.Column('block_id', sa.String(), nullable=False),
        sa.Column('branch', sa.String(length=64), nullable=False),
        sa.Column('learning_platform', sa.String(length=32), nullable=True),
        sa.Column('active', sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column('configuration_source', sa.String(length=50), nullable=False, server_default='manual'),
        sa.Column('configured_by', sa.String(length=255), nullable=True),
        sa.Column('configured_at', sa.DateTime(), nullable=True),
        sa.Column('catalog_refreshed_at', sa.DateTime(), nullable=True),
        sa.Column('metadata_json', sa.JSON(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.ForeignKeyConstraint(['subject_id'], ['academic_subjects.id']),
        sa.ForeignKeyConstraint(['term_id'], ['academic_terms.id']),
        sa.ForeignKeyConstraint(['block_id'], ['academic_blocks.id']),
        sa.CheckConstraint("learning_platform IS NULL OR learning_platform IN ('cms', 'udemy')", name='ck_academic_subject_delivery_platform'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('subject_id', 'term_id', 'block_id', 'branch', name='uq_academic_subject_delivery_scope'),
    )
    op.create_index('ix_academic_subject_deliveries_subject_id', 'academic_subject_deliveries', ['subject_id'])
    op.create_index('ix_academic_subject_deliveries_term_id', 'academic_subject_deliveries', ['term_id'])
    op.create_index('ix_academic_subject_deliveries_block_id', 'academic_subject_deliveries', ['block_id'])
    op.create_index('ix_academic_subject_deliveries_branch', 'academic_subject_deliveries', ['branch'])
    op.create_index('ix_academic_subject_deliveries_learning_platform', 'academic_subject_deliveries', ['learning_platform'])
    op.create_index('ix_academic_subject_deliveries_active', 'academic_subject_deliveries', ['active'])
    op.create_index('ix_academic_subject_deliveries_configuration_source', 'academic_subject_deliveries', ['configuration_source'])
    op.create_index('ix_academic_subject_deliveries_configured_by', 'academic_subject_deliveries', ['configured_by'])
    op.create_index('ix_academic_subject_deliveries_configured_at', 'academic_subject_deliveries', ['configured_at'])
    op.create_index('ix_academic_subject_deliveries_catalog_refreshed_at', 'academic_subject_deliveries', ['catalog_refreshed_at'])
    op.create_index('ix_academic_subject_delivery_scope_active', 'academic_subject_deliveries', ['term_id', 'block_id', 'branch', 'active'])
    op.create_index('ix_academic_subject_delivery_platform_scope', 'academic_subject_deliveries', ['learning_platform', 'term_id', 'block_id', 'branch'])


def downgrade() -> None:
    op.execute('DROP TABLE IF EXISTS academic_subject_deliveries CASCADE')
