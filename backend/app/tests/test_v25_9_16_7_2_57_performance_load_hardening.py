from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
VERSION = '25.9.16.7.2.64.12'
TITLE = 'Performance Load Hardening'


def text(path: str) -> str:
    return (ROOT / path).read_text(encoding='utf-8')


def test_v57_version_sync_and_no_new_migration() -> None:
    targets = [
        'backend/app/core/config.py',
        'frontend/package.json',
        'frontend/package-lock.json',
        'frontend/Dockerfile',
        'docker-compose.prod.yml',
        '.env.example',
        '.env.production.example',
        'frontend/components/layout/AppShell.tsx',
        'README.md',
        'RUN_CURRENT.md',
        'scripts/claude-code-review-pack.sh',
        'scripts/uat-build-gate.sh',
        'scripts/uat-runtime-verify.sh',
        'scripts/performance-readiness-report.sh',
    ]
    for target in targets:
        assert VERSION in text(target), target
    migrations = [p.name for p in (ROOT / 'backend/alembic/versions').glob('*.py')]
    assert '0052_v25_9_16_7_2_27_learning_behavior_logic_calibration.py' in migrations
    assert not any(name.startswith('0053_') or name.startswith('0054_') for name in migrations)


def test_v57_performance_readiness_endpoint_is_read_only() -> None:
    route = text('backend/app/api/routes/health.py')
    service = text('backend/app/services/performance_readiness.py')
    assert "/health/performance-readiness" in route and "PerformanceReadinessReport" in route
    assert 'PerformanceReadinessService(db).performance_readiness_report()' in route
    assert 'read_only_no_query_plan_execution_no_mutation' in service
    assert 'Không scan raw tracking.log trong request' in service
    forbidden = ['EXPLAIN ANALYZE', 'analytics_ingest_task.delay', 'analytics_class_recalculate_task.delay', '.delete(', '.update(']
    for term in forbidden:
        assert term not in service


def test_v57_performance_gate_checks_load_risks() -> None:
    service = text('backend/app/services/performance_readiness.py')
    for token in [
        'ANALYTICS_DASHBOARD_MAX_PAGE_SIZE',
        'BANK_SEARCH_MAX_RESULTS',
        'OPENEDX_CONNECTOR_MAX_BATCH_SIZE',
        'ANALYTICS_POST_INGEST_MAX_JOBS_PER_RUN',
        'CRITICAL_INDEXES',
        'ix_analytics_events_course_user_time',
        'ix_ai_questions_bank_status_created_id',
        'pg_stat_user_tables',
        'ACTIVE_JOB_PRESSURE',
        'FAILED_JOB_LAST_HOUR',
    ]:
        assert token in service


def test_v57_analytics_ui_surfaces_performance_panel() -> None:
    page = text('frontend/app/analytics/learning/page.tsx')
    api = text('frontend/lib/api.ts')
    types = text('frontend/types/index.ts')
    css = text('frontend/app/globals.css')
    assert 'getPerformanceReadiness' in api
    assert 'PerformanceReadinessReport' in types
    assert 'Hiệu năng vận hành' in page
    assert 'analytics-performance-readiness-panel' in page
    assert 'performanceReadinessLabel' in page
    assert 'analytics-performance-readiness-panel' in css


def test_v57_scripts_and_review_pack_cover_performance_gate() -> None:
    report = text('scripts/performance-readiness-report.sh')
    runtime = text('scripts/uat-runtime-verify.sh')
    review = text('scripts/claude-code-review-pack.sh')
    assert '/health/performance-readiness' in report
    assert 'PERFORMANCE_READINESS_SUMMARY.md' in report
    assert '/health/performance-readiness' in runtime
    assert 'performance-readiness.json' in runtime
    assert 'PerformanceReadinessService' in review
    assert 'scripts/performance-readiness-report.sh' in review
    banned = ['curl -X POST', 'curl -X DELETE', 'rm -rf', 'DROP TABLE', 'TRUNCATE TABLE']
    for term in banned:
        assert term not in report
