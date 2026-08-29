"""Normalize legacy Question Bank rows and keep publish/review state safe.

Revision ID: 0059_v25_9_16_7_2_64_37
Revises: 0058_v25_9_16_7_2_64_36

This migration is deliberately non-destructive: it does not delete questions,
reviews, releases, or search documents. It only canonicalizes legacy status/default
values that can break review transactions or make readiness statistics lie.
"""
from alembic import op
import sqlalchemy as sa

revision = '0059_v25_9_16_7_2_64_37'
down_revision = '0058_v25_9_16_7_2_64_36'
branch_labels = None
depends_on = None


_PUBLISHED_LIFECYCLE = (
    'published',
    'verified',
    'success',
    'published_with_tag_warning',
    'published_ok_stale_verify',
)


def _columns(inspector: sa.Inspector, table_name: str) -> set[str]:
    return {str(column.get('name')) for column in inspector.get_columns(table_name)}


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if inspector.has_table('ai_questions'):
        cols = _columns(inspector, 'ai_questions')

        # Preserve Open edX truth first. Some legacy rows kept review status as
        # approved while publish_status/openedx_publish_status already indicated
        # that the component was published.
        if {'status', 'bank_version_id'}.issubset(cols):
            lifecycle_predicates: list[str] = []
            params: dict[str, object] = {}
            placeholders = ', '.join(f':published_{index}' for index, _ in enumerate(_PUBLISHED_LIFECYCLE))
            for index, value in enumerate(_PUBLISHED_LIFECYCLE):
                params[f'published_{index}'] = value
            if 'openedx_publish_status' in cols:
                lifecycle_predicates.append(f"LOWER(COALESCE(openedx_publish_status, '')) IN ({placeholders})")
            if 'publish_status' in cols:
                lifecycle_predicates.append(f"LOWER(COALESCE(publish_status, '')) IN ({placeholders})")
            if lifecycle_predicates:
                bind.execute(sa.text(
                    "UPDATE ai_questions SET status = 'published' "
                    "WHERE bank_version_id IS NOT NULL "
                    "AND (" + " OR ".join(lifecycle_predicates) + ") "
                    "AND LOWER(TRIM(COALESCE(status, ''))) <> 'published'"
                ), params)

            # Canonical review state for old bank rows that pre-date the
            # Versioned Question Bank workflow. Unknown values not listed here
            # are intentionally left untouched; runtime readiness will block them
            # instead of guessing their meaning.
            bind.execute(sa.text(
                "UPDATE ai_questions SET status = 'pending_review' "
                "WHERE bank_version_id IS NOT NULL "
                "AND (status IS NULL OR TRIM(status) = '' "
                "OR LOWER(TRIM(status)) IN ('draft', 'needs_review', 'generated', 'edited', 'review', 'pending_review'))"
            ))
            bind.execute(sa.text(
                "UPDATE ai_questions SET status = 'draft_error' "
                "WHERE bank_version_id IS NOT NULL AND LOWER(TRIM(COALESCE(status, ''))) IN ('error', 'draft_error')"
            ))
            bind.execute(sa.text(
                "UPDATE ai_questions SET status = 'approved' "
                "WHERE bank_version_id IS NOT NULL AND LOWER(TRIM(COALESCE(status, ''))) = 'approved'"
            ))
            bind.execute(sa.text(
                "UPDATE ai_questions SET status = 'rejected' "
                "WHERE bank_version_id IS NOT NULL AND LOWER(TRIM(COALESCE(status, ''))) = 'rejected'"
            ))
            bind.execute(sa.text(
                "UPDATE ai_questions SET status = 'published' "
                "WHERE bank_version_id IS NOT NULL AND LOWER(TRIM(COALESCE(status, ''))) = 'published'"
            ))

        if 'is_retired' in cols:
            bind.execute(sa.text("UPDATE ai_questions SET is_retired = FALSE WHERE is_retired IS NULL"))
        if 'is_duplicate' in cols:
            bind.execute(sa.text("UPDATE ai_questions SET is_duplicate = FALSE WHERE is_duplicate IS NULL"))
        if 'question_revision_no' in cols:
            bind.execute(sa.text("UPDATE ai_questions SET question_revision_no = 1 WHERE question_revision_no IS NULL OR question_revision_no < 1"))
        if 'repair_attempt_count' in cols:
            bind.execute(sa.text("UPDATE ai_questions SET repair_attempt_count = 0 WHERE repair_attempt_count IS NULL OR repair_attempt_count < 0"))
        if 'openedx_manual_action_required' in cols:
            bind.execute(sa.text("UPDATE ai_questions SET openedx_manual_action_required = FALSE WHERE openedx_manual_action_required IS NULL"))

    if inspector.has_table('ai_question_review_logs'):
        cols = _columns(inspector, 'ai_question_review_logs')
        if 'old_status' in cols:
            bind.execute(sa.text(
                "UPDATE ai_question_review_logs SET old_status = 'legacy_unknown' "
                "WHERE old_status IS NULL OR TRIM(old_status) = ''"
            ))
        if 'new_status' in cols:
            bind.execute(sa.text(
                "UPDATE ai_question_review_logs SET new_status = 'legacy_unknown' "
                "WHERE new_status IS NULL OR TRIM(new_status) = ''"
            ))

    # Search documents are a denormalized cache. Keep their status aligned with
    # the source Question after the repair so UI filters do not continue showing
    # stale needs_review/draft values.
    if inspector.has_table('ai_question_search_documents') and inspector.has_table('ai_questions'):
        doc_cols = _columns(inspector, 'ai_question_search_documents')
        question_cols = _columns(inspector, 'ai_questions')
        if {'question_id', 'status'}.issubset(doc_cols) and {'id', 'status'}.issubset(question_cols):
            bind.execute(sa.text(
                "UPDATE ai_question_search_documents "
                "SET status = (SELECT q.status FROM ai_questions q WHERE q.id = ai_question_search_documents.question_id) "
                "WHERE EXISTS (SELECT 1 FROM ai_questions q "
                "WHERE q.id = ai_question_search_documents.question_id "
                "AND COALESCE(q.status, '') <> COALESCE(ai_question_search_documents.status, ''))"
            ))


def downgrade() -> None:
    # Data normalization is intentionally not reversed. Re-introducing NULL or
    # ambiguous legacy statuses would make review/release behavior unsafe.
    pass
