"""v25.9.16.3.0 student learning insight snapshots

Revision ID: 0040_v25_9_16_3_0_learning
Revises: 0039_v25_9_16_2_13_terms
Create Date: 2026-06-18
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = '0040_v25_9_16_3_0_learning'
down_revision = '0039_v25_9_16_2_13_terms'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'academic_student_learning_snapshots',
        sa.Column('id', sa.String(), primary_key=True),
        sa.Column('class_id', sa.String(), sa.ForeignKey('academic_classes.id'), nullable=False),
        sa.Column('student_id', sa.String(), sa.ForeignKey('academic_students.id'), nullable=False),
        sa.Column('openedx_course_id', sa.String(length=255), nullable=False),
        sa.Column('openedx_username', sa.String(length=255), nullable=True),
        sa.Column('openedx_user_id', sa.String(length=64), nullable=True),
        sa.Column('enrollment_status', sa.String(length=50), nullable=False, server_default='unknown'),
        sa.Column('enrollment_mode', sa.String(length=50), nullable=True),
        sa.Column('progress_percent', sa.Float(), nullable=True),
        sa.Column('grade_percent', sa.Float(), nullable=True),
        sa.Column('passed', sa.Boolean(), nullable=True),
        sa.Column('completed_blocks', sa.Integer(), nullable=True),
        sa.Column('total_blocks', sa.Integer(), nullable=True),
        sa.Column('last_activity_at', sa.DateTime(), nullable=True),
        sa.Column('raw_json', sa.JSON(), nullable=True),
        sa.Column('last_synced_at', sa.DateTime(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint('class_id', 'student_id', 'openedx_course_id', name='uq_academic_learning_class_student_course'),
    )
    op.create_index('ix_academic_learning_class_course_sync', 'academic_student_learning_snapshots', ['class_id', 'openedx_course_id', 'last_synced_at'])
    op.create_index('ix_academic_learning_status_grade', 'academic_student_learning_snapshots', ['enrollment_status', 'passed', 'grade_percent'])
    op.create_index(op.f('ix_academic_student_learning_snapshots_class_id'), 'academic_student_learning_snapshots', ['class_id'])
    op.create_index(op.f('ix_academic_student_learning_snapshots_student_id'), 'academic_student_learning_snapshots', ['student_id'])
    op.create_index(op.f('ix_academic_student_learning_snapshots_openedx_course_id'), 'academic_student_learning_snapshots', ['openedx_course_id'])
    op.create_index(op.f('ix_academic_student_learning_snapshots_openedx_username'), 'academic_student_learning_snapshots', ['openedx_username'])
    op.create_index(op.f('ix_academic_student_learning_snapshots_openedx_user_id'), 'academic_student_learning_snapshots', ['openedx_user_id'])
    op.create_index(op.f('ix_academic_student_learning_snapshots_enrollment_status'), 'academic_student_learning_snapshots', ['enrollment_status'])
    op.create_index(op.f('ix_academic_student_learning_snapshots_last_activity_at'), 'academic_student_learning_snapshots', ['last_activity_at'])
    op.create_index(op.f('ix_academic_student_learning_snapshots_last_synced_at'), 'academic_student_learning_snapshots', ['last_synced_at'])


def downgrade() -> None:
    op.drop_index(op.f('ix_academic_student_learning_snapshots_last_synced_at'), table_name='academic_student_learning_snapshots')
    op.drop_index(op.f('ix_academic_student_learning_snapshots_last_activity_at'), table_name='academic_student_learning_snapshots')
    op.drop_index(op.f('ix_academic_student_learning_snapshots_enrollment_status'), table_name='academic_student_learning_snapshots')
    op.drop_index(op.f('ix_academic_student_learning_snapshots_openedx_user_id'), table_name='academic_student_learning_snapshots')
    op.drop_index(op.f('ix_academic_student_learning_snapshots_openedx_username'), table_name='academic_student_learning_snapshots')
    op.drop_index(op.f('ix_academic_student_learning_snapshots_openedx_course_id'), table_name='academic_student_learning_snapshots')
    op.drop_index(op.f('ix_academic_student_learning_snapshots_student_id'), table_name='academic_student_learning_snapshots')
    op.drop_index(op.f('ix_academic_student_learning_snapshots_class_id'), table_name='academic_student_learning_snapshots')
    op.drop_index('ix_academic_learning_status_grade', table_name='academic_student_learning_snapshots')
    op.drop_index('ix_academic_learning_class_course_sync', table_name='academic_student_learning_snapshots')
    op.drop_table('academic_student_learning_snapshots')
