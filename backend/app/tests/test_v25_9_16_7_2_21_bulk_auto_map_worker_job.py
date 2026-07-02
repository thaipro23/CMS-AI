from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
ROUTE = ROOT / 'backend/app/api/routes/academic.py'
WORKER = ROOT / 'backend/app/worker.py'
MODELS = ROOT / 'backend/app/models/academic.py'
SCHEMAS = ROOT / 'backend/app/schemas/academic.py'
MIGRATION = ROOT / 'backend/alembic/versions/0051_v25_9_16_7_2_21_bulk_academic_jobs.py'
JOBS_PAGE = ROOT / 'frontend/app/jobs/page.tsx'
STUDENT_PAGE = ROOT / 'frontend/app/student-management/page.tsx'
API = ROOT / 'frontend/lib/api.ts'
TYPES = ROOT / 'frontend/types/index.ts'


def test_bulk_auto_map_has_persistent_parent_job_model_and_migration():
    models = MODELS.read_text(encoding='utf-8')
    migration = MIGRATION.read_text(encoding='utf-8')
    schemas = SCHEMAS.read_text(encoding='utf-8')
    assert 'class AcademicBulkOperationJob' in models
    assert "__tablename__ = 'academic_bulk_operation_jobs'" in models
    assert 'op.create_table(' in migration
    assert 'academic_bulk_operation_jobs' in migration
    assert 'class AcademicBulkOperationJobOut' in schemas


def test_bulk_auto_map_route_only_creates_worker_job_not_inline_sync():
    route = ROUTE.read_text(encoding='utf-8')
    assert "@router.post('/subjects/course-mapping/auto-all-sync/jobs'" in route
    assert 'AcademicBulkOperationJob(' in route
    assert 'academic_subject_auto_map_all_sync_task.delay(job.id)' in route
    assert 'Đã tạo job Auto map tất cả' in route
    endpoint_block = route.split("@router.post('/subjects/course-mapping/auto-all-sync/jobs'", 1)[1].split("@router.get('/bulk-operation-jobs'", 1)[0]
    assert '_enqueue_class_sync_job(' not in endpoint_block
    assert 'auto_map_subject_courses_for_filter(' not in endpoint_block


def test_worker_runs_auto_map_and_enqueues_child_class_sync_jobs():
    worker = WORKER.read_text(encoding='utf-8')
    assert "@celery_app.task(name='academic_subject_auto_map_all_sync_task')" in worker
    assert 'auto_map_subject_courses_for_filter' in worker
    assert '_enqueue_academic_class_sync_child_job' in worker
    assert "job_type='full_cms_sync'" in worker
    assert 'academic_class_sync_task.delay(job.id)' in worker
    assert "parent_job_type': 'subject_auto_map_all_sync'" in worker


def test_jobs_page_and_student_management_show_bulk_job_progress():
    api = API.read_text(encoding='utf-8')
    types = TYPES.read_text(encoding='utf-8')
    jobs = JOBS_PAGE.read_text(encoding='utf-8')
    student = STUDENT_PAGE.read_text(encoding='utf-8')
    assert 'AcademicBulkOperationJob' in types
    assert 'getAcademicBulkOperationJobs' in api
    assert '/academic/bulk-operation-jobs' in api
    assert 'bulkOperationJobs' in jobs
    assert 'Auto map tất cả + đồng bộ CMS' in jobs
    assert 'Auto map đang chạy nền' in student
    assert 'Xem Jobs' in student
