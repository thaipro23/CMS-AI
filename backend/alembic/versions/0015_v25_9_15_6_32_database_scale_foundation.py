"""v25.9.15.6.32 database scale foundation

Revision ID: 0015_v25_9_15_6_32
Revises: 0014_v25_9_15_6_31_13
Create Date: 2026-06-12

Adds the composite indexes required before scaling Bank Manager to:
- 6 departments
- 300 subjects
- 1,500 subject versions
- 15,000 chapters
- 1,500,000 questions

PostgreSQL uses CREATE INDEX CONCURRENTLY in an autocommit block so production
reads/writes are not blocked by long index builds. Other DBs fall back to normal
CREATE INDEX IF NOT EXISTS for dev/test compatibility.
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = '0015_v25_9_15_6_32'
down_revision = '0014_v25_9_15_6_31_13'
branch_labels = None
depends_on = None

# name, table, columns/expression SQL, note
INDEXES: list[tuple[str, str, str, str]] = [
    (
        'ix_ai_questions_bank_status_created_id',
        'ai_questions',
        '(bank_version_id, status, created_at DESC, id DESC)',
        'Chapter question list by bank/status with keyset ordering.',
    ),
    (
        'ix_ai_questions_bank_difficulty_status_retired',
        'ai_questions',
        '(bank_version_id, difficulty, status, is_retired)',
        'Difficulty/status counters and release validation without table scan.',
    ),
    (
        'ix_ai_questions_bank_family_difficulty',
        'ai_questions',
        '(bank_version_id, question_family_id, difficulty)',
        'Quiz slot planning and duplicate-family balancing.',
    ),
    (
        'ix_ai_questions_chapter_status_created',
        'ai_questions',
        '(subject_chapter_id, status, created_at DESC, id DESC)',
        'Chapter-scoped review queue and latest-question feed.',
    ),
    (
        'ix_ai_questions_release_difficulty',
        'ai_questions',
        '(bank_release_id, difficulty)',
        'Release composition validation by difficulty.',
    ),
    (
        'ix_ai_bank_versions_offering_chapter_status',
        'ai_question_bank_versions',
        '(subject_offering_id, chapter_id, status)',
        'Find latest/mutable bank version for a chapter inside a subject version.',
    ),
    (
        'ix_ai_releases_bank_status_created',
        'ai_question_bank_releases',
        '(bank_version_id, status, created_at DESC)',
        'Release list/history for a bank version.',
    ),
    (
        'ix_ai_release_questions_release_difficulty',
        'ai_bank_release_questions',
        '(bank_release_id, difficulty)',
        'Released question counts per difficulty.',
    ),
    (
        'ix_ai_material_chunks_bank_chunk',
        'ai_material_chunks',
        '(bank_version_id, material_version_id, chunk_index)',
        'Material chunk browser and generation source lookup.',
    ),
    # Safe extras still inside Database Scale Foundation: these are small but
    # common Bank hierarchy/list/history access paths and do not change behavior.
    (
        'ix_ai_subject_offerings_subject_status_created',
        'ai_subject_offerings',
        '(subject_id, status, created_at DESC, id DESC)',
        'Subject version list per subject.',
    ),
    (
        'ix_ai_subject_chapters_offering_status_order',
        'ai_subject_chapters',
        '(subject_offering_id, status, sort_order, id)',
        'Chapter list per subject version without sorting all chapters.',
    ),
    (
        'ix_ai_course_quiz_instances_release_status_created',
        'ai_course_quiz_instances',
        '(bank_release_id, status, created_at DESC)',
        'Quiz history by release/status.',
    ),
    (
        'ix_ai_course_quiz_instances_course_status_created',
        'ai_course_quiz_instances',
        '(openedx_course_id, status, created_at DESC)',
        'Quiz history by Open edX course.',
    ),
    (
        'ix_ai_audit_logs_actor_status_created',
        'ai_audit_logs',
        '(actor_id, status, created_at DESC)',
        'Teacher/user activity tracking page.',
    ),
    (
        'ix_ai_audit_logs_target_created',
        'ai_audit_logs',
        '(target_type, target_id, created_at DESC)',
        'Audit drill-down by bank/release/quiz target.',
    ),
]


def _table_exists(bind, table_name: str) -> bool:
    return sa.inspect(bind).has_table(table_name)


def _index_exists(bind, table_name: str, index_name: str) -> bool:
    if not _table_exists(bind, table_name):
        return False
    return any(item.get('name') == index_name for item in sa.inspect(bind).get_indexes(table_name))


def _create_index_sql(bind, name: str, table: str, expr: str) -> str:
    if bind.dialect.name == 'postgresql':
        return f'CREATE INDEX CONCURRENTLY IF NOT EXISTS {name} ON {table} {expr}'
    return f'CREATE INDEX IF NOT EXISTS {name} ON {table} {expr}'


def _drop_index_sql(bind, name: str) -> str:
    if bind.dialect.name == 'postgresql':
        return f'DROP INDEX CONCURRENTLY IF EXISTS {name}'
    return f'DROP INDEX IF EXISTS {name}'


def upgrade() -> None:
    bind = op.get_bind()
    statements: list[str] = []
    for name, table, expr, _note in INDEXES:
        if _table_exists(bind, table) and not _index_exists(bind, table, name):
            statements.append(_create_index_sql(bind, name, table, expr))

    if not statements:
        return

    if bind.dialect.name == 'postgresql':
        # CREATE INDEX CONCURRENTLY must be executed outside a transaction.
        with op.get_context().autocommit_block():
            for statement in statements:
                op.execute(statement)
    else:
        for statement in statements:
            op.execute(statement)


def downgrade() -> None:
    bind = op.get_bind()
    statements = [_drop_index_sql(bind, name) for name, _table, _expr, _note in reversed(INDEXES)]
    if bind.dialect.name == 'postgresql':
        with op.get_context().autocommit_block():
            for statement in statements:
                op.execute(statement)
    else:
        for statement in statements:
            op.execute(statement)
