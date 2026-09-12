from pathlib import Path
from types import SimpleNamespace

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.api.routes import academic as academic_routes
from app.models.academic import (
    AcademicBulkOperationJob,
    AcademicClassSyncJob,
    AcademicTeacherReportJob,
)
from app.services.business_rbac import BusinessRBACService


ROOT = Path(__file__).resolve().parents[3]
ROUTE_SOURCE = (ROOT / 'backend/app/api/routes/academic.py').read_text(encoding='utf-8')
API_SOURCE = (ROOT / 'frontend/lib/api.ts').read_text(encoding='utf-8')
JOBS_PAGE_SOURCE = (ROOT / 'frontend/app/jobs/page.tsx').read_text(encoding='utf-8')
TEACHER_PAGE_SOURCE = (
    ROOT / 'frontend/app/teacher-management/TeacherManagementPlatformPage.tsx'
).read_text(encoding='utf-8')


def test_retry_routes_exist_for_failed_bulk_and_teacher_report_jobs():
    assert "@router.post('/bulk-operation-jobs/{job_id}/retry'" in ROUTE_SOURCE
    assert "@router.post('/training/teachers/report-jobs/{job_id}/retry'" in ROUTE_SOURCE
    assert "if job.status != 'failed'" in ROUTE_SOURCE
    assert 'retry_count' in ROUTE_SOURCE


def test_frontend_exposes_retry_actions_and_orphan_explanation():
    assert 'retryAcademicBulkOperationJob' in API_SOURCE
    assert 'retryAcademicTrainingTeacherReportJob' in API_SOURCE
    assert 'CELERY_JOB_ORPHANED' in JOBS_PAGE_SOURCE
    assert 'retryAcademicTrainingTeacherReportJob' in TEACHER_PAGE_SOURCE
    assert 'Chạy lại tác vụ' in JOBS_PAGE_SOURCE


def _retry_engine():
    engine = create_engine('sqlite+pysqlite:///:memory:')
    for model in (AcademicBulkOperationJob, AcademicClassSyncJob, AcademicTeacherReportJob):
        model.__table__.create(engine)
    return engine


def _allow_scope_and_capture_enqueue(monkeypatch):
    calls = []
    monkeypatch.setattr(
        BusinessRBACService,
        'require_academic_scope',
        lambda *args, **kwargs: None,
    )

    def fake_enqueue(task, job_id, *, queue, attempt=1, **kwargs):
        calls.append({'job_id': job_id, 'queue': queue, 'attempt': attempt})
        return {
            'task_name': str(getattr(task, 'name', 'test-task')),
            'celery_task_id': f'task-{job_id}-{attempt}',
            'queue': queue,
            'attempt': attempt,
            'enqueued_at': '2026-09-12T12:00:00',
        }

    monkeypatch.setattr(academic_routes, 'enqueue_job_task', fake_enqueue)
    return calls


def test_failed_teacher_report_retries_same_row_on_exports_queue(monkeypatch):
    calls = _allow_scope_and_capture_enqueue(monkeypatch)
    engine = _retry_engine()
    with Session(engine) as db:
        db.add(AcademicTeacherReportJob(
            id='report-1',
            job_type='export_excel',
            status='failed',
            progress_current=55,
            result_json={'code': 'CELERY_JOB_ORPHANED'},
            error_message='Worker interrupted',
        ))
        db.commit()

        job = academic_routes.retry_training_teacher_report_job(
            'report-1',
            user=SimpleNamespace(),
            db=db,
        )

        assert job.id == 'report-1'
        assert job.status == 'queued'
        assert job.progress_current == 0
        assert job.result_json['retry_count'] == 1
        assert job.result_json['last_failure']['code'] == 'CELERY_JOB_ORPHANED'
        assert calls == [{'job_id': 'report-1', 'queue': 'exports', 'attempt': 2}]
    engine.dispose()


def test_failed_bulk_retry_keeps_scope_and_marks_failed_children_for_batched_retry(monkeypatch):
    calls = _allow_scope_and_capture_enqueue(monkeypatch)
    engine = _retry_engine()
    with Session(engine) as db:
        db.add(AcademicBulkOperationJob(
            id='bulk-1',
            job_type='subject_auto_map_all_sync',
            status='failed',
            request_json={'approved_class_ids': ['class-1']},
            result_json={
                'phase': 'finished',
                'target_class_ids': ['class-1'],
                'code': 'CELERY_JOB_ORPHANED',
            },
            error_message='Worker interrupted',
        ))
        db.add(AcademicClassSyncJob(
            id='child-1',
            job_type='full_cms_sync',
            status='failed',
            class_id='class-1',
            parent_job_id='bulk-1',
        ))
        db.commit()

        job = academic_routes.retry_academic_bulk_operation_job(
            'bulk-1',
            user=SimpleNamespace(),
            db=db,
        )

        assert job.id == 'bulk-1'
        assert job.status == 'queued'
        assert job.request_json['approved_class_ids'] == ['class-1']
        assert job.result_json['phase'] == 'dispatching'
        assert job.result_json['retry_child_job_ids'] == ['child-1']
        assert job.result_json['retry_count'] == 1
        assert calls == [{'job_id': 'bulk-1', 'queue': 'sync', 'attempt': 2}]
    engine.dispose()
