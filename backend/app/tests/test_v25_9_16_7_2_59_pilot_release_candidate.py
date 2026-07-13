from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
VERSION = '25.9.16.7.2.64.13'


def text(path: str) -> str:
    return (ROOT / path).read_text(encoding='utf-8')


def test_v59_version_sync_and_docs():
    assert f"app_version: str = '{VERSION}'" in text('backend/app/core/config.py')
    assert f'"version": "{VERSION}"' in text('frontend/package.json')
    assert f'NEXT_PUBLIC_APP_VERSION: ${{APP_VERSION:-{VERSION}}}' in text('docker-compose.prod.yml')
    assert f"'{VERSION}'" in text('frontend/components/layout/AppShell.tsx')
    assert text('CHANGELOG.md').startswith(f'## v{VERSION} — Question Bank Quiz Creation/Auto-map Workflow Split')
    assert f'v{VERSION} — Question Bank Quiz Creation/Auto-map Workflow Split' in text('RUN_CURRENT.md')
    assert 'ai_server_openedx_v25_9_16_7_2_64_13' in text('RUN_CURRENT.md')
    assert 'RELEASE_v25.9.16.7.2.64.13_QUESTION_BANK_QUIZ_CREATION_AUTOMAP_WORKFLOW_SPLIT.md' in '\n'.join(p.name for p in (ROOT / 'docs').glob('*64*'))


def test_v59_release_candidate_backend_gate():
    route = text('backend/app/api/routes/health.py')
    service = text('backend/app/services/release_candidate.py')
    assert "/health/release-candidate" in route and "ReleaseCandidateReport" in route
    assert 'ReleaseCandidateService(db).report' in route
    assert 'require_permission(\'view_dashboard\')' in route
    assert 'class ReleaseCandidateService' in service
    assert 'analytics_uat_evidence_pack' in service
    assert 'SecurityReadinessService().report()' in service
    assert 'PerformanceReadinessService(self.db).performance_readiness_report()' in service
    assert 'read_only_release_candidate_gate_no_mutation' in service
    assert 'Không mutate database' in service
    assert 'Không đọc raw tracking.log trong request' in service


def test_v59_frontend_panel_and_api_client():
    page = text('frontend/app/analytics/learning/page.tsx')
    api = text('frontend/lib/api.ts')
    types = text('frontend/types/index.ts')
    css = text('frontend/app/globals.css')
    assert 'getReleaseCandidateReadiness' in api
    assert 'ReleaseCandidateReport' in types
    assert 'releaseCandidateTone' in page
    assert 'Pilot Release Candidate' in page
    assert 'analytics-release-candidate-panel' in page
    assert '.analytics-release-candidate-panel' in css


def test_v59_scripts_and_review_pack_gate():
    script = text('scripts/pilot-release-candidate-report.sh')
    runtime = text('scripts/uat-runtime-verify.sh')
    build_gate = text('scripts/uat-build-gate.sh')
    review = text('scripts/claude-code-review-pack.sh')
    assert '/health/release-candidate' in script
    assert 'PILOT_RELEASE_CANDIDATE_SUMMARY.md' in script
    assert 'RELEASE_CANDIDATE /health/release-candidate' in runtime
    assert 'scripts/pilot-release-candidate-report.sh' in build_gate
    assert 'scripts/pilot-release-candidate-report.sh' in review
    assert 'GET /api/health/release-candidate' in text('docs/CLAUDE_CODE_REVIEW_HANDOFF_V25_9_16_7_2_64_13.md')


def test_v59_no_schema_migration_added():
    versions = sorted((ROOT / 'backend/alembic/versions').glob('*.py'))
    names = [p.name for p in versions]
    assert '0052_v25_9_16_7_2_27_learning_behavior_logic_calibration.py' in names
    assert not any(name.startswith('0053') or name.startswith('0054') for name in names)
