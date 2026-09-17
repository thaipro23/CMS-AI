from __future__ import annotations

from celery.schedules import crontab

from app.worker import celery_app
from app.services.academic.daily_teacher_report_runtime import register_daily_teacher_report_tasks
from app.services.academic.student_management_runtime import register_student_management_runtime_tasks


# Register production-safe replacements under the legacy public task names so
# existing API enqueue code does not need to know about the runtime split.
register_daily_teacher_report_tasks(celery_app)
register_student_management_runtime_tasks(celery_app)

# Make routing explicit for the new coordinator/watchdog tasks.
_routes = dict(getattr(celery_app.conf, 'task_routes', {}) or {})
_routes.update({
    'academic_sync_all_student_scores_task': {'queue': 'sync'},
    'academic_daily_score_report_parent_task': {'queue': 'sync'},
    'academic_teacher_report_watchdog_task': {'queue': 'sync'},
    'academic_teacher_report_job_task': {'queue': 'exports'},
})
celery_app.conf.task_routes = _routes

# The 05:00 wall-clock schedule is Vietnam time. Celery itself already uses
# Asia/Ho_Chi_Minh; keep it explicit here because this pipeline is operator-facing.
celery_app.conf.timezone = 'Asia/Ho_Chi_Minh'
celery_app.conf.enable_utc = True

_beat_schedule = dict(getattr(celery_app.conf, 'beat_schedule', {}) or {})
_beat_schedule['academic-score-sync-all-students'] = {
    'task': 'academic_sync_all_student_scores_task',
    'schedule': crontab(hour=5, minute=0),
}
_beat_schedule['academic-teacher-report-watchdog'] = {
    'task': 'academic_teacher_report_watchdog_task',
    'schedule': 60.0,
}
celery_app.conf.beat_schedule = _beat_schedule

# Keep watchdog/coordinator bounded. The class-level learning sync and teacher/
# class live export retain their existing task limits in app.worker.
_annotations = dict(getattr(celery_app.conf, 'task_annotations', {}) or {})
_annotations.update({
    'academic_sync_all_student_scores_task': {'soft_time_limit': 540, 'time_limit': 600},
    'academic_daily_score_report_parent_task': {'soft_time_limit': 540, 'time_limit': 600},
    'academic_teacher_report_watchdog_task': {'soft_time_limit': 45, 'time_limit': 55},
})
celery_app.conf.task_annotations = _annotations
