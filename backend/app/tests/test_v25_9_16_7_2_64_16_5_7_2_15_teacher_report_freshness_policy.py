from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]


def text(path: str) -> str:
    return (ROOT / path).read_text(encoding='utf-8')


def test_teacher_report_jobs_refresh_live_cms_before_cache_or_excel():
    worker = text('backend/app/worker.py')
    task = worker.split("def academic_teacher_report_job_task(job_id: str):", 1)[1].split("@celery_app.task(name='analytics_ingest_task')", 1)[0]
    refresh_at = task.index('service.refresh_training_teacher_learning_data(')
    cache_at = task.index('service.rebuild_training_teacher_report_cache(')
    export_at = task.index('report = service.training_teacher_report(')
    assert refresh_at < cache_at
    assert refresh_at < export_at
    assert 'class_id=class_id' in task
    assert "strict=True" in task
    assert "Dừng báo cáo để không xuất dữ liệu điểm cũ" in text('backend/app/services/academic/teacher_report.py')
    assert "grade_preserved" in text('backend/app/services/academic_service.py')
    assert "snapshot.raw_json.get('grade_preserved') is True" in text('backend/app/services/academic/teacher_report.py')


def test_teacher_report_cache_job_is_platform_scoped_and_restored_after_reload():
    route = text('backend/app/api/routes/academic.py')
    api = text('frontend/lib/api.ts')
    page = text('frontend/app/teacher-management/TeacherManagementPlatformPage.tsx')
    assert "learning_platform: str = Query('cms', pattern='^(cms|udemy)$')" in route
    assert "learning_platform=learning_platform" in route
    assert 'filters.learningPlatform' in api
    assert 'params.set("learning_platform", filters.learningPlatform)' in api
    assert 'job.job_type === "rebuild_cache"' in page
    assert 'String(request.learning_platform || "cms") === platform' in page
    assert 'learningPlatform: platform' in page


def test_exam_policy_uses_final_day_only_and_progress_deadlines_are_warnings():
    policy = text('backend/app/services/training_policy_service.py')
    assert "quiz_rule': 'progress_deadlines_are_warnings_final_day_blocks_exam'" in policy
    assert "deadline_kind': 'progress_checkpoint'" in policy
    assert "status = 'progress_deadline_missed_not_100'" in policy
    assert "status = 'progress_deadline_missed_not_attempted'" in policy
    assert "status = 'completed_after_progress_deadline'" in policy
    assert 'final_day_expired = bool(exam_cutoff and today > exam_cutoff)' in policy
    assert "exam_cutoff_date" in policy
    assert "assignment_blocks_exam': False" in policy
    assert "elif not final_day_expired:" in policy
    assert "exam_label = 'Chưa bị cấm thi'" in policy
    assert "elif final_day_missing_full > 0:" in policy


def test_deadline_completion_requires_full_score_not_any_positive_score():
    service = text('backend/app/services/academic_service.py')
    body = service.split('def _completed_quiz_numbers_from_snapshot', 1)[1].split('def _quiz_numbers_from_component_item', 1)[0]
    assert 'normalized_percent >= 100.0' in body
    assert 'percent > 0' not in body


def test_teacher_report_live_refresh_time_limit_fits_redis_visibility_window():
    worker = text('backend/app/worker.py')
    config = text('backend/app/core/config.py')
    assert "'academic_teacher_report_job_task': {'soft_time_limit': 5400, 'time_limit': 5700}" in worker
    assert 'celery_broker_visibility_timeout_seconds: int = 7200' in config


def test_class_excel_export_is_exact_scope_fresh_and_teacher_accessible():
    route = text('backend/app/api/routes/academic.py')
    worker = text('backend/app/worker.py')
    report = text('backend/app/services/academic/teacher_report.py')
    api = text('frontend/lib/api.ts')
    page = text('frontend/app/student-management/classes/[classId]/page.tsx')

    assert "@router.post('/training/classes/{class_id}/export/jobs'" in route
    assert 'service.get_class_detail(user, class_id)' in route
    assert 'service.assert_can_access_class(user, class_id)' in route
    assert "'approved_class_id': class_id" in route
    assert 'class_id=class_id' in worker
    assert "raise PermissionError('Job xuất lớp vượt ngoài phạm vi lớp đã được duyệt khi enqueue.')" in worker
    assert "Lớp chưa ghép Course CMS; không thể xác nhận điểm mới nhất để xuất Excel." in report
    assert 'if not class_id and status_name in' in report
    assert 'createAcademicTrainingClassExportJob' in api
    assert 'Xuất Excel lớp' in page
    assert 'downloadAcademicTrainingTeacherReportJob' in page


def test_class_read_routes_use_academic_visibility_not_question_bank_permission():
    route = text('backend/app/api/routes/academic.py')
    for marker in [
        'def get_class_detail(',
        'def list_class_students(',
        'def get_class_mapping_summary(',
        'def get_class_learning_summary(',
        'def get_class_sync_job(',
        'def list_class_sync_jobs(',
    ]:
        block = route.split(marker, 1)[1].split('\n\n', 1)[0]
        assert 'Depends(_require_academic_view_permission)' in block
        assert "require_permission('view_questions')" not in block


def test_class_detail_exposes_official_final_day_with_block_fallback():
    service = text('backend/app/services/academic_service.py')
    schema = text('backend/app/schemas/academic.py')
    frontend_types = text('frontend/types/index.ts')
    class_page = text('frontend/app/student-management/classes/[classId]/page.tsx')
    assert "'exam_cutoff_date': cls.end_date or (block.end_date if block else None)" in service
    assert "'exam_cutoff_source': 'class_end_date' if cls.end_date" in service
    assert 'exam_cutoff_date: datetime | None = None' in schema
    assert 'exam_cutoff_date?: string | null' in frontend_types
    assert 'classInfo?.exam_cutoff_date ? `Ngày cuối xét cấm thi:' in class_page
