from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
VERSION = '25.9.16.7.2.64.13'
TITLE = 'Bank Release Publish Reliability + Rollback QA'


def read(path: str) -> str:
    return (ROOT / path).read_text()


def test_v50_version_and_runbook_are_current():
    assert f"app_version: str = '{VERSION}'" in read('backend/app/core/config.py')
    assert f'"version": "{VERSION}"' in read('frontend/package.json')
    assert f'NEXT_PUBLIC_APP_VERSION: ${{APP_VERSION:-{VERSION}}}' in read('docker-compose.prod.yml')
    assert f'# v{VERSION} — {TITLE}' in read('RUN_V25_9_16_7_2_53.md')
    assert read('CHANGELOG.md').startswith(f'## v{VERSION} — {TITLE}')


def test_v50_backend_exposes_read_only_evidence_pack():
    route = read('backend/app/api/routes/learning_analytics.py')
    service = read('backend/app/services/learning_analytics/analytics_core_service.py')
    assert "@router.get('/ops/evidence-pack')" in route
    assert 'def analytics_uat_evidence_pack(' in route
    assert 'action=\'analytics.uat_evidence_pack.view\'' in route
    assert 'def analytics_uat_evidence_pack(' in service
    body = service.split('    def analytics_uat_evidence_pack(', 1)[1].split('    def ops_status(', 1)[0]
    assert 'production_readiness_report' in body
    assert 'analytics_sla_report' in body
    assert 'pilot_acceptance_report' in body
    assert 'class_result_doctor' in body
    assert 'never scans raw tracking.log' in body or 'Không đọc raw tracking.log' in body
    assert 'Không enqueue job trong request.' in body
    assert 'Không recalculate trong request.' in body
    assert 'Không mutate dữ liệu.' in body
    assert 'signals_only_not_violation' in body
    assert "getattr(settings, 'app_version', '25.9.16.7.2.64.13')" in body


def test_v50_script_exports_json_and_markdown_evidence():
    script = read('scripts/analytics-uat-evidence-pack.sh')
    assert 'set -euo pipefail' in script
    assert 'OUT_DIR=' in script
    assert '/analytics/ops/evidence-pack?' in script
    assert 'EVIDENCE_SUMMARY.md' in script
    assert 'build.json' in script
    assert 'readiness.json' in script
    assert 'analytics-sla.json' in script
    assert 'pilot-acceptance.json' in script
    assert 'evidence-pack.json' in script
    assert 'class-doctor.json' in script
    assert 'curl -fsS' in script


def test_v50_frontend_surfaces_evidence_pack_panel():
    page = read('frontend/app/analytics/learning/page.tsx')
    api = read('frontend/lib/api.ts')
    types = read('frontend/types/index.ts')
    css = read('frontend/app/globals.css')
    assert 'getAnalyticsEvidencePack' in api
    assert 'AnalyticsEvidencePackReport' in types
    assert 'getAnalyticsEvidencePack(headers' in page
    assert 'Gói bằng chứng UAT' in page
    assert 'analytics-evidence-pack-panel' in page
    assert 'Read-only:' in page
    assert 'v25.9.16.7.2.64.13 — UAT evidence pack' in css
