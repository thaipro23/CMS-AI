"""v25.9.16.5.57 training policy deadlines and assignment defense scores

Revision ID: 0046_v25_9_16_5_57_training_policy
Revises: 0045_v25_9_16_5_22_auto_retire
Create Date: 2026-06-29
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = '0046_v25_9_16_5_57_training_policy'
down_revision = '0045_v25_9_16_5_22_auto_retire'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'academic_quiz_deadline_overrides',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('class_id', sa.String(), nullable=False),
        sa.Column('course_id', sa.String(length=255), nullable=True),
        sa.Column('component_key', sa.String(length=512), nullable=True),
        sa.Column('component_label', sa.String(length=255), nullable=False, server_default=''),
        sa.Column('quiz_number', sa.Integer(), nullable=True),
        sa.Column('start_date', sa.DateTime(), nullable=True),
        sa.Column('deadline_date', sa.DateTime(), nullable=True),
        sa.Column('reason', sa.Text(), nullable=False, server_default=''),
        sa.Column('created_by', sa.String(length=255), nullable=True),
        sa.Column('updated_by', sa.String(length=255), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('metadata_json', sa.JSON(), nullable=True),
        sa.ForeignKeyConstraint(['class_id'], ['academic_classes.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('class_id', 'course_id', 'quiz_number', name='uq_academic_quiz_deadline_class_course_number'),
    )
    op.create_index('ix_academic_quiz_deadline_class_course', 'academic_quiz_deadline_overrides', ['class_id', 'course_id', 'quiz_number'])
    op.create_index(op.f('ix_academic_quiz_deadline_overrides_class_id'), 'academic_quiz_deadline_overrides', ['class_id'])
    op.create_index(op.f('ix_academic_quiz_deadline_overrides_component_key'), 'academic_quiz_deadline_overrides', ['component_key'])
    op.create_index(op.f('ix_academic_quiz_deadline_overrides_course_id'), 'academic_quiz_deadline_overrides', ['course_id'])
    op.create_index(op.f('ix_academic_quiz_deadline_overrides_created_by'), 'academic_quiz_deadline_overrides', ['created_by'])
    op.create_index(op.f('ix_academic_quiz_deadline_overrides_quiz_number'), 'academic_quiz_deadline_overrides', ['quiz_number'])
    op.create_index(op.f('ix_academic_quiz_deadline_overrides_updated_by'), 'academic_quiz_deadline_overrides', ['updated_by'])

    op.create_table(
        'academic_assignment_defense_scores',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('class_id', sa.String(), nullable=False),
        sa.Column('student_id', sa.String(), nullable=False),
        sa.Column('course_id', sa.String(length=255), nullable=True),
        sa.Column('assignment_key', sa.String(length=512), nullable=True),
        sa.Column('assignment_label', sa.String(length=255), nullable=False, server_default='Assignment'),
        sa.Column('score_10', sa.Float(), nullable=True),
        sa.Column('defense_status', sa.String(length=50), nullable=False, server_default='not_graded'),
        sa.Column('graded_by', sa.String(length=255), nullable=True),
        sa.Column('graded_at', sa.DateTime(), nullable=True),
        sa.Column('note', sa.Text(), nullable=False, server_default=''),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('metadata_json', sa.JSON(), nullable=True),
        sa.ForeignKeyConstraint(['class_id'], ['academic_classes.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['student_id'], ['academic_students.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('class_id', 'student_id', 'course_id', 'assignment_key', name='uq_academic_assignment_defense_class_student_key'),
    )
    op.create_index('ix_academic_assignment_defense_class_student', 'academic_assignment_defense_scores', ['class_id', 'student_id'])
    op.create_index(op.f('ix_academic_assignment_defense_scores_assignment_key'), 'academic_assignment_defense_scores', ['assignment_key'])
    op.create_index(op.f('ix_academic_assignment_defense_scores_class_id'), 'academic_assignment_defense_scores', ['class_id'])
    op.create_index(op.f('ix_academic_assignment_defense_scores_course_id'), 'academic_assignment_defense_scores', ['course_id'])
    op.create_index(op.f('ix_academic_assignment_defense_scores_defense_status'), 'academic_assignment_defense_scores', ['defense_status'])
    op.create_index(op.f('ix_academic_assignment_defense_scores_graded_at'), 'academic_assignment_defense_scores', ['graded_at'])
    op.create_index(op.f('ix_academic_assignment_defense_scores_graded_by'), 'academic_assignment_defense_scores', ['graded_by'])
    op.create_index(op.f('ix_academic_assignment_defense_scores_student_id'), 'academic_assignment_defense_scores', ['student_id'])


def downgrade() -> None:
    op.drop_index(op.f('ix_academic_assignment_defense_scores_student_id'), table_name='academic_assignment_defense_scores')
    op.drop_index(op.f('ix_academic_assignment_defense_scores_graded_by'), table_name='academic_assignment_defense_scores')
    op.drop_index(op.f('ix_academic_assignment_defense_scores_graded_at'), table_name='academic_assignment_defense_scores')
    op.drop_index(op.f('ix_academic_assignment_defense_scores_defense_status'), table_name='academic_assignment_defense_scores')
    op.drop_index(op.f('ix_academic_assignment_defense_scores_course_id'), table_name='academic_assignment_defense_scores')
    op.drop_index(op.f('ix_academic_assignment_defense_scores_class_id'), table_name='academic_assignment_defense_scores')
    op.drop_index(op.f('ix_academic_assignment_defense_scores_assignment_key'), table_name='academic_assignment_defense_scores')
    op.drop_index('ix_academic_assignment_defense_class_student', table_name='academic_assignment_defense_scores')
    op.drop_table('academic_assignment_defense_scores')
    op.drop_index(op.f('ix_academic_quiz_deadline_overrides_updated_by'), table_name='academic_quiz_deadline_overrides')
    op.drop_index(op.f('ix_academic_quiz_deadline_overrides_quiz_number'), table_name='academic_quiz_deadline_overrides')
    op.drop_index(op.f('ix_academic_quiz_deadline_overrides_created_by'), table_name='academic_quiz_deadline_overrides')
    op.drop_index(op.f('ix_academic_quiz_deadline_overrides_course_id'), table_name='academic_quiz_deadline_overrides')
    op.drop_index(op.f('ix_academic_quiz_deadline_overrides_component_key'), table_name='academic_quiz_deadline_overrides')
    op.drop_index(op.f('ix_academic_quiz_deadline_overrides_class_id'), table_name='academic_quiz_deadline_overrides')
    op.drop_index('ix_academic_quiz_deadline_class_course', table_name='academic_quiz_deadline_overrides')
    op.drop_table('academic_quiz_deadline_overrides')
