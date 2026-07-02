"""v25.9.16.7.2.12 class identity includes campus and branch

Revision ID: 0050_v25_9_16_7_2_12_class_scope
Revises: 0049_v25_9_16_6_3
Create Date: 2026-07-02
"""

from alembic import op

revision = '0050_v25_9_16_7_2_12_class_scope'
down_revision = '0049_v25_9_16_6_3'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Old identity was term + block + subject + class_code. That is too narrow:
    # AP can return the same visible class code/name in another campus/branch.
    # Dropping this constraint is required before a clean AP resync; otherwise
    # distinct classes from another campus are merged/skipped or rejected.
    op.execute('ALTER TABLE academic_classes DROP CONSTRAINT IF EXISTS uq_academic_classes_term_block_subject_code')
    op.execute('DROP INDEX IF EXISTS uq_academic_classes_active_scope_code')
    op.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS uq_academic_classes_active_scope_code
        ON academic_classes (
            term_id,
            COALESCE(block_id, ''),
            subject_id,
            class_code,
            COALESCE(campus, ''),
            COALESCE(branch, '')
        )
        WHERE active IS TRUE
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_academic_classes_scope_lookup
        ON academic_classes (branch, campus, term_id, block_id, subject_id, class_code, active)
        """
    )


def downgrade() -> None:
    # Downgrade can fail if production already contains the now-valid case of the
    # same class_code under multiple campuses. Do not downgrade this migration on
    # production data; keep this only for local test reversibility.
    op.execute('DROP INDEX IF EXISTS ix_academic_classes_scope_lookup')
    op.execute('DROP INDEX IF EXISTS uq_academic_classes_active_scope_code')
    op.create_unique_constraint(
        'uq_academic_classes_term_block_subject_code',
        'academic_classes',
        ['term_id', 'block_id', 'subject_id', 'class_code'],
    )
