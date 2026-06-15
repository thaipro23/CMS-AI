"""v25.9.15.6.37 async bank operation jobs

Revision ID: 0019_v25_9_15_6_37
Revises: 0018_v25_9_15_6_35
Create Date: 2026-06-15
"""

from alembic import op
import sqlalchemy as sa


revision = '0019_v25_9_15_6_37'
down_revision = '0018_v25_9_15_6_35'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'ai_bank_operation_jobs',
        sa.Column('id', sa.String(), primary_key=True),
        sa.Column('operation_type', sa.String(length=80), nullable=False),
        sa.Column('status', sa.String(length=50), nullable=False, server_default='queued'),
        sa.Column('target_type', sa.String(length=80), nullable=False, server_default=''),
        sa.Column('target_id', sa.String(length=255), nullable=True),
        sa.Column('bank_version_id', sa.String(), nullable=True),
        sa.Column('release_id', sa.String(), nullable=True),
        sa.Column('material_version_id', sa.String(), nullable=True),
        sa.Column('course_quiz_instance_id', sa.String(), nullable=True),
        sa.Column('requested_by', sa.String(length=255), nullable=True),
        sa.Column('course_id', sa.String(length=255), nullable=True),
        sa.Column('progress_current', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('progress_total', sa.Integer(), nullable=False, server_default='1'),
        sa.Column('progress_label', sa.String(length=255), nullable=False, server_default='Đang chờ xử lý'),
        sa.Column('request_json', sa.JSON(), nullable=True),
        sa.Column('result_json', sa.JSON(), nullable=True),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('started_at', sa.DateTime(), nullable=True),
        sa.Column('finished_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['bank_version_id'], ['ai_question_bank_versions.id']),
        sa.ForeignKeyConstraint(['release_id'], ['ai_question_bank_releases.id']),
        sa.ForeignKeyConstraint(['material_version_id'], ['ai_learning_material_versions.id']),
        sa.ForeignKeyConstraint(['course_quiz_instance_id'], ['ai_course_quiz_instances.id']),
    )
    op.create_index('ix_ai_bank_operation_jobs_status_created', 'ai_bank_operation_jobs', ['status', 'created_at'])
    op.create_index('ix_ai_bank_operation_jobs_target_status_created', 'ai_bank_operation_jobs', ['target_type', 'target_id', 'status', 'created_at'])
    op.create_index('ix_ai_bank_operation_jobs_actor_created', 'ai_bank_operation_jobs', ['requested_by', 'created_at'])
    op.create_index('ix_ai_bank_operation_jobs_bank_status_created', 'ai_bank_operation_jobs', ['bank_version_id', 'status', 'created_at'])
    op.create_index('ix_ai_bank_operation_jobs_release_status_created', 'ai_bank_operation_jobs', ['release_id', 'status', 'created_at'])


def downgrade() -> None:
    op.drop_index('ix_ai_bank_operation_jobs_release_status_created', table_name='ai_bank_operation_jobs')
    op.drop_index('ix_ai_bank_operation_jobs_bank_status_created', table_name='ai_bank_operation_jobs')
    op.drop_index('ix_ai_bank_operation_jobs_actor_created', table_name='ai_bank_operation_jobs')
    op.drop_index('ix_ai_bank_operation_jobs_target_status_created', table_name='ai_bank_operation_jobs')
    op.drop_index('ix_ai_bank_operation_jobs_status_created', table_name='ai_bank_operation_jobs')
    op.drop_table('ai_bank_operation_jobs')
