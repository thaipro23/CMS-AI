from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
VERSION = '25.9.16.7.2.64.12'


def text(path: str) -> str:
    return (ROOT / path).read_text(encoding='utf-8')


def test_v63_version_sync_and_docs():
    assert f"app_version: str = '{VERSION}'" in text('backend/app/core/config.py')
    assert f'"version": "{VERSION}"' in text('frontend/package.json')
    assert f'NEXT_PUBLIC_APP_VERSION: ${{APP_VERSION:-{VERSION}}}' in text('docker-compose.prod.yml')
    assert 'Question Bank Quiz Creation/Auto-map Workflow Split' in text('README.md')
    assert 'question-bank-quiz-creation-automap-workflow-split.zip' in text('RUN_CURRENT.md')
    assert text('CHANGELOG.md').startswith('## v25.9.16.7.2.64.12 — Question Bank Quiz Creation/Auto-map Workflow Split')


def test_v63_readiness_pydantic_contracts_are_wired_to_health_routes():
    schema = text('backend/app/schemas/readiness.py')
    health = text('backend/app/api/routes/health.py')
    assert 'class OperationReportBase' in schema
    for name in [
        'SecurityReadinessReport',
        'PerformanceReadinessReport',
        'QueryHotspotReport',
        'ReleaseCandidateReport',
        'PilotOperationsReport',
        'MaintainabilityContractReport',
    ]:
        assert f'class {name}' in schema
        assert name in health
    for route in [
        "@router.get('/health/security-readiness', response_model=SecurityReadinessReport)",
        "@router.get('/health/performance-readiness', response_model=PerformanceReadinessReport)",
        "@router.get('/health/query-hotspots', response_model=QueryHotspotReport)",
        "@router.get('/health/release-candidate', response_model=ReleaseCandidateReport)",
        "@router.get('/health/pilot-operations', response_model=PilotOperationsReport)",
        "@router.get('/health/maintainability-contract', response_model=MaintainabilityContractReport)",
    ]:
        assert route in health
    assert "extra='allow'" in schema or "extra=\"allow\"" in schema


def test_v63_maintainability_contract_gate_is_static_and_read_only():
    service = text('backend/app/services/maintainability_contract.py')
    script = text('scripts/maintainability-contract-report.sh')
    assert 'class MaintainabilityContractService' in service
    assert 'static_source_contract_scan_no_db_no_mutation' in service
    assert 'LARGE_FILE_LIMITS' in service
    assert 'CONTRACT_MODULES' in service
    assert 'frontend/types/readiness.ts' in service
    assert '/health/maintainability-contract' in script
    assert 'MAINTAINABILITY_CONTRACT_SUMMARY.md' in script
    banned = ['SessionLocal', 'db.query', '.execute(', '.delete(', '.update(', '.delay(']
    for term in banned:
        assert term not in service


def test_v63_frontend_split_contract_modules_exist():
    assert 'export type {' in text('frontend/types/readiness.ts')
    assert 'MaintainabilityContractReport' in text('frontend/types/readiness.ts')
    assert 'getMaintainabilityContract' in text('frontend/lib/api/readiness.ts')
    assert 'getSecurityReadiness' in text('frontend/lib/api/readiness.ts')
    assert 'export function apiFetch' in text('frontend/lib/api.ts')
    assert 'export async function parseResponse' in text('frontend/lib/api.ts')
    component = text('frontend/components/readiness/OperationalGatePanel.tsx')
    assert 'OperationalGatePanel' in component
    assert 'ops-gate-panel' in component
    assert '.ops-gate-panel' in text('frontend/styles/ops-readiness.css')


def test_v63_scripts_review_runtime_include_maintainability_gate():
    assert 'MAINTAINABILITY_CONTRACT /health/maintainability-contract' in text('scripts/uat-runtime-verify.sh')
    assert 'scripts/maintainability-contract-report.sh' in text('scripts/uat-build-gate.sh')
    review = text('scripts/claude-code-review-pack.sh')
    assert 'maintainability-contract-report.sh' in review
    assert 'MaintainabilityContractService' in review or 'maintainability-contract' in review
    assert 'backend/app/schemas/readiness.py' in text('docs/CLAUDE_CODE_REVIEW_HANDOFF_V25_9_16_7_2_64_12.md')


def test_v63_no_new_migration():
    assert (ROOT / 'backend/alembic/versions/0052_v25_9_16_7_2_27_learning_behavior_logic_calibration.py').exists()
    assert not list((ROOT / 'backend/alembic/versions').glob('0053*.py'))
