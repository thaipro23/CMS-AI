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


def test_03_scheduler_runs_ap_then_course_map_without_learning_sync_and_keeps_05_score_job():
    entry = _read('backend/app/worker.py')
    runtime = _read('backend/app/services/academic/student_management_runtime.py')

    assert 'register_student_management_runtime_tasks(celery_app)' in entry
    assert "crontab(hour=3, minute=0)" in runtime
    assert "academic_ap_03_schedule_task" in runtime
    assert "academic_ap_03_followup_task" in runtime
    assert "'sync_learning': False" in runtime

    # Existing score/Excel freshness pipeline stays at 05:00 Vietnam time.
    assert "'academic-score-sync-all-students'" in entry
    assert 'crontab(hour=5, minute=0)' in entry
