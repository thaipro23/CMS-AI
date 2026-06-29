"""v25.9.16.5.58 training policy correctness hardening

Revision ID: 0047_v25_9_16_5_58_training_policy_hardening
Revises: 0046_v25_9_16_5_57_training_policy
Create Date: 2026-06-29
"""
from __future__ import annotations

from alembic import op

revision = '0047_v25_9_16_5_58_training_policy_hardening'
down_revision = '0046_v25_9_16_5_57_training_policy'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Remove possible duplicates allowed by PostgreSQL NULL semantics before adding expression unique indexes.
    op.execute(
        """
        DELETE FROM academic_quiz_deadline_overrides a
        USING academic_quiz_deadline_overrides b
        WHERE a.class_id = b.class_id
          AND COALESCE(a.course_id, '') = COALESCE(b.course_id, '')
          AND a.quiz_number IS NOT DISTINCT FROM b.quiz_number
          AND a.id <> b.id
          AND (COALESCE(a.updated_at, a.created_at) < COALESCE(b.updated_at, b.created_at) OR (COALESCE(a.updated_at, a.created_at) = COALESCE(b.updated_at, b.created_at) AND a.id < b.id))
        """
    )
    op.execute(
        """
        DELETE FROM academic_assignment_defense_scores a
        USING academic_assignment_defense_scores b
        WHERE a.class_id = b.class_id
          AND a.student_id = b.student_id
          AND COALESCE(a.course_id, '') = COALESCE(b.course_id, '')
          AND COALESCE(a.assignment_key, '') = COALESCE(b.assignment_key, '')
          AND a.id <> b.id
          AND (COALESCE(a.updated_at, a.created_at) < COALESCE(b.updated_at, b.created_at) OR (COALESCE(a.updated_at, a.created_at) = COALESCE(b.updated_at, b.created_at) AND a.id < b.id))
        """
    )

    op.drop_constraint('uq_academic_quiz_deadline_class_course_number', 'academic_quiz_deadline_overrides', type_='unique')
    op.drop_constraint('uq_academic_assignment_defense_class_student_key', 'academic_assignment_defense_scores', type_='unique')

    op.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS uq_academic_quiz_deadline_class_course_number_v2
        ON academic_quiz_deadline_overrides (class_id, COALESCE(course_id, ''), quiz_number)
        WHERE quiz_number IS NOT NULL
        """
    )
    op.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS uq_academic_assignment_defense_class_student_key_v2
        ON academic_assignment_defense_scores (class_id, student_id, COALESCE(course_id, ''), COALESCE(assignment_key, ''))
        """
    )


def downgrade() -> None:
    op.execute('DROP INDEX IF EXISTS uq_academic_assignment_defense_class_student_key_v2')
    op.execute('DROP INDEX IF EXISTS uq_academic_quiz_deadline_class_course_number_v2')
    op.create_unique_constraint(
        'uq_academic_quiz_deadline_class_course_number',
        'academic_quiz_deadline_overrides',
        ['class_id', 'course_id', 'quiz_number'],
    )
    op.create_unique_constraint(
        'uq_academic_assignment_defense_class_student_key',
        'academic_assignment_defense_scores',
        ['class_id', 'student_id', 'course_id', 'assignment_key'],
    )
