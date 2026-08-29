from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
VERSION = '25.9.16.7.2.64.13'


def text(path: str) -> str:
    return (ROOT / path).read_text(encoding='utf-8')


def test_v64_version_sync_and_docs():
    assert f"app_version: str = '{VERSION}'" in text('backend/app/core/config.py')
    assert f'"version": "{VERSION}"' in text('frontend/package.json')
    assert f'NEXT_PUBLIC_APP_VERSION: ${{APP_VERSION:-{VERSION}}}' in text('docker-compose.prod.yml')
    assert f"'{VERSION}'" in text('frontend/components/layout/AppShell.tsx')
    assert 'Question Bank Quiz Creation/Auto-map Workflow Split' in text('README.md')
    assert 'RUN_V25_9_16_7_2_64_13.md' in text('README.md')
    assert text('CHANGELOG.md').startswith('## v25.9.16.7.2.64.13 — Academic AP Sync + External Assignment Workflow Split')


def test_v64_backend_final_gate_contract_is_read_only():
    route = text('backend/app/api/routes/health.py')
    service = text('backend/app/services/production_pilot_final.py')
    schema = text('backend/app/schemas/readiness.py')
    assert "@router.get('/health/production-pilot-final', response_model=ProductionPilotFinalReport)" in route
    assert 'ProductionPilotFinalService(db).report' in route
    assert 'class ProductionPilotFinalService' in service
    assert 'read_only_production_pilot_final_gate_no_mutation' in service
    assert 'Không chạy load test trong API request' in service
    assert 'Không mutate database' in service
    assert 'PilotOperationsService(self.db).report' in service
    assert 'class ProductionPilotFinalReport' in schema
    forbidden = ['.delete(', '.update(', '.add(', '.commit(', '.flush(', '.delay(', 'requests.', 'httpx.']
    for term in forbidden:
        assert term not in service


def test_v64_frontend_ops_readiness_final_gate():
    page = text('frontend/app/ops/readiness/page.tsx')
    api = text('frontend/lib/api/readiness.ts')
    types = text('frontend/types/readiness.ts')
    assert 'getProductionPilotFinal' in api
    assert '/health/production-pilot-final' in api
    assert 'ProductionPilotFinalReport' in types
    assert 'Production pilot final' in page
    assert 'final_checks' in page


def test_v64_scripts_cover_final_load_rollback_publish_verify():
    scripts = {
        'scripts/production-pilot-final-gate.sh': ['health/production-pilot-final', 'PRODUCTION_PILOT_FINAL_SUMMARY.md'],
        'scripts/load-test-hot-endpoints.sh': ['LOAD_TEST_HOT_ENDPOINTS_SUMMARY.md', 'latency.tsv'],
        'scripts/rollback-drill-verify.sh': ['ROLLBACK_DRILL_SUMMARY.md', 'dry-run only'],
        'scripts/openedx-publish-verify.sh': ['OPENEDX_PUBLISH_VERIFY_SUMMARY.md', 'publish-audit'],
    }
    for path, needles in scripts.items():
        body = text(path)
        for needle in needles:
            assert needle in body, (path, needle)
    build_gate = text('scripts/uat-build-gate.sh')
    runtime = text('scripts/uat-runtime-verify.sh')
    review = text('scripts/claude-code-review-pack.sh')
    for script in scripts:
        assert script in build_gate
        assert script in review
    assert 'PRODUCTION_PILOT_FINAL' in runtime


def test_v64_no_new_alembic_revision_and_release_zip_hygiene_contract():
    versions = [p.name for p in (ROOT / 'backend/alembic/versions').glob('*.py')]
    assert '0052_v25_9_16_7_2_27_learning_behavior_logic_calibration.py' in versions
    assert not any(name.startswith('0053') or name.startswith('0054') for name in versions)
    assert 'find . -type d' in text('scripts/rollback-drill-verify.sh') or 'dry-run only' in text('scripts/rollback-drill-verify.sh')
