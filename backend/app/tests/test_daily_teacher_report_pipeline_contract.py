from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]


def text(path: str) -> str:
    target = ROOT / path
    return target.read_text(encoding='utf-8') if target.exists() else ''


def test_daily_teacher_report_worker_registers_runtime_tasks_and_runs_at_0500_vn():
    source = text('backend/app/worker.py')
    assert "Asia/Ho_Chi_Minh" in source
    assert "crontab(hour=5, minute=0)" in source
    assert "register_daily_teacher_report_tasks(celery_app)" in source
    assert "register_student_management_runtime_tasks(celery_app)" in source
    assert "academic-teacher-report-watchdog" in source


def test_compose_celery_runtime_uses_canonical_worker_app():
    for path in ('docker-compose.yml', 'docker-compose.prod.yml'):
        source = text(path)
        assert 'app.worker.celery_app' in source
        assert 'app.worker_entry.celery_app' not in source


def test_k8s_celery_runtime_uses_canonical_worker_app():
    for path in (
        'deploy/k8s/base/worker.yaml',
        'deploy/k8s/base/worker-heavy.yaml',
        'deploy/k8s/base/worker-analytics.yaml',
        'deploy/k8s/base/beat.yaml',
    ):
        source = text(path)
        assert 'app.worker.celery_app' in source
        assert 'app.worker_entry.celery_app' not in source


def test_management_report_pipeline_never_refreshes_cms_and_teacher_class_export_keeps_live_refresh():
    source = text('backend/app/services/academic/daily_teacher_report_runtime.py')
    assert "scheduled_export_excel" in source
    assert "MANAGEMENT_REPORT_PREBUILT_ONLY" in source
    assert "management_scope" in source
    assert "refresh_training_teacher_learning_data" in source
    assert "if not management_scope" in source
    assert "job.job_type == 'rebuild_cache'" in source
    assert "cms_refreshed': False" in source


def test_ghost_job_detection_uses_progress_and_runtime_not_updated_at_only():
    source = text('backend/app/services/academic/daily_teacher_report_runtime.py')
    assert "progress_changed_at" in source
    assert "heartbeat_at" in source
    assert "max_runtime_seconds" in source
    assert "WORKER_HEARTBEAT_LOST" in source
    assert "JOB_PROGRESS_STALLED" in source
    assert "JOB_RUNTIME_EXCEEDED" in source
    health = source.split('def _job_health_failure(', 1)[1].split('def reconcile_teacher_report_watchdog', 1)[0]
    # Comments may mention updated_at, but the watchdog must never read it as a
    # liveness signal. Runtime heartbeat/progress and started_at are authoritative.
    assert "getattr(job, 'updated_at'" not in health
    assert 'getattr(job, "updated_at"' not in health


def test_latest_management_artifact_api_is_download_only_streaming_and_reports_vn_time():
    source = text('backend/app/api/routes/teacher_report_artifacts.py')
    assert "/training/teacher-reports/latest" in source
    assert "/training/teacher-reports/latest/download" in source
    assert "SCHEDULED_EXPORT_JOB_TYPE" in source
    assert "Asia/Ho_Chi_Minh" in source
    assert "generated_at" in source
    assert "source_synced_at" in source
    assert "StreamingResponse" in source
    assert "storage.iter_bytes" in source
    assert "storage.read_bytes" not in source
    assert "refresh_training_teacher_learning_data" not in source


def test_daily_parent_waits_for_terminal_children_before_scheduled_exports():
    source = text('backend/app/services/academic/daily_teacher_report_runtime.py')
    parent = source.split('def run_daily_score_report_parent(', 1)[1].split('def _job_request(', 1)[0]
    assert "_dispatch_daily_score_window" in parent
    assert "terminal_count" in parent
    assert "if not plan.finished" in parent
    assert "_create_scheduled_export_job" in parent
    assert parent.index("if not plan.finished") < parent.index("_create_scheduled_export_job")


def test_cms_teacher_management_keeps_operations_visible_and_has_one_excel_flow():
    page = text('frontend/app/teacher-management/cms/page.tsx')
    api = text('frontend/lib/teacherReportArtifacts.ts')
    management = text('frontend/app/teacher-management/TeacherManagementPlatformPage.tsx')
    academic_bulk = text('frontend/lib/academicBulk.ts')
    assert 'CmsTeacherReportArtifactBar' not in page
    assert 'enterprise-page-identity__actions' not in page
    assert 'display: none !important' not in page
    assert '/academic/training/teacher-reports/latest' in api
    assert '/academic/training/teacher-reports/latest/download' in api
    assert 'downloadLatestTeacherReportArtifact' in management
    assert 'getLatestTeacherReportArtifact' in management
    assert 'artifactDownloading ? "Đang tải Excel..." : "Tải Excel"' in management
    assert 'Đồng bộ full CMS' in management
    assert 'Cập nhật điểm' in management
    assert 'syncLearning: false' in management
    assert 'refreshLatestAcademicScores' in management
    assert "import { API, apiFetch }" in academic_bulk
    assert 'await apiFetch(' in academic_bulk
