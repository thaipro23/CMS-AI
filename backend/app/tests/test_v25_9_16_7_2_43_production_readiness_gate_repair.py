from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
VERSION = '25.9.16.7.2.64.13'
TITLE = 'Bank Release Publish Reliability + Rollback QA'


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding='utf-8')


def test_v43_version_docs_and_changelog_are_current():
    assert f"app_version: str = '{VERSION}'" in read('backend/app/core/config.py')
    assert f'"version": "{VERSION}"' in read('frontend/package.json')
    assert f'NEXT_PUBLIC_APP_VERSION: ${{APP_VERSION:-{VERSION}}}' in read('docker-compose.prod.yml')
    assert f"process.env.NEXT_PUBLIC_APP_VERSION || '{VERSION}'" in read('frontend/components/layout/AppShell.tsx')
    assert f'# v{VERSION} — {TITLE}' in read('RUN_CURRENT.md')
    assert f'# v{VERSION} — {TITLE}' in read('RUN_V25_9_16_7_2_53.md')
    assert read('CHANGELOG.md').startswith(f'## v{VERSION} — {TITLE}')


def test_v43_readiness_service_is_actionable_and_deduped():
    service = read('backend/app/services/learning_analytics/analytics_core_service.py')
    assert 'def _production_readiness_issue' in service
    assert 'def _normalize_production_issue' in service
    assert 'def _dedupe_production_issues' in service
    assert "'stage_status': stage_status" in service
    assert "'summary_label':" in service
    assert "'primary_blocker': primary_blocker" in service
    assert "'sections': section_items" in service
    assert "'blockers': blockers" in service
    assert "'warnings': warnings" in service
    assert "'can_pilot': ready" in service
    assert "'can_broad_rollout': stage_status == 'READY'" in service
    assert "key = (category, code)" in service
    assert "'NO_BEHAVIOR_SNAPSHOTS'" in service
    assert "severity='WARNING'" in service
    assert 'Thiếu snapshot là trạng thái dữ liệu' in service


def test_v43_health_readiness_endpoint_exists_and_is_safe():
    health = read('backend/app/api/routes/health.py')
    assert "@router.get('/health/readiness')" in health
    assert 'production_readiness_report()' in health
    assert 'primary_blocker' in health
    assert 'sections' in health
    assert 'next_actions' in health
    assert "require_permission('view_dashboard')" in health


def test_v43_frontend_replaces_opaque_readiness_banner():
    page = read('frontend/app/analytics/learning/page.tsx')
    types = read('frontend/types/index.ts')
    css = read('frontend/app/globals.css')
    assert 'analytics-production-readiness-panel' in page
    assert 'readinessTone(productionReadiness)' in page
    assert 'readinessLabel(productionReadiness)' in page
    assert 'productionReadiness.primary_blocker' in page
    assert 'analytics-readiness-issue-list' in page
    assert 'Cần xử lý trước production:' not in page
    assert 'stage_status?' in types
    assert 'summary_label?' in types
    assert 'primary_blocker?' in types
    assert 'sections?' in types
    assert 'command?: string | null' in types
    assert 'v25.9.16.7.2.64.13 — analytics production readiness gate repair' in css


def test_v43_no_migration_added():
    versions = sorted((ROOT / 'backend/alembic/versions').glob('*.py'))
    assert versions[-1].name == '0052_v25_9_16_7_2_27_learning_behavior_logic_calibration.py'
