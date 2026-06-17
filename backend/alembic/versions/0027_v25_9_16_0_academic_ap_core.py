"""v25.9.16.0 academic AP core migration

Revision ID: 0027_v25_9_16_0_academic_ap_core
Revises: 0026_v25_9_15_6_38_4
Create Date: 2026-06-16
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = '0027_v25_9_16_0_academic_ap_core'
down_revision = '0036_v25_9_15_6_38_8_4'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'academic_terms',
        sa.Column('id', sa.String(), primary_key=True),
        sa.Column('ap_term_id', sa.String(length=64), nullable=True),
        sa.Column('term_code', sa.String(length=128), nullable=False),
        sa.Column('term_name', sa.String(length=255), nullable=False),
        sa.Column('branch', sa.String(length=64), nullable=True),
        sa.Column('start_date', sa.DateTime(), nullable=True),
        sa.Column('end_date', sa.DateTime(), nullable=True),
        sa.Column('active', sa.Boolean(), nullable=False, server_default=sa.text('true')),
        sa.Column('metadata_json', sa.JSON(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.UniqueConstraint('term_code', 'branch', name='uq_academic_terms_code_branch'),
    )
    op.create_index('ix_academic_terms_ap_term_id', 'academic_terms', ['ap_term_id'])
    op.create_index('ix_academic_terms_term_code', 'academic_terms', ['term_code'])
    op.create_index('ix_academic_terms_term_name', 'academic_terms', ['term_name'])
    op.create_index('ix_academic_terms_branch', 'academic_terms', ['branch'])
    op.create_index('ix_academic_terms_active', 'academic_terms', ['active'])
    op.create_index('ix_academic_terms_branch_active', 'academic_terms', ['branch', 'active'])

    op.create_table(
        'academic_blocks',
        sa.Column('id', sa.String(), primary_key=True),
        sa.Column('term_id', sa.String(), sa.ForeignKey('academic_terms.id'), nullable=False),
        sa.Column('ap_block_id', sa.String(length=64), nullable=True),
        sa.Column('block_code', sa.String(length=128), nullable=False),
        sa.Column('block_name', sa.String(length=255), nullable=False),
        sa.Column('start_date', sa.DateTime(), nullable=True),
        sa.Column('end_date', sa.DateTime(), nullable=True),
        sa.Column('sort_order', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('active', sa.Boolean(), nullable=False, server_default=sa.text('true')),
        sa.Column('metadata_json', sa.JSON(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.UniqueConstraint('term_id', 'block_code', name='uq_academic_blocks_term_code'),
    )
    op.create_index('ix_academic_blocks_term_id', 'academic_blocks', ['term_id'])
    op.create_index('ix_academic_blocks_ap_block_id', 'academic_blocks', ['ap_block_id'])
    op.create_index('ix_academic_blocks_block_code', 'academic_blocks', ['block_code'])
    op.create_index('ix_academic_blocks_sort_order', 'academic_blocks', ['sort_order'])
    op.create_index('ix_academic_blocks_active', 'academic_blocks', ['active'])
    op.create_index('ix_academic_blocks_term_active_order', 'academic_blocks', ['term_id', 'active', 'sort_order'])

    op.create_table(
        'academic_subjects',
        sa.Column('id', sa.String(), primary_key=True),
        sa.Column('ap_subject_id', sa.String(length=64), nullable=True),
        sa.Column('subject_code', sa.String(length=64), nullable=False),
        sa.Column('subject_name', sa.String(length=255), nullable=False),
        sa.Column('subject_name_en', sa.String(length=255), nullable=True),
        sa.Column('skill_code', sa.String(length=64), nullable=True),
        sa.Column('branch', sa.String(length=64), nullable=True),
        sa.Column('active', sa.Boolean(), nullable=False, server_default=sa.text('true')),
        sa.Column('metadata_json', sa.JSON(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.UniqueConstraint('subject_code', 'branch', name='uq_academic_subjects_code_branch'),
    )
    op.create_index('ix_academic_subjects_ap_subject_id', 'academic_subjects', ['ap_subject_id'])
    op.create_index('ix_academic_subjects_subject_code', 'academic_subjects', ['subject_code'])
    op.create_index('ix_academic_subjects_skill_code', 'academic_subjects', ['skill_code'])
    op.create_index('ix_academic_subjects_branch', 'academic_subjects', ['branch'])
    op.create_index('ix_academic_subjects_active', 'academic_subjects', ['active'])
    op.create_index('ix_academic_subjects_branch_active_code', 'academic_subjects', ['branch', 'active', 'subject_code'])

    op.create_table(
        'academic_teachers',
        sa.Column('id', sa.String(), primary_key=True),
        sa.Column('teacher_code', sa.String(length=64), nullable=True),
        sa.Column('username', sa.String(length=255), nullable=False),
        sa.Column('email', sa.String(length=255), nullable=True),
        sa.Column('full_name', sa.String(length=255), nullable=False, server_default=''),
        sa.Column('campus', sa.String(length=64), nullable=True),
        sa.Column('branch', sa.String(length=64), nullable=True),
        sa.Column('active', sa.Boolean(), nullable=False, server_default=sa.text('true')),
        sa.Column('metadata_json', sa.JSON(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.UniqueConstraint('username', name='uq_academic_teachers_username'),
    )
    op.create_index('ix_academic_teachers_teacher_code', 'academic_teachers', ['teacher_code'])
    op.create_index('ix_academic_teachers_username', 'academic_teachers', ['username'])
    op.create_index('ix_academic_teachers_email', 'academic_teachers', ['email'])
    op.create_index('ix_academic_teachers_campus', 'academic_teachers', ['campus'])
    op.create_index('ix_academic_teachers_branch', 'academic_teachers', ['branch'])
    op.create_index('ix_academic_teachers_active', 'academic_teachers', ['active'])
    op.create_index('ix_academic_teachers_active_username', 'academic_teachers', ['active', 'username'])

    op.create_table(
        'academic_students',
        sa.Column('id', sa.String(), primary_key=True),
        sa.Column('student_code', sa.String(length=64), nullable=True),
        sa.Column('username', sa.String(length=255), nullable=False),
        sa.Column('email', sa.String(length=255), nullable=True),
        sa.Column('full_name', sa.String(length=255), nullable=False, server_default=''),
        sa.Column('phone', sa.String(length=64), nullable=True),
        sa.Column('campus', sa.String(length=64), nullable=True),
        sa.Column('branch', sa.String(length=64), nullable=True),
        sa.Column('active', sa.Boolean(), nullable=False, server_default=sa.text('true')),
        sa.Column('metadata_json', sa.JSON(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.UniqueConstraint('username', name='uq_academic_students_username'),
    )
    op.create_index('ix_academic_students_student_code', 'academic_students', ['student_code'])
    op.create_index('ix_academic_students_username', 'academic_students', ['username'])
    op.create_index('ix_academic_students_email', 'academic_students', ['email'])
    op.create_index('ix_academic_students_campus', 'academic_students', ['campus'])
    op.create_index('ix_academic_students_branch', 'academic_students', ['branch'])
    op.create_index('ix_academic_students_active', 'academic_students', ['active'])
    op.create_index('ix_academic_students_code_username', 'academic_students', ['student_code', 'username'])
    op.create_index('ix_academic_students_active_username', 'academic_students', ['active', 'username'])

    op.create_table(
        'academic_classes',
        sa.Column('id', sa.String(), primary_key=True),
        sa.Column('ap_class_id', sa.String(length=64), nullable=True),
        sa.Column('term_id', sa.String(), sa.ForeignKey('academic_terms.id'), nullable=False),
        sa.Column('block_id', sa.String(), sa.ForeignKey('academic_blocks.id'), nullable=True),
        sa.Column('subject_id', sa.String(), sa.ForeignKey('academic_subjects.id'), nullable=False),
        sa.Column('class_code', sa.String(length=128), nullable=False),
        sa.Column('class_name', sa.String(length=255), nullable=False, server_default=''),
        sa.Column('campus', sa.String(length=64), nullable=True),
        sa.Column('branch', sa.String(length=64), nullable=True),
        sa.Column('start_date', sa.DateTime(), nullable=True),
        sa.Column('end_date', sa.DateTime(), nullable=True),
        sa.Column('active', sa.Boolean(), nullable=False, server_default=sa.text('true')),
        sa.Column('metadata_json', sa.JSON(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.UniqueConstraint('term_id', 'block_id', 'subject_id', 'class_code', name='uq_academic_classes_term_block_subject_code'),
    )
    op.create_index('ix_academic_classes_ap_class_id', 'academic_classes', ['ap_class_id'])
    op.create_index('ix_academic_classes_term_id', 'academic_classes', ['term_id'])
    op.create_index('ix_academic_classes_block_id', 'academic_classes', ['block_id'])
    op.create_index('ix_academic_classes_subject_id', 'academic_classes', ['subject_id'])
    op.create_index('ix_academic_classes_class_code', 'academic_classes', ['class_code'])
    op.create_index('ix_academic_classes_campus', 'academic_classes', ['campus'])
    op.create_index('ix_academic_classes_branch', 'academic_classes', ['branch'])
    op.create_index('ix_academic_classes_active', 'academic_classes', ['active'])
    op.create_index('ix_academic_classes_teacher_lookup', 'academic_classes', ['term_id', 'block_id', 'subject_id', 'active'])
    op.create_index('ix_academic_classes_campus_branch', 'academic_classes', ['campus', 'branch'])

    op.create_table(
        'academic_teacher_assignments',
        sa.Column('id', sa.String(), primary_key=True),
        sa.Column('teacher_id', sa.String(), sa.ForeignKey('academic_teachers.id'), nullable=False),
        sa.Column('class_id', sa.String(), sa.ForeignKey('academic_classes.id'), nullable=False),
        sa.Column('subject_id', sa.String(), sa.ForeignKey('academic_subjects.id'), nullable=False),
        sa.Column('term_id', sa.String(), sa.ForeignKey('academic_terms.id'), nullable=False),
        sa.Column('block_id', sa.String(), sa.ForeignKey('academic_blocks.id'), nullable=True),
        sa.Column('campus', sa.String(length=64), nullable=True),
        sa.Column('branch', sa.String(length=64), nullable=True),
        sa.Column('source', sa.String(length=50), nullable=False, server_default='ap'),
        sa.Column('synced_at', sa.DateTime(), nullable=False),
        sa.Column('metadata_json', sa.JSON(), nullable=True),
        sa.UniqueConstraint('teacher_id', 'class_id', 'subject_id', 'term_id', 'block_id', name='uq_academic_teacher_assignment'),
    )
    op.create_index('ix_academic_teacher_assignments_teacher_id', 'academic_teacher_assignments', ['teacher_id'])
    op.create_index('ix_academic_teacher_assignments_class_id', 'academic_teacher_assignments', ['class_id'])
    op.create_index('ix_academic_teacher_assignments_subject_id', 'academic_teacher_assignments', ['subject_id'])
    op.create_index('ix_academic_teacher_assignments_term_id', 'academic_teacher_assignments', ['term_id'])
    op.create_index('ix_academic_teacher_assignments_block_id', 'academic_teacher_assignments', ['block_id'])
    op.create_index('ix_academic_teacher_assignments_campus', 'academic_teacher_assignments', ['campus'])
    op.create_index('ix_academic_teacher_assignments_branch', 'academic_teacher_assignments', ['branch'])
    op.create_index('ix_academic_teacher_assignments_synced_at', 'academic_teacher_assignments', ['synced_at'])
    op.create_index('ix_academic_teacher_assignments_teacher_term_block', 'academic_teacher_assignments', ['teacher_id', 'term_id', 'block_id'])
    op.create_index('ix_academic_teacher_assignments_class_teacher', 'academic_teacher_assignments', ['class_id', 'teacher_id'])

    op.create_table(
        'academic_class_students',
        sa.Column('id', sa.String(), primary_key=True),
        sa.Column('class_id', sa.String(), sa.ForeignKey('academic_classes.id'), nullable=False),
        sa.Column('student_id', sa.String(), sa.ForeignKey('academic_students.id'), nullable=False),
        sa.Column('source', sa.String(length=50), nullable=False, server_default='ap'),
        sa.Column('synced_at', sa.DateTime(), nullable=False),
        sa.Column('metadata_json', sa.JSON(), nullable=True),
        sa.UniqueConstraint('class_id', 'student_id', name='uq_academic_class_student'),
    )
    op.create_index('ix_academic_class_students_class_id', 'academic_class_students', ['class_id'])
    op.create_index('ix_academic_class_students_student_id', 'academic_class_students', ['student_id'])
    op.create_index('ix_academic_class_students_synced_at', 'academic_class_students', ['synced_at'])
    op.create_index('ix_academic_class_students_class_student', 'academic_class_students', ['class_id', 'student_id'])

    op.create_table(
        'academic_course_mappings',
        sa.Column('id', sa.String(), primary_key=True),
        sa.Column('term_id', sa.String(), sa.ForeignKey('academic_terms.id'), nullable=False),
        sa.Column('block_id', sa.String(), sa.ForeignKey('academic_blocks.id'), nullable=True),
        sa.Column('subject_id', sa.String(), sa.ForeignKey('academic_subjects.id'), nullable=False),
        sa.Column('campus', sa.String(length=64), nullable=True),
        sa.Column('branch', sa.String(length=64), nullable=True),
        sa.Column('openedx_course_id', sa.String(length=255), nullable=False),
        sa.Column('active', sa.Boolean(), nullable=False, server_default=sa.text('true')),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.UniqueConstraint('term_id', 'block_id', 'subject_id', 'campus', 'branch', name='uq_academic_course_mapping_scope'),
    )
    op.create_index('ix_academic_course_mappings_term_id', 'academic_course_mappings', ['term_id'])
    op.create_index('ix_academic_course_mappings_block_id', 'academic_course_mappings', ['block_id'])
    op.create_index('ix_academic_course_mappings_subject_id', 'academic_course_mappings', ['subject_id'])
    op.create_index('ix_academic_course_mappings_campus', 'academic_course_mappings', ['campus'])
    op.create_index('ix_academic_course_mappings_branch', 'academic_course_mappings', ['branch'])
    op.create_index('ix_academic_course_mappings_openedx_course_id', 'academic_course_mappings', ['openedx_course_id'])
    op.create_index('ix_academic_course_mappings_active', 'academic_course_mappings', ['active'])
    op.create_index('ix_academic_course_mappings_subject_term', 'academic_course_mappings', ['subject_id', 'term_id', 'block_id'])

    op.create_table(
        'academic_class_course_mappings',
        sa.Column('id', sa.String(), primary_key=True),
        sa.Column('class_id', sa.String(), sa.ForeignKey('academic_classes.id'), nullable=False),
        sa.Column('openedx_course_id', sa.String(length=255), nullable=False),
        sa.Column('openedx_cohort_name', sa.String(length=255), nullable=True),
        sa.Column('active', sa.Boolean(), nullable=False, server_default=sa.text('true')),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.UniqueConstraint('class_id', name='uq_academic_class_course_mappings_class_id'),
    )
    op.create_index('ix_academic_class_course_mappings_class_id', 'academic_class_course_mappings', ['class_id'])
    op.create_index('ix_academic_class_course_mappings_openedx_course_id', 'academic_class_course_mappings', ['openedx_course_id'])
    op.create_index('ix_academic_class_course_mappings_openedx_cohort_name', 'academic_class_course_mappings', ['openedx_cohort_name'])
    op.create_index('ix_academic_class_course_mappings_active', 'academic_class_course_mappings', ['active'])

    op.create_table(
        'academic_sync_runs',
        sa.Column('id', sa.String(), primary_key=True),
        sa.Column('source', sa.String(length=50), nullable=False, server_default='ap'),
        sa.Column('mode', sa.String(length=50), nullable=False, server_default='manual'),
        sa.Column('status', sa.String(length=50), nullable=False, server_default='running'),
        sa.Column('requested_by', sa.String(length=255), nullable=True),
        sa.Column('term_name', sa.String(length=255), nullable=True),
        sa.Column('campus', sa.String(length=64), nullable=True),
        sa.Column('branch', sa.String(length=64), nullable=True),
        sa.Column('counters_json', sa.JSON(), nullable=True),
        sa.Column('error_message', sa.Text(), nullable=False, server_default=''),
        sa.Column('started_at', sa.DateTime(), nullable=False),
        sa.Column('finished_at', sa.DateTime(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
    )
    op.create_index('ix_academic_sync_runs_source', 'academic_sync_runs', ['source'])
    op.create_index('ix_academic_sync_runs_mode', 'academic_sync_runs', ['mode'])
    op.create_index('ix_academic_sync_runs_status', 'academic_sync_runs', ['status'])
    op.create_index('ix_academic_sync_runs_requested_by', 'academic_sync_runs', ['requested_by'])
    op.create_index('ix_academic_sync_runs_term_name', 'academic_sync_runs', ['term_name'])
    op.create_index('ix_academic_sync_runs_campus', 'academic_sync_runs', ['campus'])
    op.create_index('ix_academic_sync_runs_branch', 'academic_sync_runs', ['branch'])
    op.create_index('ix_academic_sync_runs_status_created', 'academic_sync_runs', ['status', 'created_at'])

    op.create_table(
        'academic_sync_errors',
        sa.Column('id', sa.String(), primary_key=True),
        sa.Column('sync_run_id', sa.String(), sa.ForeignKey('academic_sync_runs.id'), nullable=True),
        sa.Column('source', sa.String(length=50), nullable=False, server_default='ap'),
        sa.Column('entity_type', sa.String(length=80), nullable=False),
        sa.Column('entity_key', sa.String(length=255), nullable=False, server_default=''),
        sa.Column('message', sa.Text(), nullable=False, server_default=''),
        sa.Column('payload_json', sa.JSON(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
    )
    op.create_index('ix_academic_sync_errors_sync_run_id', 'academic_sync_errors', ['sync_run_id'])
    op.create_index('ix_academic_sync_errors_source', 'academic_sync_errors', ['source'])
    op.create_index('ix_academic_sync_errors_entity_type', 'academic_sync_errors', ['entity_type'])
    op.create_index('ix_academic_sync_errors_entity_key', 'academic_sync_errors', ['entity_key'])
    op.create_index('ix_academic_sync_errors_created_at', 'academic_sync_errors', ['created_at'])


def downgrade() -> None:
    for table in [
        'academic_sync_errors',
        'academic_sync_runs',
        'academic_class_course_mappings',
        'academic_course_mappings',
        'academic_class_students',
        'academic_teacher_assignments',
        'academic_classes',
        'academic_students',
        'academic_teachers',
        'academic_subjects',
        'academic_blocks',
        'academic_terms',
    ]:
        op.drop_table(table)
