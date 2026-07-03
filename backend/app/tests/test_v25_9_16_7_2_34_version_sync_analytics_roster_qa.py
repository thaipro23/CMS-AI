from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
VERSION = '25.9.16.7.2.35'


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding='utf-8')


def test_v35_runtime_version_still_keeps_v34_roster_qa_baseline():
    assert f"app_version: str = '{VERSION}'" in read('backend/app/core/config.py')
    assert f'"version": "{VERSION}"' in read('frontend/package.json')
    assert f'NEXT_PUBLIC_APP_VERSION: ${{APP_VERSION:-{VERSION}}}' in read('docker-compose.prod.yml')
    assert f"process.env.NEXT_PUBLIC_APP_VERSION || '{VERSION}'" in read('frontend/components/layout/AppShell.tsx')
    assert f'APP_VERSION={VERSION}' in read('.env.example')
    assert f'APP_VERSION={VERSION}' in read('.env.production.example')
    assert f'# AI Server Open edX — v{VERSION}' in read('README.md')
    assert f'# v{VERSION} — Analytics Post-Ingest Recalculate Orchestrator' in read('RUN_CURRENT.md')


def test_changelog_order_and_known_heading_cleanup():
    changelog = read('CHANGELOG.md')
    assert changelog.startswith('## v25.9.16.7.2.35 — Analytics Post-Ingest Recalculate Orchestrator')
    assert changelog.index('## v25.9.16.7.2.34 — Production Polish Version Sync + Analytics Roster QA') < changelog.index('## v25.9.16.7.2.33 — Class Actions Toolbar + Learning Roster Fallback')
    assert '## v25.9.16.7.2.30 — Responsive Device-Adaptive UX' in changelog
    assert '## v25.9.16.7.2.32 — Responsive Device-Adaptive UX' not in changelog


def test_analytics_class_overview_exposes_roster_snapshot_qa_fields():
    source = read('backend/app/services/learning_analytics/analytics_core_service.py')
    assert "'roster_count': student_count" in source
    assert "'missing_snapshot_count': missing_snapshot_count" in source
    assert "totals['roster_count'] += item['roster_count']" in source
    assert "totals['missing_snapshot_count'] += item['missing_snapshot_count']" in source
    assert "'roster_count': int(totals.get('roster_count', 0))" in source
    assert "'missing_snapshot_count': int(totals.get('missing_snapshot_count', 0))" in source


def test_analytics_behavior_summary_and_frontend_show_snapshot_coverage():
    service = read('backend/app/services/learning_analytics/analytics_core_service.py')
    types = read('frontend/types/index.ts')
    page = read('frontend/app/analytics/learning/page.tsx')
    assert "'roster_count': len(roster)" in service
    assert "'snapshot_count': len(rows)" in service
    assert "'data_status': data_status" in service
    assert 'roster_count?: number' in types
    assert 'missing_snapshot_count?: number' in types
    assert 'Snapshot nhận định' in page
    assert 'Thiếu snapshot' in page
    assert 'summary.snapshot_count ?? rows.length' in page
