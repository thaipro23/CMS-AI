from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]


def _read(relative_path: str) -> str:
    return (ROOT / relative_path).read_text(encoding='utf-8')


def test_student_management_has_separate_course_map_and_latest_score_actions():
    page = _read('frontend/app/student-management/StudentManagementPlatformPage.tsx')
    api = _read('frontend/lib/academicBulk.ts')

    assert 'Tự động ghép Course' in page
    assert 'Lấy điểm mới nhất' in page
    assert 'syncLearning: false' in page
    assert 'refreshLatestAcademicScores' in page
    assert '/academic/subjects/learning/refresh/jobs' in api


def test_learning_refresh_is_a_separate_backend_route_and_learning_only_worker():
    router = _read('backend/app/api/router.py')
    route = _read('backend/app/api/routes/academic_learning_bulk.py')
    runtime = _read('backend/app/services/academic/student_management_runtime.py')

    assert 'academic_learning_bulk' in router
    assert "job_type='learning_refresh_filter'" in route
    assert "job_type='learning_sync'" in runtime
    assert "auto_map_course" not in route


def test_one_0100_scheduler_replaces_legacy_ap_and_score_publishers():
    worker = _read('backend/app/worker.py')
    runtime = _read('backend/app/services/academic/student_management_runtime.py')
    daily = _read('backend/app/services/academic/daily_academic_pipeline.py')

    assert 'register_student_management_runtime_tasks(celery_app)' in worker
    assert 'register_daily_teacher_report_tasks(celery_app)' in worker
    assert 'register_daily_academic_pipeline_tasks(celery_app)' in worker
    assert "crontab(hour=3, minute=0)" not in runtime
    assert "academic_ap_03_schedule_task" in runtime
    assert "academic_ap_03_followup_task" in runtime
    assert "'sync_learning': False" in runtime
    assert "'academic-score-sync-all-students'" not in worker
    assert 'crontab(hour=5, minute=0)' not in worker
    assert "crontab(hour=1, minute=0)" in daily
    assert "'academic-daily-pipeline-01-vn'" in daily


def test_academic_batch_window_is_four_in_config_and_k8s_worker():
    config = _read('backend/app/core/config.py')
    worker_manifest = _read('deploy/k8s/base/worker.yaml')
    env_example = _read('.env.production.example')

    assert 'academic_bulk_sync_dispatch_window: int = 4' in config
    assert 'value: "4"' in worker_manifest
    assert '--concurrency=${CELERY_CONCURRENCY:-4}' in worker_manifest
    assert 'ACADEMIC_BULK_SYNC_DISPATCH_WINDOW=4' in env_example
