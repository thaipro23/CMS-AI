from pathlib import Path


def _root() -> Path:
    return Path(__file__).resolve().parents[3]


def test_data_quality_guard_routes_and_backfill_jobs_exist():
    route = (_root() / 'backend' / 'app' / 'api' / 'routes' / 'learning_analytics.py').read_text(encoding='utf-8')
    assert "@router.get('/ops/data-quality')" in route
    assert "@router.get('/backfill/plan')" in route
    assert "@router.post('/backfill/jobs')" in route
    assert "analytics.backfill.enqueue" in route
    assert "signals_only_not_violation" in route
    assert "allowed_class_ids=allowed_class_ids" in route


def test_data_quality_service_is_snapshot_only_and_has_readiness_codes():
    service = (_root() / 'backend' / 'app' / 'services' / 'learning_analytics' / 'analytics_core_service.py').read_text(encoding='utf-8')
    assert "def analytics_data_quality_report" in service
    assert "def analytics_backfill_plan" in service
    assert "TRACKING_LOG_NOT_MOUNTED" in service
    assert "MISSING_COURSE_MAPPING" in service
    assert "MISSING_SESSION_STRUCTURE" in service
    assert "NO_BEHAVIOR_SNAPSHOT" in service
    assert "STALE_BEHAVIOR_SNAPSHOT" in service
    start = service.index('    def analytics_data_quality_report(')
    end = service.index('    def analytics_backfill_plan', start)
    body = service[start:end]
    assert 'TrackingLogReader(' not in body
    assert 'Path(file_path).read' not in body
    assert 'AnalyticsLearningBehaviorSnapshot' in body
    assert 'AnalyticsCourseSession' in body


def test_health_and_frontend_surface_data_quality_guard():
    health = (_root() / 'backend' / 'app' / 'api' / 'routes' / 'health.py').read_text(encoding='utf-8')
    api = (_root() / 'frontend' / 'lib' / 'api.ts').read_text(encoding='utf-8')
    types = (_root() / 'frontend' / 'types' / 'index.ts').read_text(encoding='utf-8')
    page = (_root() / 'frontend' / 'app' / 'analytics' / 'learning' / 'page.tsx').read_text(encoding='utf-8')
    assert 'data_quality_readiness' in health
    assert 'getAnalyticsDataQualityReport' in api
    assert 'getAnalyticsBackfillPlan' in api
    assert 'enqueueAnalyticsBackfillJobs' in api
    assert 'AnalyticsDataQualityReport' in types
    assert 'AnalyticsBackfillPlanResponse' in types
    assert 'Trạng thái dữ liệu' in page
    assert 'Backfill học online' in page
    assert 'Không đọc raw log khi mở dashboard' in page


def test_config_exposes_snapshot_stale_hours():
    config = (_root() / 'backend' / 'app' / 'core' / 'config.py').read_text(encoding='utf-8')
    env = (_root() / '.env.production.example').read_text(encoding='utf-8')
    assert 'analytics_snapshot_stale_hours' in config
    assert 'ANALYTICS_SNAPSHOT_STALE_HOURS=168' in env
