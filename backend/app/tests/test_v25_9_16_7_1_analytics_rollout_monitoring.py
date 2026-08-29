from pathlib import Path


def _root() -> Path:
    return Path(__file__).resolve().parents[3]


def test_rollout_and_monitoring_routes_exist():
    route = (_root() / 'backend' / 'app' / 'api' / 'routes' / 'learning_analytics.py').read_text(encoding='utf-8')
    service = (_root() / 'backend' / 'app' / 'services' / 'learning_analytics' / 'analytics_core_service.py').read_text(encoding='utf-8')
    health = (_root() / 'backend' / 'app' / 'api' / 'routes' / 'health.py').read_text(encoding='utf-8')
    assert "@router.get('/ops/rollout-control')" in route
    assert "@router.get('/ops/monitoring')" in route
    assert 'def rollout_control_report' in service
    assert 'def analytics_monitoring_report' in service
    assert 'rollout_status' in health
    assert 'monitoring_status' in health
    assert 'signals_only_not_violation' in service


def test_rollout_is_env_only_and_uses_existing_schema():
    service = (_root() / 'backend' / 'app' / 'services' / 'learning_analytics' / 'analytics_core_service.py').read_text(encoding='utf-8')
    start = service.index('    def rollout_control_report(')
    end = service.index('    def analytics_monitoring_report', start)
    body = service[start:end]
    assert 'AcademicClass' in body
    assert 'AcademicClassStudent' in body
    assert 'AnalyticsLearningBehaviorSnapshot' in body
    assert 'AnalyticsCourseSession' in body
    assert 'AnalyticsRollout' not in body
    assert 'AcademicClassSyncJob(' not in body
    assert 'ANALYTICS_ROLLOUT' not in ''.join(p.name for p in (_root() / 'backend' / 'alembic' / 'versions').glob('*rollout*'))


def test_monitoring_is_snapshot_only_and_detects_stuck_jobs():
    service = (_root() / 'backend' / 'app' / 'services' / 'learning_analytics' / 'analytics_core_service.py').read_text(encoding='utf-8')
    start = service.index('    def analytics_monitoring_report(')
    end = service.index('    def analytics_data_quality_report', start)
    body = service[start:end]
    assert 'TrackingLogReader(' not in body
    assert 'Path(file_path).read' not in body
    assert 'STUCK_ANALYTICS_JOBS' in body
    assert 'STALE_BEHAVIOR_SNAPSHOTS' in body
    assert 'SCHEDULER_DISABLED' in body
    assert 'INGEST_STALE' in body
    assert 'analytics_monitoring_stuck_job_minutes' in body


def test_rollout_guards_backfill_and_export():
    route = (_root() / 'backend' / 'app' / 'api' / 'routes' / 'learning_analytics.py').read_text(encoding='utf-8')
    assert 'ANALYTICS_ROLLOUT_BACKFILL_DISABLED' in route
    assert 'ANALYTICS_CLASS_NOT_IN_ROLLOUT' in route
    assert 'CLASS_NOT_IN_ROLLOUT' in route
    assert 'ANALYTICS_ROLLOUT_EXPORT_DISABLED' in route
    assert 'HTTPException(status_code=409' in route


def test_frontend_and_smoke_surface_rollout_monitoring():
    page = (_root() / 'frontend' / 'app' / 'analytics' / 'learning' / 'page.tsx').read_text(encoding='utf-8')
    api = (_root() / 'frontend' / 'lib' / 'api.ts').read_text(encoding='utf-8')
    types = (_root() / 'frontend' / 'types' / 'index.ts').read_text(encoding='utf-8')
    smoke = (_root() / 'scripts' / 'smoke-test-prod.sh').read_text(encoding='utf-8')
    rollout_script = (_root() / 'scripts' / 'analytics-rollout-monitor.sh').read_text(encoding='utf-8')
    env = (_root() / '.env.production.example').read_text(encoding='utf-8')
    assert 'getAnalyticsRolloutControl' in api
    assert 'getAnalyticsMonitoring' in api
    assert 'AnalyticsRolloutControlReport' in types
    assert 'AnalyticsMonitoringReport' in types
    assert 'Rollout' in page
    assert 'Monitoring' in page
    assert '/api/analytics/ops/rollout-control' in smoke
    assert '/api/analytics/ops/monitoring' in smoke
    assert '/analytics/ops/rollout-control' in rollout_script
    assert '/analytics/ops/monitoring' in rollout_script
    assert 'FAIL_ON_BLOCKERS' in rollout_script
    assert 'ANALYTICS_ROLLOUT_MODE=production' in env
    assert 'ANALYTICS_MONITORING_STUCK_JOB_MINUTES=60' in env
