from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]


def text(path: str) -> str:
    target = ROOT / path
    return target.read_text(encoding='utf-8') if target.exists() else ''


def test_daily_teacher_report_worker_entry_replaces_legacy_tasks_and_runs_at_0500_vn():
    source = text('backend/app/worker_entry.py')
    assert "Asia/Ho_Chi_Minh" in source
    assert "crontab(hour=5, minute=0)" in source
    assert "academic_sync_all_student_scores_task" in source
    assert "academic_teacher_report_job_task" in source
    assert "academic-teacher-report-watchdog" in source


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
    assert 'updated_at' not in health


def test_latest_management_artifact_api_is_download_only_and_reports_vn_time():
    source = text('backend/app/api/routes/teacher_report_artifacts.py')
    assert "/training/teacher-reports/latest" in source
    assert "/training/teacher-reports/latest/download" in source
    assert "scheduled_export_excel" in source
    assert "Asia/Ho_Chi_Minh" in source
    assert "generated_at" in source
    assert "source_synced_at" in source
    assert "refresh_training_teacher_learning_data" not in source


def test_daily_parent_waits_for_terminal_children_before_scheduled_exports():
    source = text('backend/app/services/academic/daily_teacher_report_runtime.py')
    parent = source.split('def run_daily_score_report_parent(', 1)[1].split('def _job_request(', 1)[0]
    assert "child_job_ids" in parent
    assert "terminal_count" in parent
    assert "if terminal_count < target_count" in parent
    assert "_create_scheduled_export_job" in parent
    assert parent.index("if terminal_count < target_count") < parent.index("_create_scheduled_export_job")


def test_cms_teacher_management_hides_legacy_job_actions_and_uses_prebuilt_artifact_bar():
    page = text('frontend/app/teacher-management/cms/page.tsx')
    api = text('frontend/lib/teacherReportArtifacts.ts')
    bar = text('frontend/components/training/CmsTeacherReportArtifactBar.tsx')
    assert 'CmsTeacherReportArtifactBar' in page
    assert 'enterprise-page-identity__actions' in page
    assert 'display: none !important' in page
    assert '/academic/training/teacher-reports/latest' in api
    assert '/academic/training/teacher-reports/latest/download' in api
    assert "timeZone: 'Asia/Ho_Chi_Minh'" in bar
    assert 'Tải Excel' in bar
