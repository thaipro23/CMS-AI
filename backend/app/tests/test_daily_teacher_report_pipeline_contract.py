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


def test_ghost_job_detection_uses_progress_and_runtime_not_updated_at_only():
    source = text('backend/app/services/academic/daily_teacher_report_runtime.py')
    assert "progress_changed_at" in source
    assert "heartbeat_at" in source
    assert "max_runtime_seconds" in source
    assert "WORKER_HEARTBEAT_LOST" in source
    assert "JOB_PROGRESS_STALLED" in source
    assert "JOB_RUNTIME_EXCEEDED" in source


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
    assert "daily_score_report_pipeline" in source
    assert "child_job_ids" in source
    assert "terminal_count" in source
    assert "scheduled_export_excel" in source
    assert source.index("terminal_count") < source.index("scheduled_export_excel")
