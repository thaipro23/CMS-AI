from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
VERSION = '25.9.16.7.2.64.13'


def text(path: str) -> str:
    return (ROOT / path).read_text(encoding='utf-8')


def test_v60_version_sync_and_docs():
    assert f"app_version: str = '{VERSION}'" in text('backend/app/core/config.py')
    assert f'"version": "{VERSION}"' in text('frontend/package.json')
    assert f'NEXT_PUBLIC_APP_VERSION: ${{APP_VERSION:-{VERSION}}}' in text('docker-compose.prod.yml')
    assert f"'{VERSION}'" in text('frontend/components/layout/AppShell.tsx')
    assert 'Question Bank Quiz Creation/Auto-map Workflow Split' in text('README.md')
    assert 'RUN_V25_9_16_7_2_64_13.md' in text('README.md')
    assert text('CHANGELOG.md').startswith('## v25.9.16.7.2.64.13 — Question Bank Quiz Creation/Auto-map Workflow Split')


def test_v60_pilot_operations_backend_is_read_only():
    service = text('backend/app/services/pilot_operations.py')
    assert 'class PilotOperationsService' in service
    assert 'read_only_pilot_operations_runbook_no_mutation' in service
    assert 'ReleaseCandidateService(self.db).report' in service
    assert 'rollback_triggers' in service
    assert 'monitoring_cadence' in service
    assert 'Không enqueue job hoặc recalculate' in service
    assert 'mutate data' in service.lower() or 'Không mutate database' in service
    route = text('backend/app/api/routes/health.py')
    assert "/health/pilot-operations" in route and "PilotOperationsReport" in route
    assert 'PilotOperationsService(db).report' in route
    assert '_allowed_class_ids_for_analytics(db, user)' in route


def test_v60_frontend_panel_and_api_contract():
    page = text('frontend/app/analytics/learning/page.tsx')
    api = text('frontend/lib/api.ts')
    types = text('frontend/types/index.ts')
    css = text('frontend/app/globals.css')
    assert 'getPilotOperationsReadiness' in api
    assert '/health/pilot-operations' in api
    assert 'PilotOperationsReport' in types
    assert 'Pilot operations runbook' in page
    assert 'rollback_triggers' in page
    assert 'analytics-pilot-operations-panel' in css


def test_v60_scripts_and_review_pack_cover_runbook():
    script = text('scripts/pilot-operations-runbook.sh')
    assert 'health/pilot-operations' in script
    assert 'PILOT_OPERATIONS_RUNBOOK.md' in script
    assert 'Rollback Triggers' in script
    assert 'Read-only Guarantees' in script
    assert 'scripts/pilot-operations-runbook.sh' in text('scripts/uat-build-gate.sh')
    assert 'PILOT_OPERATIONS' in text('scripts/uat-runtime-verify.sh')
    review = text('scripts/claude-code-review-pack.sh')
    assert 'pilot-operations-runbook.sh' in review
    assert 'GET /api/health/pilot-operations' in review


def test_v60_no_new_alembic_revision():
    versions = list((ROOT / 'backend/alembic/versions').glob('0053*.py')) + list((ROOT / 'backend/alembic/versions').glob('0054*.py'))
    assert versions == []
    assert (ROOT / 'backend/alembic/versions/0052_v25_9_16_7_2_27_learning_behavior_logic_calibration.py').exists()
