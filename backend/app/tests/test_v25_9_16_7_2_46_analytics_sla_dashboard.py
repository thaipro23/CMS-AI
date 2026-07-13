from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
VERSION = '25.9.16.7.2.64.12'
TITLE = 'Bank Release Publish Reliability + Rollback QA'


def read(path: str) -> str:
    return (ROOT / path).read_text()


def test_version_and_run_docs_are_synced_to_46():
    assert f"app_version: str = '{VERSION}'" in read('backend/app/core/config.py')
    assert f'"version": "{VERSION}"' in read('frontend/package.json')
    assert f'NEXT_PUBLIC_APP_VERSION: ${{APP_VERSION:-{VERSION}}}' in read('docker-compose.prod.yml')
    assert f"'{VERSION}'" in read('frontend/components/layout/AppShell.tsx')
    assert f'# v{VERSION} — {TITLE}' in read('RUN_CURRENT.md')
    assert f'# v{VERSION} — {TITLE}' in read('RUN_V25_9_16_7_2_53.md')
    assert read('CHANGELOG.md').startswith(f'## v{VERSION} — {TITLE}')


def test_backend_has_read_only_sla_endpoint_and_report():
    route = read('backend/app/api/routes/learning_analytics.py')
    service = read('backend/app/services/learning_analytics/analytics_core_service.py')
    assert "@router.get('/ops/sla')" in route
    assert 'def analytics_sla_dashboard(' in route
    assert 'analytics_sla_report(allowed_class_ids=allowed_class_ids, limit=limit)' in route
    assert 'def analytics_sla_report(' in service
    assert 'does not\n        scan tracking.log' in service or 'does not scan tracking.log' in service
    assert 'classes_needing_snapshot' in service
    assert 'recalculate_completed_last_hour' in service
    assert 'post_ingest_recalculate' in service


def test_sla_env_controls_exist_without_new_migration():
    config = read('backend/app/core/config.py')
    env = read('.env.production.example') + read('.env.example')
    assert 'analytics_sla_ingest_target_seconds' in config
    assert 'analytics_sla_snapshot_target_seconds' in config
    assert 'analytics_sla_max_queued_jobs' in config
    assert 'ANALYTICS_SLA_INGEST_TARGET_SECONDS=300' in env
    assert 'ANALYTICS_SLA_SNAPSHOT_TARGET_SECONDS=3600' in env
    assert 'ANALYTICS_SLA_CLASS_GAP_LIMIT=20' in env
    assert '0053_' not in ''.join(p.name for p in (ROOT / 'backend/alembic/versions').iterdir())


def test_frontend_surfaces_sla_panel_on_analytics_learning():
    page = read('frontend/app/analytics/learning/page.tsx')
    api = read('frontend/lib/api.ts')
    types = read('frontend/types/index.ts')
    css = read('frontend/app/globals.css')
    assert 'getAnalyticsSlaReport' in api
    assert 'export type AnalyticsSlaReport' in types
    assert 'const [slaReport, setSlaReport]' in page
    assert 'SLA vận hành analytics' in page
    assert 'classes_needing_snapshot' in page
    assert '.analytics-sla-panel' in css
    assert 'v25.9.16.7.2.64.12 — Bank Release Publish Reliability + Rollback QA' in css
