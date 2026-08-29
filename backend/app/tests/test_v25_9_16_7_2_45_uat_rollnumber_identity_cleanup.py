from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
VERSION = '25.9.16.7.2.64.13'
TITLE = 'Bank Release Publish Reliability + Rollback QA'


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding='utf-8')


def test_v45_version_and_docs_are_current():
    assert f"app_version: str = '{VERSION}'" in read('backend/app/core/config.py')
    assert f'# v{VERSION} — {TITLE}' in read('RUN_CURRENT.md')
    assert read('CHANGELOG.md').startswith(f'## v{VERSION} — {TITLE}')
    assert 'ACADEMIC_IDENTITY_CLEANUP_ALLOW_DESTRUCTIVE=false' in read('.env.production.example')


def test_v45_backend_cleanup_endpoint_is_guarded_and_destructive_only_when_confirmed():
    routes = read('backend/app/api/routes/academic.py')
    schemas = read('backend/app/schemas/academic.py')
    service = read('backend/app/services/academic_service.py')
    assert "@router.post('/classes/{class_id}/identity-reconciliation/uat-cleanup'" in routes
    assert 'response_model=AcademicIdentityCleanupOut' in routes
    assert 'class AcademicIdentityCleanupIn' in schemas
    assert 'class AcademicIdentityCleanupOut' in schemas
    assert 'def cleanup_identity_reconciliation_for_class' in service
    assert 'academic_identity_cleanup_allow_destructive' in service
    assert 'DELETE_WRONG_UAT_IDENTITY' in service
    assert 'It never deletes Open edX' in service
    assert 'self.db.delete(mapping)' in service
    assert 'AcademicStudentLearningSnapshot' in service


def test_v45_frontend_exposes_dry_run_and_confirmed_uat_cleanup():
    api = read('frontend/lib/api.ts')
    page = read('frontend/app/student-management/classes/[classId]/page.tsx')
    css = read('frontend/app/globals.css')
    types = read('frontend/types/index.ts')
    assert 'AcademicIdentityCleanupResult' in types
    assert 'cleanupAcademicClassIdentityReconciliation' in api
    assert 'identity-reconciliation/uat-cleanup' in api
    assert 'Dry-run cleanup' in page
    assert 'Xóa mapping sai UAT' in page
    assert 'DELETE_WRONG_UAT_IDENTITY' in page
    assert 'identity-cleanup-result' in css
