from pathlib import Path


def _root() -> Path:
    return Path(__file__).resolve().parents[3]


def test_pilot_acceptance_route_service_and_script_exist():
    route = (_root() / 'backend' / 'app' / 'api' / 'routes' / 'learning_analytics.py').read_text(encoding='utf-8')
    service = (_root() / 'backend' / 'app' / 'services' / 'learning_analytics' / 'analytics_core_service.py').read_text(encoding='utf-8')
    script = (_root() / 'scripts' / 'analytics-pilot-acceptance.sh').read_text(encoding='utf-8')
    assert "@router.get('/ops/pilot-acceptance')" in route
    assert 'analytics.pilot_acceptance.view' in route
    assert 'def pilot_acceptance_report' in service
    assert 'ready_for_pilot' in service
    assert 'ready_for_broad_production' in service
    assert 'signals_only_not_violation' in service
    assert '/analytics/ops/pilot-acceptance' in script
    assert 'FAIL_ON_WARNINGS' in script


def test_pilot_acceptance_is_snapshot_only_and_uses_existing_schema():
    service = (_root() / 'backend' / 'app' / 'services' / 'learning_analytics' / 'analytics_core_service.py').read_text(encoding='utf-8')
    start = service.index('    def pilot_acceptance_report(')
    end = service.index('    def ops_status', start)
    body = service[start:end]
    assert 'TrackingLogReader(' not in body
    assert 'Path(file_path).read' not in body
    assert 'AnalyticsLearningBehaviorSnapshot' in body
    assert 'AnalyticsCourseSession' in body
    assert 'AnalyticsStudentVideoProgress' in body
    assert 'AcademicClassStudent' in body
    assert 'AcademicClassSyncJob(' not in body


def test_frontend_surfaces_pilot_acceptance_without_duplicate_select_options():
    page = (_root() / 'frontend' / 'app' / 'analytics' / 'learning' / 'page.tsx').read_text(encoding='utf-8')
    api = (_root() / 'frontend' / 'lib' / 'api.ts').read_text(encoding='utf-8')
    types = (_root() / 'frontend' / 'types' / 'index.ts').read_text(encoding='utf-8')
    assert 'getAnalyticsPilotAcceptance' in api
    assert 'AnalyticsPilotAcceptanceReport' in types
    assert 'Pilot acceptance' in page
    assert 'Pilot đạt' in page
    assert 'Pilot chưa đạt' in page
    assert 'pilotAcceptance.classes.slice' in page
    # Regression guard: v6.9 accidentally rendered the classification options twice.
    assert page.count('CLASSIFICATION_OPTIONS.map((option)') == 1


def test_smoke_test_and_docs_include_pilot_gate():
    smoke = (_root() / 'scripts' / 'smoke-test-prod.sh').read_text(encoding='utf-8')
    run = (_root() / 'RUN_V25_9_16_7_2.md').read_text(encoding='utf-8')
    ux = (_root() / 'UX_UI_CONTEXT_V25_9_16_7_2.md').read_text(encoding='utf-8')
    assert '/api/analytics/ops/pilot-acceptance' in smoke
    assert '/tmp/analytics-pilot-acceptance-smoke.json' in smoke
    assert 'analytics-pilot-acceptance.sh' in run
    assert 'Pilot acceptance' in ux
    assert 'không phải kết luận vi phạm' in run
