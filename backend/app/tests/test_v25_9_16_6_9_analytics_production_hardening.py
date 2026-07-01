from pathlib import Path


def _root() -> Path:
    return Path(__file__).resolve().parents[3]


def test_production_readiness_route_and_health_are_exposed():
    route = (_root() / 'backend' / 'app' / 'api' / 'routes' / 'learning_analytics.py').read_text(encoding='utf-8')
    health = (_root() / 'backend' / 'app' / 'api' / 'routes' / 'health.py').read_text(encoding='utf-8')
    assert "@router.get('/ops/production-readiness')" in route
    assert 'production_readiness_report(allowed_class_ids=allowed_class_ids)' in route
    assert 'production_readiness' in health
    assert 'ready_for_production' in health
    assert 'production_blocker_count' in health
    assert 'signals_only_not_violation' in health


def test_service_has_production_readiness_and_enqueue_guards():
    service = (_root() / 'backend' / 'app' / 'services' / 'learning_analytics' / 'analytics_core_service.py').read_text(encoding='utf-8')
    assert 'def production_readiness_report' in service
    assert 'def analytics_enqueue_guard' in service
    assert 'def analytics_ingest_enqueue_guard' in service
    assert 'TRACKING_LOG_NOT_MOUNTED' in service
    assert 'SCHEDULER_DISABLED' in service
    assert 'NO_TRACKING_EVENTS_INGESTED' in service
    assert 'NO_BEHAVIOR_SNAPSHOTS' in service
    assert 'TOO_MANY_ACTIVE_ANALYTICS_JOBS' in service
    start = service.index('    def production_readiness_report(')
    end = service.index('    def ops_status', start)
    body = service[start:end]
    assert 'TrackingLogReader(' not in body
    assert 'Path(file_path).read' not in body
    assert 'AnalyticsTrackingEvent.id' in body
    assert 'AnalyticsLearningBehaviorSnapshot.id' in body


def test_routes_limit_enqueue_and_export_for_production():
    route = (_root() / 'backend' / 'app' / 'api' / 'routes' / 'learning_analytics.py').read_text(encoding='utf-8')
    service = (_root() / 'backend' / 'app' / 'services' / 'learning_analytics' / 'analytics_core_service.py').read_text(encoding='utf-8')
    assert 'analytics_backfill_max_jobs_per_request' in route
    assert 'analytics_backfill_max_active_jobs' in service
    assert 'HTTPException(status_code=409' in route
    assert 'analytics_recalculate_max_students_per_job' in route
    assert 'analytics_export_max_rows' in service
    assert '.limit(max_rows).all()' in service
    assert 'Giới hạn xuất tối đa' in service


def test_config_env_and_smoke_include_production_hardening():
    config = (_root() / 'backend' / 'app' / 'core' / 'config.py').read_text(encoding='utf-8')
    env = (_root() / '.env.production.example').read_text(encoding='utf-8')
    smoke = (_root() / 'scripts' / 'smoke-test-prod.sh').read_text(encoding='utf-8')
    assert 'analytics_backfill_max_jobs_per_request' in config
    assert 'analytics_recalculate_enqueue_cooldown_seconds' in config
    assert 'analytics_ingest_enqueue_cooldown_seconds' in config
    assert 'analytics_export_max_rows' in config
    assert 'ANALYTICS_BACKFILL_MAX_JOBS_PER_REQUEST=25' in env
    assert 'ANALYTICS_EXPORT_MAX_ROWS=50000' in env
    assert '/api/analytics/ops/production-readiness' in smoke
    assert '/tmp/analytics-production-readiness-smoke.json' in smoke


def test_frontend_surfaces_production_readiness():
    page = (_root() / 'frontend' / 'app' / 'analytics' / 'learning' / 'page.tsx').read_text(encoding='utf-8')
    api = (_root() / 'frontend' / 'lib' / 'api.ts').read_text(encoding='utf-8')
    types = (_root() / 'frontend' / 'types' / 'index.ts').read_text(encoding='utf-8')
    assert 'getAnalyticsProductionReadiness' in api
    assert 'AnalyticsProductionReadinessReport' in types
    assert 'getAnalyticsProductionReadiness(headers)' in page
    assert 'Production readiness' in page
    assert 'Sẵn sàng production' in page
    assert 'Chưa sẵn sàng production' in page
    assert 'Cần xử lý trước production' in page
