from __future__ import annotations

from app.worker import celery_app


def _route(task_name: str) -> str | None:
    routes = dict(celery_app.conf.task_routes or {})
    route = routes.get(task_name) or {}
    return route.get("queue")


def test_user_triggered_sync_tasks_use_fast_lane():
    assert _route("bank_release_publish_task") == "sync-fast"
    assert _route("bank_quiz_create_task") == "sync-fast"
    assert _route("academic_class_sync_task") == "sync-fast"
    assert _route("academic_teacher_report_watchdog_task") == "sync-fast"


def test_bulk_academic_tasks_use_bulk_lane():
    assert _route("academic_ap_sync_task") == "sync-bulk"
    assert _route("academic_learning_refresh_filter_task") == "sync-bulk"
    assert _route("academic_sync_all_student_scores_task") == "sync-bulk"
    assert _route("academic_subject_auto_map_all_sync_task") == "sync-bulk"
    assert _route("academic_subject_catalog_refresh_task") == "sync-bulk"
    assert _route("academic_daily_score_report_parent_task") == "sync-bulk"
    assert _route("academic_ap_03_schedule_task") == "sync-bulk"
    assert _route("academic_ap_03_followup_task") == "sync-bulk"
