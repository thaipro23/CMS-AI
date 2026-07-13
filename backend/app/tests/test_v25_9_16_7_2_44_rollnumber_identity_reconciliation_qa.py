from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
VERSION = '25.9.16.7.2.64.12'
TITLE = 'Bank Release Publish Reliability + Rollback QA'


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding='utf-8')


def test_v44_version_docs_and_changelog_are_current():
    assert f"app_version: str = '{VERSION}'" in read('backend/app/core/config.py')
    assert f'"version": "{VERSION}"' in read('frontend/package.json')
    assert f'NEXT_PUBLIC_APP_VERSION: ${{APP_VERSION:-{VERSION}}}' in read('docker-compose.prod.yml')
    assert f"process.env.NEXT_PUBLIC_APP_VERSION || '{VERSION}'" in read('frontend/components/layout/AppShell.tsx')
    assert f'# AI Server Open edX — v{VERSION}' in read('README.md')
    assert f'# v{VERSION} — {TITLE}' in read('RUN_CURRENT.md')
    assert f'# v{VERSION} — {TITLE}' in read('RUN_V25_9_16_7_2_53.md')
    assert read('CHANGELOG.md').startswith(f'## v{VERSION} — {TITLE}')


def test_v44_backend_identity_reconciliation_is_read_only_and_rollnumber_aware():
    service = read('backend/app/services/academic_service.py')
    routes = read('backend/app/api/routes/academic.py')
    schemas = read('backend/app/schemas/academic.py')
    assert 'def identity_reconciliation_for_class' in service
    assert 'def _identity_reconciliation_status' in service
    assert "'policy': 'rollnumber_canonical_username'" in service
    assert "'dry_run': True" in service
    assert "'mutation_performed': False" in service
    assert 'LEGACY_AP_USERNAME' in service
    assert 'DUPLICATE_ROLLNUMBER' in service
    assert 'MISSING_ROLLNUMBER' in service
    assert "canonical_username = self._student_cms_username(student)" in service
    assert "@router.get('/classes/{class_id}/identity-reconciliation'" in routes
    assert 'response_model=AcademicIdentityReconciliationOut' in routes
    assert 'class AcademicIdentityReconciliationItemOut' in schemas
    assert 'class AcademicIdentityReconciliationOut' in schemas


def test_v44_class_detail_ui_surfaces_identity_panel_and_api_client():
    page = read('frontend/app/student-management/classes/[classId]/page.tsx')
    api = read('frontend/lib/api.ts')
    types = read('frontend/types/index.ts')
    css = read('frontend/app/globals.css')
    assert 'getAcademicClassIdentityReconciliation' in api
    assert 'AcademicIdentityReconciliationReport' in types
    assert 'Kiểm tra identity CMS/RollNumber' in page
    assert 'identityReportClass' in page
    assert 'LEGACY_AP_USERNAME' in page
    assert 'MISSING_ROLLNUMBER' in page
    assert 'identity-reconciliation-panel' in css
    assert 'v25.9.16.7.2.64.12 — RollNumber identity reconciliation QA' in css
