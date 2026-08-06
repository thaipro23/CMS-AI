"""Add query indexes for Batch 35 Udemy production hardening.

Revision ID: 0057_v25_9_16_7_2_64_35
Revises: 0056_v25_9_16_7_2_64_33

This migration changes indexes only. It does not transfer or transform any
legacy ACMS data.
"""
from alembic import op

revision = '0057_v25_9_16_7_2_64_35'
down_revision = '0056_v25_9_16_7_2_64_33'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index(
        'ix_udemy_student_progress_delivery_class',
        'udemy_student_progress',
        ['subject_delivery_id', 'class_id'],
    )
    op.create_index(
        'ix_udemy_student_progress_delivery_match_progress',
        'udemy_student_progress',
        ['subject_delivery_id', 'match_status', 'progress_percent'],
    )
    op.create_index(
        'ix_udemy_student_progress_delivery_imported',
        'udemy_student_progress',
        ['subject_delivery_id', 'last_imported_at'],
    )


def downgrade() -> None:
    op.drop_index('ix_udemy_student_progress_delivery_imported', table_name='udemy_student_progress')
    op.drop_index('ix_udemy_student_progress_delivery_match_progress', table_name='udemy_student_progress')
    op.drop_index('ix_udemy_student_progress_delivery_class', table_name='udemy_student_progress')
