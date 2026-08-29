from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
VERSION = '25.9.16.7.2.64.13'


def text(path: str) -> str:
    return (ROOT / path).read_text(encoding='utf-8')


def test_v64_5_version_and_docs():
    assert f"app_version: str = '{VERSION}'" in text('backend/app/core/config.py')
    assert f'"version": "{VERSION}"' in text('frontend/package.json')
    assert f'NEXT_PUBLIC_APP_VERSION: ${{APP_VERSION:-{VERSION}}}' in text('docker-compose.prod.yml')
    assert 'Question Bank Quiz Creation/Auto-map Workflow Split' in text('README.md')
    assert 'question-bank-quiz-creation-automap-workflow-split.zip' in text('RUN_CURRENT.md')
    assert text('CHANGELOG.md').startswith('## v25.9.16.7.2.64.13 — Academic AP Sync + External Assignment Workflow Split')
    assert (ROOT / 'docs/RELEASE_v25.9.16.7.2.64.13_QUESTION_BANK_QUIZ_CREATION_AUTOMAP_WORKFLOW_SPLIT.md').exists()
    assert (ROOT / 'docs/CLAUDE_CODE_REVIEW_HANDOFF_V25_9_16_7_2_64_13.md').exists()


def test_academic_sync_enrollment_workflow_is_extracted_and_delegated():
    service = text('backend/app/services/academic_service.py')
    workflow = text('backend/app/services/academic/sync_enrollment.py')
    assert 'from app.services.academic.sync_enrollment import AcademicSyncEnrollmentWorkflowService' in service
    assert 'def _academic_sync_enrollment_workflow(self) -> AcademicSyncEnrollmentWorkflowService' in service
    assert 'class AcademicSyncEnrollmentWorkflowService' in workflow
    assert 'def resolve_class_openedx_users' in workflow
    assert 'def sync_class_course_enrollment' in workflow
    assert 'def sync_class_learning_insight' in workflow
    assert 'def sync_class_full_cms_flow' in workflow
    assert 'def _try_auto_map_course_for_class' in workflow
    assert 'return self._academic_sync_enrollment_workflow().resolve_class_openedx_users' in service
    assert 'return self._academic_sync_enrollment_workflow().sync_class_course_enrollment' in service
    assert 'return self._academic_sync_enrollment_workflow().sync_class_learning_insight' in service
    assert 'return self._academic_sync_enrollment_workflow().sync_class_full_cms_flow' in service


def test_academic_service_no_longer_hosts_sync_mutation_bodies():
    service = text('backend/app/services/academic_service.py')
    resolve_body = service.split('def resolve_class_openedx_users', 1)[1].split('def _float_or_none', 1)[0]
    enrollment_body = service.split('def sync_class_course_enrollment', 1)[1].split('def sync_class_learning_insight', 1)[0]
    learning_body = service.split('def sync_class_learning_insight', 1)[1].split('def _try_auto_map_course_for_class', 1)[0]
    full_body = service.split('def sync_class_full_cms_flow', 1)[1].split('def _identity_reconciliation_status', 1)[0]
    assert 'OpenEdXConnectorClient()' not in resolve_body
    assert 'client.enroll_users' not in enrollment_body
    assert 'client.class_learning' not in learning_body
    assert 'auto_map_course=auto_map_course' in full_body
    assert 'sync_learning=sync_learning' in full_body
    assert 'return self._academic_sync_enrollment_workflow()' in resolve_body


def test_workflow_preserves_parent_delegation_and_student_ops_guard():
    workflow = text('backend/app/services/academic/sync_enrollment.py')
    assert 'def __getattr__(self, name: str) -> Any' in workflow
    assert 'return getattr(self.parent, name)' in workflow
    assert 'self.assert_can_access_class(user, class_id)' in workflow
    assert 'OpenEdXConnectorClient' in workflow
    assert 'academic_auto_create_cms_users' in workflow
    assert 'academic_auto_enroll_after_cms_sync' in workflow
    assert 'academic_full_sync_learning_after_enrollment' in workflow


def test_maintainability_contract_tracks_academic_sync_workflow_split():
    contract = text('backend/app/services/maintainability_contract.py')
    assert 'backend/app/services/academic/sync_enrollment.py' in contract
    assert 'backend/app/services/academic/access.py' in contract
    assert 'backend/app/services/academic/roster.py' in contract
    assert 'backend/app/services/academic_service.py' in contract


def test_v64_5_no_new_alembic_revision():
    assert (ROOT / 'backend/alembic/versions/0052_v25_9_16_7_2_27_learning_behavior_logic_calibration.py').exists()
    assert not list((ROOT / 'backend/alembic/versions').glob('0053*.py'))
