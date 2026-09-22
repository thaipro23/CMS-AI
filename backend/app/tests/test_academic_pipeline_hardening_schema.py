from pathlib import Path

from app.models.academic import (
    AcademicBulkOperationJob,
    AcademicTeacherReportSnapshot,
)


ROOT = Path(__file__).resolve().parents[3]
MIGRATION = (
    ROOT
    / 'backend/alembic/versions/0066_academic_pipeline_hardening.py'
)


def test_bulk_parent_has_nullable_unique_idempotency_key():
    column = AcademicBulkOperationJob.__table__.columns['idempotency_key']

    assert column.nullable is True
    assert column.unique is True
    assert column.index is True


def test_report_snapshot_metadata_is_run_specific_and_payload_stays_external():
    columns = AcademicTeacherReportSnapshot.__table__.columns

    assert {
        'id',
        'parent_job_id',
        'term_id',
        'branch',
        'scope_type',
        'campus',
        'policy_version',
        'storage_key',
        'sha256',
        'size_bytes',
        'counts_json',
        'metadata_json',
        'created_at',
        'updated_at',
    }.issubset(columns.keys())
    assert columns['storage_key'].nullable is False
    assert columns['sha256'].nullable is False
    assert 'payload_json' not in columns

    index = next(
        item
        for item in AcademicTeacherReportSnapshot.__table__.indexes
        if item.name == 'uq_academic_teacher_report_snapshot_parent_scope_campus'
    )
    assert index.unique is True


def test_migration_0066_follows_0065_and_creates_snapshot_table():
    source = MIGRATION.read_text(encoding='utf-8')

    assert "revision = '0066_academic_pipeline_hardening'" in source
    assert "down_revision = '0065_academic_job_batch_recovery'" in source
    assert "'academic_teacher_report_snapshots'" in source
    assert "'ix_academic_bulk_operation_jobs_idempotency_key'" in source
