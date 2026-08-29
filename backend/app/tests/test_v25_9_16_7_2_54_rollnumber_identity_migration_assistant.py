from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
VERSION = '25.9.16.7.2.64.13'


def _read(path: str) -> str:
    return (ROOT / path).read_text(encoding='utf-8')


def test_v54_version_sync_and_release_docs():
    assert f"app_version: str = '{VERSION}'" in _read('backend/app/core/config.py')
    assert f'"version": "{VERSION}"' in _read('frontend/package.json')
    assert f'ARG NEXT_PUBLIC_APP_VERSION={VERSION}' in _read('frontend/Dockerfile')
    assert _read('CHANGELOG.md').startswith(f'## v{VERSION} — Bank Release Publish Reliability + Rollback QA')
    assert 'Bank Release Publish Reliability + Rollback QA' in _read('docs/RELEASE_v25.9.16.7.2.64.13_ROLLNUMBER_IDENTITY_MIGRATION_ASSISTANT.md')
    assert 'RUN v25.9.16.7.2.64.13' in _read('RUN_V25_9_16_7_2_54.md')


def test_v54_rollnumber_migration_api_is_read_only_and_scoped():
    route = _read('backend/app/api/routes/academic.py')
    service = _read('backend/app/services/academic_service.py')
    schemas = _read('backend/app/schemas/academic.py')
    assert "@router.get('/identity/rollnumber-migration'" in route
    assert 'response_model=AcademicIdentityMigrationOut' in route
    assert 'user: UserContext = Depends(_require_academic_sync_permission)' in route
    assert 'def rollnumber_identity_migration_report' in service
    assert "'dry_run': True" in service
    assert "'mutation_performed': False" in service
    assert 'self.assert_can_access_class(user, class_id_value)' in service
    assert 'scope_conditions' in service and 'decision.campus_codes' in service
    assert 'class AcademicIdentityMigrationOut' in schemas
    assert 'class AcademicIdentityMigrationItemOut' in schemas


def test_v54_migration_report_exports_evidence_without_cleanup():
    script = _read('scripts/rollnumber-identity-migration-report.sh')
    assert '/academic/identity/rollnumber-migration' in script
    assert 'ROLLNUMBER_IDENTITY_MIGRATION_SUMMARY.md' in script
    assert 'Read-only report' in script
    assert 'DELETE_WRONG_UAT_IDENTITY' not in script
    assert '/uat-cleanup' not in script


def test_v54_statuses_and_blockers_are_explicit():
    service = _read('backend/app/services/academic_service.py')
    for token in [
        'LEGACY_AP_USERNAME',
        'MISSING_ROLLNUMBER',
        'DUPLICATE_ROLLNUMBER',
        'DUPLICATE_CMS_MAPPING',
        'CMS_USERNAME_MISMATCH',
        'READY_WITH_WARNINGS',
        'BLOCKED',
    ]:
        assert token in service
    assert 'Không chạy Đồng bộ full CMS diện rộng' in service
