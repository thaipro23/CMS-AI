from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
VERSION = '25.9.16.7.2.64.13'


def text(path: str) -> str:
    return (ROOT / path).read_text(encoding='utf-8')


def test_v63_1_version_and_release_docs():
    assert f"app_version: str = '{VERSION}'" in text('backend/app/core/config.py')
    assert f'"version": "{VERSION}"' in text('frontend/package.json')
    assert f'NEXT_PUBLIC_APP_VERSION: ${{APP_VERSION:-{VERSION}}}' in text('docker-compose.prod.yml')
    assert 'Question Bank Quiz Creation/Auto-map Workflow Split' in text('README.md')
    assert 'RUN_V25_9_16_7_2_64_13.md' in text('README.md')
    assert text('CHANGELOG.md').startswith('## v25.9.16.7.2.64.13 — Question Bank Quiz Creation/Auto-map Workflow Split')
    assert (ROOT / 'docs/RELEASE_v25.9.16.7.2.64.13_QUESTION_BANK_QUIZ_CREATION_AUTOMAP_WORKFLOW_SPLIT.md').exists()


def test_ops_readiness_page_uses_split_facade_and_shared_panel():
    page = text('frontend/app/ops/readiness/page.tsx')
    assert "from '../../../lib/api/readiness'" in page
    assert "from '../../../types/readiness'" in page
    assert 'OperationalGatePanel' in page
    assert 'getSecurityReadiness' in page
    assert 'getPerformanceReadiness' in page
    assert 'getReleaseCandidateReadiness' in page
    assert 'getPilotOperationsReadiness' in page
    assert 'getMaintainabilityContract' in page
    assert 'getQueryHotspots' in page
    assert 'Không enqueue job' in page or 'không enqueue job' in page.lower()


def test_readiness_split_api_is_not_just_reexport_anymore():
    api = text('frontend/lib/api/readiness.ts')
    types = text('frontend/types/readiness.ts')
    assert 'getMaintainabilityContract' in api
    assert 'getQueryHotspots' in api
    assert '/health/query-hotspots' in api
    assert 'QueryHotspotReport' in types
    assert 'MaintainabilityContractReport' in types


def test_app_shell_exposes_ops_readiness_under_admin():
    shell = text('frontend/components/layout/AppShell.tsx')
    assert "href: '/ops/readiness'" in shell
    assert "permission: 'view_jobs'" in shell
    assert "[/^\\/ops\\/readiness" in shell


def test_maintainability_contract_tracks_ops_split_route():
    service = text('backend/app/services/maintainability_contract.py')
    assert 'frontend/app/ops/readiness/page.tsx' in service
    assert 'frontend/lib/api/readiness.ts' in service
    assert 'frontend/components/readiness/OperationalGatePanel.tsx' in service


def test_v63_1_no_new_alembic_revision():
    assert (ROOT / 'backend/alembic/versions/0052_v25_9_16_7_2_27_learning_behavior_logic_calibration.py').exists()
    assert not list((ROOT / 'backend/alembic/versions').glob('0053*.py'))
