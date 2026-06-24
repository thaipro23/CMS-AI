"""v25.9.15.6.34 dashboard summary engine

Revision ID: 0017_v25_9_15_6_34
Revises: 0016_v25_9_15_6_33
Create Date: 2026-06-15

Adds ai_bank_chapter_stats, the per-chapter summary table used by Bank
Dashboard so request-time dashboard reads no longer aggregate ai_questions.
Initial population is intentionally done by the admin rebuild endpoint after
deploy, because production datasets may be large and operators should control
when the one-time ai_questions scan happens.
"""

from alembic import op
import sqlalchemy as sa


revision = '0017_v25_9_15_6_34'
down_revision = '0016_v25_9_15_6_33'
branch_labels = None
depends_on = None


def _table_exists(name: str) -> bool:
    return sa.inspect(op.get_bind()).has_table(name)


def _index_exists(table: str, name: str) -> bool:
    if not _table_exists(table):
        return False
    return any(item.get('name') == name for item in sa.inspect(op.get_bind()).get_indexes(table))


def _create_index_if_missing(name: str, table: str, columns: list[str]) -> None:
    if not _index_exists(table, name):
        op.create_index(name, table, columns)


def upgrade() -> None:
    if not _table_exists('ai_bank_chapter_stats'):
        op.create_table(
            'ai_bank_chapter_stats',
            sa.Column('chapter_id', sa.String(), sa.ForeignKey('ai_subject_chapters.id'), primary_key=True),
            sa.Column('subject_id', sa.String(), sa.ForeignKey('ai_subjects.id'), nullable=False),
            sa.Column('subject_offering_id', sa.String(), sa.ForeignKey('ai_subject_offerings.id'), nullable=True),
            sa.Column('latest_bank_version_id', sa.String(), sa.ForeignKey('ai_question_bank_versions.id'), nullable=True),
            sa.Column('total_questions', sa.Integer(), nullable=False, server_default='0'),
            sa.Column('approved_count', sa.Integer(), nullable=False, server_default='0'),
            sa.Column('pending_review_count', sa.Integer(), nullable=False, server_default='0'),
            sa.Column('draft_error_count', sa.Integer(), nullable=False, server_default='0'),
            sa.Column('rejected_count', sa.Integer(), nullable=False, server_default='0'),
            sa.Column('retired_count', sa.Integer(), nullable=False, server_default='0'),
            sa.Column('duplicate_count', sa.Integer(), nullable=False, server_default='0'),
            sa.Column('easy_count', sa.Integer(), nullable=False, server_default='0'),
            sa.Column('medium_count', sa.Integer(), nullable=False, server_default='0'),
            sa.Column('hard_count', sa.Integer(), nullable=False, server_default='0'),
            sa.Column('family_count', sa.Integer(), nullable=False, server_default='0'),
            sa.Column('material_count', sa.Integer(), nullable=False, server_default='0'),
            sa.Column('release_count', sa.Integer(), nullable=False, server_default='0'),
            sa.Column('published_release_count', sa.Integer(), nullable=False, server_default='0'),
            sa.Column('ready_to_release', sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column('unresolved_count', sa.Integer(), nullable=False, server_default='0'),
            sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        )
    _create_index_if_missing('ix_ai_bank_chapter_stats_subject', 'ai_bank_chapter_stats', ['subject_id'])
    _create_index_if_missing('ix_ai_bank_chapter_stats_offering', 'ai_bank_chapter_stats', ['subject_offering_id'])
    _create_index_if_missing('ix_ai_bank_chapter_stats_latest_bank', 'ai_bank_chapter_stats', ['latest_bank_version_id'])
    _create_index_if_missing('ix_ai_bank_chapter_stats_ready', 'ai_bank_chapter_stats', ['ready_to_release'])
    _create_index_if_missing('ix_ai_bank_chapter_stats_updated', 'ai_bank_chapter_stats', ['updated_at'])
    _create_index_if_missing('ix_ai_bank_chapter_stats_subject_unresolved', 'ai_bank_chapter_stats', ['subject_id', 'unresolved_count'])
    _create_index_if_missing('ix_ai_bank_chapter_stats_offering_ready', 'ai_bank_chapter_stats', ['subject_offering_id', 'ready_to_release'])


def downgrade() -> None:
    op.drop_index('ix_ai_bank_chapter_stats_offering_ready', table_name='ai_bank_chapter_stats')
    op.drop_index('ix_ai_bank_chapter_stats_subject_unresolved', table_name='ai_bank_chapter_stats')
    op.drop_index('ix_ai_bank_chapter_stats_updated', table_name='ai_bank_chapter_stats')
    op.drop_index('ix_ai_bank_chapter_stats_ready', table_name='ai_bank_chapter_stats')
    op.drop_index('ix_ai_bank_chapter_stats_latest_bank', table_name='ai_bank_chapter_stats')
    op.drop_index('ix_ai_bank_chapter_stats_offering', table_name='ai_bank_chapter_stats')
    op.drop_index('ix_ai_bank_chapter_stats_subject', table_name='ai_bank_chapter_stats')
    op.drop_table('ai_bank_chapter_stats')
