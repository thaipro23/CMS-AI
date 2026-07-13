from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
VERSION = '25.9.16.7.2.64.12'
TITLE = 'Bank Release Publish Reliability + Rollback QA'


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding='utf-8')


def test_v49_version_docs_and_changelog_are_current():
    assert f"app_version: str = '{VERSION}'" in read('backend/app/core/config.py')
    assert f'"version": "{VERSION}"' in read('frontend/package.json')
    assert f'NEXT_PUBLIC_APP_VERSION: ${{APP_VERSION:-{VERSION}}}' in read('docker-compose.prod.yml')
    assert f"process.env.NEXT_PUBLIC_APP_VERSION || '{VERSION}'" in read('frontend/components/layout/AppShell.tsx')
    assert f'# v{VERSION} — {TITLE}' in read('RUN_CURRENT.md')
    assert f'# v{VERSION} — {TITLE}' in read('RUN_V25_9_16_7_2_53.md')
    assert read('CHANGELOG.md').startswith(f'## v{VERSION} — {TITLE}')


def test_v49_frontend_surfaces_pilot_acceptance_panel():
    page = read('frontend/app/analytics/learning/page.tsx')
    api = read('frontend/lib/api.ts')
    types = read('frontend/types/index.ts')
    css = read('frontend/app/globals.css')
    assert 'getAnalyticsPilotAcceptance' in api
    assert 'export type AnalyticsPilotAcceptanceReport' in types
    assert 'getAnalyticsPilotAcceptance,' in page
    assert 'const [pilotAcceptance, setPilotAcceptance]' in page
    assert 'const [pilotLoading, setPilotLoading]' in page
    assert 'Kiểm thử pilot UAT' in page
    assert 'pilotChecklistCount(pilotAcceptance)' in page
    assert 'analytics-pilot-acceptance-panel' in page
    assert '.analytics-pilot-acceptance-panel' in css
    assert 'Không kết luận vi phạm cá nhân' not in page
    assert 'không kết luận vi phạm cá nhân' in page.lower()


def test_v49_uat_smoke_runner_is_read_only_and_actionable():
    script = read('scripts/analytics-uat-acceptance.sh')
    assert 'set -euo pipefail' in script
    assert '/health/build' in script
    assert '/health/readiness' in script
    assert '/rbac/scope-audit' in script
    assert '/analytics/ops/sla' in script
    assert '/analytics/ops/pilot-acceptance' in script
    assert '/analytics/classes/' in script and '/doctor' in script
    assert 'analytics/backfill/jobs' not in script
    assert 'recalculate' not in script.lower()
    assert 'curl -fsS' in script


def test_v49_no_migration_added():
    versions = sorted((ROOT / 'backend/alembic/versions').glob('*.py'))
    assert versions[-1].name == '0052_v25_9_16_7_2_27_learning_behavior_logic_calibration.py'
    assert not any(path.name.startswith('0053_') for path in versions)
