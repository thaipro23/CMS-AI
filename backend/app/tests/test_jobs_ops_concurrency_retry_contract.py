from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
WORKER = ROOT / 'backend/app/worker.py'
CONFIG = ROOT / 'backend/app/core/config.py'
ACADEMIC = ROOT / 'backend/app/api/routes/academic.py'
LEARNING_BULK = ROOT / 'backend/app/api/routes/academic_learning_bulk.py'
SCHEMAS = ROOT / 'backend/app/schemas/academic.py'
JOBS_PAGE = ROOT / 'frontend/app/jobs/page.tsx'
API = ROOT / 'frontend/lib/api.ts'
TYPES = ROOT / 'frontend/types/index.ts'
WORKER_DEPLOY = ROOT / 'deploy/k8s/base/worker.yaml'


def test_single_large_sync_worker_runs_ten_slots():
    deploy = WORKER_DEPLOY.read_text(encoding='utf-8')
    assert 'replicas: 1' in deploy
    assert '--concurrency=${CELERY_CONCURRENCY:-10}' in deploy
    assert '- name: CELERY_CONCURRENCY' in deploy
    assert 'value: "10"' in deploy
    assert '- name: ACADEMIC_BULK_SYNC_DISPATCH_WINDOW' in deploy
    assert '--prefetch-multiplier=${CELERY_WORKER_PREFETCH_MULTIPLIER:-1}' in deploy


def test_class_sync_has_bounded_transient_retry():
    config = CONFIG.read_text(encoding='utf-8')
    worker = WORKER.read_text(encoding='utf-8')
    assert 'academic_class_sync_retry_max_attempts: int = 3' in config
    assert 'academic_class_sync_retry_base_seconds: int = 15' in config
    assert 'academic_class_sync_retry_max_seconds: int = 120' in config
    assert "bind=True" in worker
    assert "CLASS_SYNC_TRANSIENT_RETRY" in worker
    assert "504 gateway timeout" in worker
    assert "httpx.TimeoutException" in worker
    assert "raise self.retry(" in worker
    assert "retry_exhausted" in worker


def test_learning_refresh_filter_has_real_worker_coordinator():
    route = LEARNING_BULK.read_text(encoding='utf-8')
    worker = WORKER.read_text(encoding='utf-8')
    academic = ACADEMIC.read_text(encoding='utf-8')
    assert "job_type='learning_refresh_filter'" in route
    assert "'academic_learning_refresh_filter_task': {'queue': 'sync'}" in worker
    assert "@celery_app.task(name='academic_learning_refresh_filter_task')" in worker
    assert "job_type='learning_sync'" in worker
    assert "window = max(1, min(10, int(settings.academic_bulk_sync_dispatch_window)))" in worker
    assert "'learning_refresh_filter'," in academic


def test_jobs_console_shows_generation_and_groups_bulk_children():
    jobs = JOBS_PAGE.read_text(encoding='utf-8')
    api = API.read_text(encoding='utf-8')
    types = TYPES.read_text(encoding='utf-8')
    schemas = SCHEMAS.read_text(encoding='utf-8')
    assert 'getJobs(null, headers)' in jobs
    assert "label: 'Gen câu hỏi'" in jobs
    assert '<option value="generation">Gen câu hỏi</option>' in jobs
    assert "learning_refresh_filter: 'Cập nhật điểm CMS theo bộ lọc'" in jobs
    assert "Chờ tự chạy lại" in jobs
    assert "10 slot đồng bộ lớp" in jobs
    assert "parentJobId: job.parent_job_id" in jobs
    assert "topLevelClassRows" in jobs
    assert "courseId: string | null | undefined" in api
    assert "parent_job_id?: string | null" in types
    assert "parent_job_id: str | None = None" in schemas

def test_audit_events_do_not_stay_in_queued_state_after_enqueue_or_retry():
    worker = WORKER.read_text(encoding='utf-8')
    academic = ACADEMIC.read_text(encoding='utf-8')
    jobs = JOBS_PAGE.read_text(encoding='utf-8')

    retry_block = worker.split("action='academic.class_sync.async.retry'", 1)[1].split("raise self.retry", 1)[0]
    assert "status='success'" in retry_block
    assert "status='queued'" not in retry_block

    email_block = academic.split("action='academic.progress_email.enqueue'", 1)[1].split("return job", 1)[0]
    assert "status='success'" in email_block
    assert "status='queued'" not in email_block

    assert "academic.class_sync.async.retry" not in jobs or "Chờ tự chạy lại" in jobs

def test_k8s_runtime_bypasses_public_haproxy_for_connector_calls():
    for relative in (
        'deploy/k8s/base/backend.yaml',
        'deploy/k8s/base/worker.yaml',
        'deploy/k8s/base/worker-heavy.yaml',
        'deploy/k8s/base/worker-analytics.yaml',
    ):
        source = (ROOT / relative).read_text(encoding='utf-8')
        assert 'OPENEDX_CONNECTOR_INTERNAL_BASE_URL' in source
        assert 'http://lms:8000' in source

def test_legacy_queued_audit_events_render_as_success():
    audit = (ROOT / 'backend/app/api/routes/audit.py').read_text(encoding='utf-8')

    assert "_LEGACY_EVENT_SUCCESS_ACTIONS" in audit
    assert "'academic.progress_email.enqueue'" in audit
    assert "'academic.class_sync.async.retry'" in audit
    assert 'def _effective_status' in audit
    assert "_csv_cell(_effective_status(row))" in audit

