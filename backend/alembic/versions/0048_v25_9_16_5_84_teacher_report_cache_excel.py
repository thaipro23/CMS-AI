"""v25.9.16.5.84 teacher report cache and background excel export

Revision ID: 0048_v25_9_16_5_84_teacher_report_cache
Revises: 0047_v25_9_16_5_58_training_policy_hardening
Create Date: 2026-07-01
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = '0048_v25_9_16_5_84_teacher_report_cache'
down_revision = '0047_v25_9_16_5_58_training_policy_hardening'
branch_labels = None
depends_on = None


def upgrade() -> None:
    if sa.inspect(op.get_bind()).has_table('academic_teacher_report_summaries'):
        return
    op.create_table(
        'academic_teacher_report_summaries',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('term_id', sa.String(), nullable=False),
        sa.Column('branch', sa.String(length=64), nullable=True),
        sa.Column('campus', sa.String(length=64), nullable=True),
        sa.Column('scope_key', sa.String(length=255), nullable=False),
        sa.Column('teacher_id', sa.String(), nullable=False),
        sa.Column('teacher_username', sa.String(length=255), nullable=False),
        sa.Column('teacher_name', sa.String(length=255), nullable=False, server_default=''),
        sa.Column('teacher_email', sa.String(length=255), nullable=True),
        sa.Column('class_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('student_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('unique_student_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('risk_student_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('cms_synced_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('learning_enrolled_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('learning_avg_progress_percent', sa.Float(), nullable=True),
        sa.Column('learning_avg_grade_10', sa.Float(), nullable=True),
        sa.Column('report_json', sa.JSON(), nullable=True),
        sa.Column('summary_json', sa.JSON(), nullable=True),
        sa.Column('source_sync_run_id', sa.String(length=255), nullable=True),
        sa.Column('built_by', sa.String(length=255), nullable=True),
        sa.Column('built_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.ForeignKeyConstraint(['teacher_id'], ['academic_teachers.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['term_id'], ['academic_terms.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('scope_key', 'teacher_id', name='uq_academic_teacher_report_scope_teacher'),
    )
    op.create_index('ix_academic_teacher_report_scope_built', 'academic_teacher_report_summaries', ['scope_key', 'built_at'])
    op.create_index('ix_academic_teacher_report_scope_risk', 'academic_teacher_report_summaries', ['scope_key', 'risk_student_count'])
    op.create_index(op.f('ix_academic_teacher_report_summaries_scope_key'), 'academic_teacher_report_summaries', ['scope_key'])
    op.create_index(op.f('ix_academic_teacher_report_summaries_teacher_id'), 'academic_teacher_report_summaries', ['teacher_id'])
    op.create_index(op.f('ix_academic_teacher_report_summaries_teacher_username'), 'academic_teacher_report_summaries', ['teacher_username'])
    op.create_index(op.f('ix_academic_teacher_report_summaries_term_id'), 'academic_teacher_report_summaries', ['term_id'])

    op.create_table(
        'academic_teacher_report_jobs',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('job_type', sa.String(length=80), nullable=False),
        sa.Column('status', sa.String(length=50), nullable=False, server_default='queued'),
        sa.Column('term_id', sa.String(), nullable=True),
        sa.Column('branch', sa.String(length=64), nullable=True),
        sa.Column('campus', sa.String(length=64), nullable=True),
        sa.Column('requested_by', sa.String(length=255), nullable=True),
        sa.Column('progress_current', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('progress_total', sa.Integer(), nullable=False, server_default='100'),
        sa.Column('progress_label', sa.String(length=255), nullable=False, server_default='Đang chờ xử lý'),
        sa.Column('request_json', sa.JSON(), nullable=True),
        sa.Column('result_json', sa.JSON(), nullable=True),
        sa.Column('file_path', sa.String(length=1024), nullable=True),
        sa.Column('file_name', sa.String(length=255), nullable=True),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('started_at', sa.DateTime(), nullable=True),
        sa.Column('finished_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.ForeignKeyConstraint(['term_id'], ['academic_terms.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_academic_teacher_report_jobs_scope_status', 'academic_teacher_report_jobs', ['term_id', 'branch', 'campus', 'status'])
    op.create_index('ix_academic_teacher_report_jobs_actor_created', 'academic_teacher_report_jobs', ['requested_by', 'created_at'])
    op.create_index(op.f('ix_academic_teacher_report_jobs_job_type'), 'academic_teacher_report_jobs', ['job_type'])
    op.create_index(op.f('ix_academic_teacher_report_jobs_status'), 'academic_teacher_report_jobs', ['status'])


def downgrade() -> None:
    op.drop_table('academic_teacher_report_jobs')
    op.drop_table('academic_teacher_report_summaries')
