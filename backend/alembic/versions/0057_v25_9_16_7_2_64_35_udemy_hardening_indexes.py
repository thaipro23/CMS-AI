"""Add query indexes for Batch 35 Udemy production hardening.

Revision ID: 0057_v25_9_16_7_2_64_35
Revises: 0056_v25_9_16_7_2_64_33

This migration changes indexes only. It does not transfer or transform any
legacy ACMS data.
"""
from alembic import op
import sqlalchemy as sa

revision = '0057_v25_9_16_7_2_64_35'
down_revision = '0056_v25_9_16_7_2_64_33'
branch_labels = None
depends_on = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    existing = {
        idx.get('name')
        for idx in inspector.get_indexes('udemy_student_progress')
    } if inspector.has_table('udemy_student_progress') else set()
    indexes = [
        ('ix_udemy_student_progress_delivery_class', ['subject_delivery_id', 'class_id']),
        ('ix_udemy_student_progress_delivery_match_progress', ['subject_delivery_id', 'match_status', 'progress_percent']),
        ('ix_udemy_student_progress_delivery_imported', ['subject_delivery_id', 'last_imported_at']),
    ]
    for name, columns in indexes:
        if name not in existing:
            op.create_index(name, 'udemy_student_progress', columns)


def downgrade() -> None:
    op.execute('DROP INDEX IF EXISTS ix_udemy_student_progress_delivery_imported')
    op.execute('DROP INDEX IF EXISTS ix_udemy_student_progress_delivery_match_progress')
    op.execute('DROP INDEX IF EXISTS ix_udemy_student_progress_delivery_class')
