"""Add durable Udemy progress import batches and current snapshots.

Revision ID: 0056_v25_9_16_7_2_64_33
Revises: 0055_v25_9_16_7_2_64_32
"""
from alembic import op
import sqlalchemy as sa

revision = '0056_v25_9_16_7_2_64_33'
down_revision = '0055_v25_9_16_7_2_64_32'
branch_labels = None
depends_on = None


def upgrade() -> None:
    if sa.inspect(op.get_bind()).has_table('udemy_progress_import_batches'):
        return
    op.create_table(
        'udemy_progress_import_batches',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('parent_job_id', sa.String(), nullable=True),
        sa.Column('subject_delivery_id', sa.String(), nullable=False),
        sa.Column('duplicate_of_batch_id', sa.String(), nullable=True),
        sa.Column('idempotency_key', sa.String(length=255), nullable=False),
        sa.Column('file_name', sa.String(length=255), nullable=False),
        sa.Column('file_hash', sa.String(length=64), nullable=False),
        sa.Column('file_size_bytes', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('file_path', sa.Text(), nullable=True),
        sa.Column('error_report_path', sa.Text(), nullable=True),
        sa.Column('parser_format', sa.String(length=50), nullable=True),
        sa.Column('status', sa.String(length=50), nullable=False, server_default='queued'),
        sa.Column('force_reimport', sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column('total_rows', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('processed_rows', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('matched_rows', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('outside_roster_rows', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('unmatched_rows', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('ambiguous_rows', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('failed_rows', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('requested_by', sa.String(length=255), nullable=True),
        sa.Column('request_json', sa.JSON(), nullable=True),
        sa.Column('result_json', sa.JSON(), nullable=True),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('started_at', sa.DateTime(), nullable=True),
        sa.Column('finished_at', sa.DateTime(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.ForeignKeyConstraint(['parent_job_id'], ['academic_bulk_operation_jobs.id']),
        sa.ForeignKeyConstraint(['subject_delivery_id'], ['academic_subject_deliveries.id']),
        sa.ForeignKeyConstraint(['duplicate_of_batch_id'], ['udemy_progress_import_batches.id']),
        sa.CheckConstraint("status IN ('queued', 'running', 'completed', 'failed', 'skipped')", name='ck_udemy_progress_batch_status'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('idempotency_key'),
    )
    for name, columns in [
        ('ix_udemy_progress_import_batches_parent_job_id', ['parent_job_id']),
        ('ix_udemy_progress_import_batches_subject_delivery_id', ['subject_delivery_id']),
        ('ix_udemy_progress_import_batches_duplicate_of_batch_id', ['duplicate_of_batch_id']),
        ('ix_udemy_progress_import_batches_idempotency_key', ['idempotency_key']),
        ('ix_udemy_progress_import_batches_file_hash', ['file_hash']),
        ('ix_udemy_progress_import_batches_parser_format', ['parser_format']),
        ('ix_udemy_progress_import_batches_status', ['status']),
        ('ix_udemy_progress_import_batches_requested_by', ['requested_by']),
        ('ix_udemy_progress_import_batches_finished_at', ['finished_at']),
        ('ix_udemy_progress_import_batches_created_at', ['created_at']),
        ('ix_udemy_progress_batch_delivery_created', ['subject_delivery_id', 'created_at']),
        ('ix_udemy_progress_batch_job_status', ['parent_job_id', 'status']),
        ('ix_udemy_progress_batch_delivery_hash', ['subject_delivery_id', 'file_hash']),
    ]:
        op.create_index(name, 'udemy_progress_import_batches', columns)

    op.create_table(
        'udemy_student_progress',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('subject_delivery_id', sa.String(), nullable=False),
        sa.Column('class_id', sa.String(), nullable=True),
        sa.Column('student_id', sa.String(), nullable=True),
        sa.Column('email', sa.String(length=320), nullable=False),
        sa.Column('normalized_email', sa.String(length=320), nullable=False),
        sa.Column('display_name', sa.String(length=255), nullable=True),
        sa.Column('progress_percent', sa.Float(), nullable=False, server_default='0'),
        sa.Column('is_late', sa.Boolean(), nullable=True),
        sa.Column('current_plan_week', sa.Integer(), nullable=True),
        sa.Column('required_progress_percent', sa.Float(), nullable=True),
        sa.Column('current_deadline_date', sa.Date(), nullable=True),
        sa.Column('match_status', sa.String(length=50), nullable=False, server_default='unmatched'),
        sa.Column('source_format', sa.String(length=50), nullable=False, server_default='unknown'),
        sa.Column('last_import_batch_id', sa.String(), nullable=False),
        sa.Column('last_imported_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('metadata_json', sa.JSON(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.ForeignKeyConstraint(['subject_delivery_id'], ['academic_subject_deliveries.id']),
        sa.ForeignKeyConstraint(['class_id'], ['academic_classes.id']),
        sa.ForeignKeyConstraint(['student_id'], ['academic_students.id']),
        sa.ForeignKeyConstraint(['last_import_batch_id'], ['udemy_progress_import_batches.id']),
        sa.CheckConstraint('progress_percent >= 0 AND progress_percent <= 100', name='ck_udemy_student_progress_percent'),
        sa.CheckConstraint("match_status IN ('matched_roster', 'matched_student_outside_roster', 'ambiguous', 'unmatched')", name='ck_udemy_student_progress_match_status'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('subject_delivery_id', 'normalized_email', name='uq_udemy_student_progress_delivery_email'),
    )
    for name, columns in [
        ('ix_udemy_student_progress_subject_delivery_id', ['subject_delivery_id']),
        ('ix_udemy_student_progress_class_id', ['class_id']),
        ('ix_udemy_student_progress_student_id', ['student_id']),
        ('ix_udemy_student_progress_normalized_email', ['normalized_email']),
        ('ix_udemy_student_progress_is_late', ['is_late']),
        ('ix_udemy_student_progress_match_status', ['match_status']),
        ('ix_udemy_student_progress_source_format', ['source_format']),
        ('ix_udemy_student_progress_last_import_batch_id', ['last_import_batch_id']),
        ('ix_udemy_student_progress_last_imported_at', ['last_imported_at']),
        ('ix_udemy_student_progress_delivery_late', ['subject_delivery_id', 'is_late']),
        ('ix_udemy_student_progress_delivery_match', ['subject_delivery_id', 'match_status']),
        ('ix_udemy_student_progress_class_student', ['class_id', 'student_id']),
    ]:
        op.create_index(name, 'udemy_student_progress', columns)

    op.create_table(
        'udemy_progress_unmatched_rows',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('batch_id', sa.String(), nullable=False),
        sa.Column('subject_delivery_id', sa.String(), nullable=False),
        sa.Column('row_number', sa.Integer(), nullable=True),
        sa.Column('email', sa.String(length=320), nullable=True),
        sa.Column('display_name', sa.String(length=255), nullable=True),
        sa.Column('raw_progress', sa.String(length=255), nullable=True),
        sa.Column('normalized_progress', sa.Float(), nullable=True),
        sa.Column('reason_code', sa.String(length=80), nullable=False),
        sa.Column('reason_message', sa.Text(), nullable=False),
        sa.Column('raw_json', sa.JSON(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.ForeignKeyConstraint(['batch_id'], ['udemy_progress_import_batches.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['subject_delivery_id'], ['academic_subject_deliveries.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    for name, columns in [
        ('ix_udemy_progress_unmatched_rows_batch_id', ['batch_id']),
        ('ix_udemy_progress_unmatched_rows_subject_delivery_id', ['subject_delivery_id']),
        ('ix_udemy_progress_unmatched_rows_email', ['email']),
        ('ix_udemy_progress_unmatched_rows_reason_code', ['reason_code']),
        ('ix_udemy_progress_unmatched_rows_created_at', ['created_at']),
        ('ix_udemy_progress_unmatched_batch_reason', ['batch_id', 'reason_code']),
        ('ix_udemy_progress_unmatched_delivery_email', ['subject_delivery_id', 'email']),
    ]:
        op.create_index(name, 'udemy_progress_unmatched_rows', columns)


def downgrade() -> None:
    op.execute('DROP TABLE IF EXISTS udemy_progress_unmatched_rows CASCADE')
    op.execute('DROP TABLE IF EXISTS udemy_student_progress CASCADE')
    op.execute('DROP TABLE IF EXISTS udemy_progress_import_batches CASCADE')
