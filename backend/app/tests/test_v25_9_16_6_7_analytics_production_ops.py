from pathlib import Path


def _root() -> Path:
    return Path(__file__).resolve().parents[3]


def test_analytics_async_tasks_and_scheduler_are_registered():
    worker = (_root() / 'backend' / 'app' / 'worker.py').read_text(encoding='utf-8')
    assert "@celery_app.task(name='analytics_ingest_task')" in worker
    assert "@celery_app.task(name='analytics_class_recalculate_task')" in worker
    assert 'analytics_ingest_scheduler_enabled' in worker
    assert 'analytics-ingest-openedx-tracking-log' in worker
    assert "job.job_type != 'learning_analytics_recalculate'" in worker


def test_analytics_routes_have_job_endpoints_and_scope_guards():
    route = (_root() / 'backend' / 'app' / 'api' / 'routes' / 'learning_analytics.py').read_text(encoding='utf-8')
    assert "@router.post('/ingest/jobs')" in route
    assert "@router.get('/ops/status')" in route
    assert "@router.post('/classes/{class_id}/learning-behavior/jobs', response_model=AcademicClassSyncJobOut)" in route
    assert '_allowed_class_ids_for_analytics' in route
    assert 'AcademicService(db).assert_can_access_class(user, class_id)' in route
    assert 'allowed_class_ids=allowed_class_ids' in route
    assert 'signals_only_not_violation' in route


def test_analytics_dashboard_service_accepts_scope_filter_and_ops_status():
    service = (_root() / 'backend' / 'app' / 'services' / 'learning_analytics' / 'analytics_core_service.py').read_text(encoding='utf-8')
    assert "'version': '25.9.16.7.2.7'" in service
    assert 'def ops_status' in service
    assert 'safe_policy' in service
    assert 'allowed_class_ids: set[str] | None = None' in service
    assert 'AnalyticsLearningBehaviorSnapshot.class_id.in_' in service
    dashboard_start = service.index('    def learning_dashboard(')
    export_start = service.index('    def export_learning_behavior_csv', dashboard_start)
    assert 'allowed_class_ids=allowed_class_ids' in service[dashboard_start:export_start]


def test_health_and_smoke_cover_analytics_ops():
    health = (_root() / 'backend' / 'app' / 'api' / 'routes' / 'health.py').read_text(encoding='utf-8')
    smoke = (_root() / 'scripts' / 'smoke-test-prod.sh').read_text(encoding='utf-8')
    verify = (_root() / 'scripts' / 'production-build-verify.sh').read_text(encoding='utf-8')
    assert "@router.get('/health/analytics')" in health
    assert '/api/health/analytics' in smoke
    assert '/api/analytics/ops/status' in smoke
    assert '/api/health/analytics' in verify
    assert 'signals_only_not_violation' in smoke


def test_frontend_jobs_and_class_detail_use_async_analytics_jobs():
    jobs = (_root() / 'frontend' / 'app' / 'jobs' / 'page.tsx').read_text(encoding='utf-8')
    class_page = (_root() / 'frontend' / 'app' / 'student-management' / 'classes' / '[classId]' / 'page.tsx').read_text(encoding='utf-8')
    api = (_root() / 'frontend' / 'lib' / 'api.ts').read_text(encoding='utf-8')
    assert 'getAnalyticsOpsStatus' in jobs
    assert 'learning_analytics_recalculate' in jobs
    assert '<option value="analytics">Học online</option>' in jobs
    assert 'enqueueAnalyticsClassLearningBehaviorJob' in class_page
    assert 'Đã đưa tính lại học online vào hàng đợi' in class_page
    assert 'recalculateAnalyticsClassLearningBehavior(headers, classId, effectiveCourseId)' not in class_page
    assert 'enqueueAnalyticsIngestJob' in api
    assert 'enqueueAnalyticsClassLearningBehaviorJob' in api
