from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
VERSION = '25.9.16.7.2.64.12'


def text(path: str) -> str:
    return (ROOT / path).read_text(encoding='utf-8')


def test_v64_7_version_and_docs():
    assert f"app_version: str = '{VERSION}'" in text('backend/app/core/config.py')
    assert f'"version": "{VERSION}"' in text('frontend/package.json')
    assert f'NEXT_PUBLIC_APP_VERSION: ${{APP_VERSION:-{VERSION}}}' in text('docker-compose.prod.yml')
    assert 'Academic Identity Import/Reconciliation Workflow Split' in text('README.md')
    assert 'academic-identity-import-reconciliation-workflow-split.zip' in text('RUN_CURRENT.md')
    assert text('CHANGELOG.md').startswith('## v25.9.16.7.2.64.12 — Academic AP Sync + External Assignment Workflow Split')
    assert (ROOT / 'docs/RELEASE_v25.9.16.7.2.64.12_ACADEMIC_IDENTITY_IMPORT_RECONCILIATION_WORKFLOW_SPLIT.md').exists()
    assert (ROOT / 'docs/CLAUDE_CODE_REVIEW_HANDOFF_V25_9_16_7_2_64_12.md').exists()


def test_academic_identity_workflow_is_extracted_and_delegated():
    service = text('backend/app/services/academic_service.py')
    workflow = text('backend/app/services/academic/identity.py')
    assert 'from app.services.academic.identity import AcademicIdentityReconciliationWorkflowService' in service
    assert 'def _academic_identity_workflow(self) -> AcademicIdentityReconciliationWorkflowService' in service
    assert 'class AcademicIdentityReconciliationWorkflowService' in workflow
    for name in [
        '_identity_reconciliation_status',
        'identity_reconciliation_for_class',
        'cleanup_identity_reconciliation_for_class',
        '_identity_reconciliation_next_actions',
        'rollnumber_identity_migration_report',
        'import_openedx_user_mappings',
    ]:
        assert f'def {name}' in workflow
        assert f'self._academic_identity_workflow().{name}' in service


def test_academic_service_no_longer_hosts_identity_reconciliation_bodies():
    service = text('backend/app/services/academic_service.py')
    section = service.split('def _identity_reconciliation_status', 1)[1].split('def import_openedx_user_mappings', 1)[0]
    assert 'rollnumber_canonical_username' not in section
    assert 'raw_rows = query.limit(20000).all()' not in section
    assert 'OpenEdXUserMapping(' not in section
    assert 'mutation_performed' not in section
    assert 'return self._academic_identity_workflow()' in section


def test_identity_workflow_preserves_rollnumber_cleanup_import_semantics():
    workflow = text('backend/app/services/academic/identity.py')
    assert 'rollnumber_canonical_username' in workflow
    assert 'rollnumber_identity_migration_assistant' in workflow
    assert 'academic_identity_cleanup_allow_destructive' in workflow
    assert 'DELETE_WRONG_UAT_IDENTITY' in workflow
    assert 'mutation_performed' in workflow
    assert 'OpenEdXUserMapping' in workflow
    assert 'manual_import' in workflow
    assert 'Imported by' in workflow
    assert 'read_only_no_openedx_mutation' in workflow


def test_sync_enrollment_extracted_functions_are_bound_to_workflow_class():
    sync = text('backend/app/services/academic/sync_enrollment.py')
    assert 'AcademicSyncEnrollmentWorkflowService._student_cms_username = _student_cms_username' in sync
    assert 'AcademicSyncEnrollmentWorkflowService.sync_class_full_cms_flow = sync_class_full_cms_flow' in sync
    assert 'normal bound-method semantics' in sync


def test_maintainability_contract_tracks_academic_identity_workflow_split():
    contract = text('backend/app/services/maintainability_contract.py')
    assert 'backend/app/services/academic/identity.py' in contract
    assert 'backend/app/services/academic/sync_enrollment.py' in contract
    assert 'backend/app/services/academic/access.py' in contract
    assert 'backend/app/services/academic/roster.py' in contract
    assert 'backend/app/services/academic_service.py' in contract


def test_v64_7_no_new_alembic_revision():
    assert (ROOT / 'backend/alembic/versions/0052_v25_9_16_7_2_27_learning_behavior_logic_calibration.py').exists()
    assert not list((ROOT / 'backend/alembic/versions').glob('0053*.py'))
