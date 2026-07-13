from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
VERSION = '25.9.16.7.2.64.12'


def text(path: str) -> str:
    return (ROOT / path).read_text(encoding='utf-8')


def test_v64_3_version_and_docs():
    assert f"app_version: str = '{VERSION}'" in text('backend/app/core/config.py')
    assert f'"version": "{VERSION}"' in text('frontend/package.json')
    assert f'NEXT_PUBLIC_APP_VERSION: ${{APP_VERSION:-{VERSION}}}' in text('docker-compose.prod.yml')
    assert 'Question Bank Quiz Creation/Auto-map Workflow Split' in text('README.md')
    assert 'RUN_V25_9_16_7_2_64_12.md' in text('README.md')
    assert text('CHANGELOG.md').startswith('## v25.9.16.7.2.64.12 — Academic AP Sync + External Assignment Workflow Split')
    assert (ROOT / 'docs/RELEASE_v25.9.16.7.2.64.12_QUESTION_BANK_QUIZ_CREATION_AUTOMAP_WORKFLOW_SPLIT.md').exists()
    assert (ROOT / 'docs/CLAUDE_CODE_REVIEW_HANDOFF_V25_9_16_7_2_64_12.md').exists()


def test_question_bank_release_publish_workflow_is_extracted_and_delegated():
    service = text('backend/app/services/question_bank_service.py')
    workflow = text('backend/app/services/question_bank/release_publish.py')
    assert 'from app.services.question_bank.release_publish import QuestionBankReleasePublishWorkflowService' in service
    assert 'def _release_publish_workflow(self) -> QuestionBankReleasePublishWorkflowService' in service
    assert 'return self._release_publish_workflow().release_readiness' in service
    assert 'return self._release_publish_workflow().create_release' in service
    assert 'return self._release_publish_workflow().release_publish_audit' in service
    assert 'return await self._release_publish_workflow().publish_release_to_openedx' in service
    assert 'class QuestionBankReleasePublishWorkflowService' in workflow
    assert 'def release_readiness' in workflow
    assert 'def create_release' in workflow
    assert 'def release_publish_audit' in workflow
    assert 'async def publish_release_to_openedx' in workflow
    assert 'async def rollback_course_quiz_instance' in workflow


def test_question_bank_service_no_longer_contains_release_publish_bodies():
    service = text('backend/app/services/question_bank_service.py')
    release_readiness_body = service.split('def release_readiness', 1)[1].split('def list_course_quiz_instances', 1)[0]
    create_release_body = service.split('def create_release', 1)[1].split('def cancel_failed_release', 1)[0]
    publish_body = service.split('async def publish_release_to_openedx', 1)[1]
    assert 'QuestionBankReleasePublishWorkflowService' in service
    assert 'pending_review_count' not in release_readiness_body
    assert 'release_code = f' not in create_release_body
    assert 'connector.ensure_problem_library' not in publish_body
    assert 'question_to_openedx_olx' not in publish_body


def test_release_publish_workflow_preserves_low_level_parent_delegation():
    workflow = text('backend/app/services/question_bank/release_publish.py')
    assert 'def __getattr__(self, name)' in workflow
    assert 'return getattr(self._service, name)' in workflow
    assert 'def db(self) -> Session' in workflow
    assert 'return self._service.db' in workflow
    assert 'behavior-preserving' in workflow


def test_maintainability_contract_tracks_question_bank_release_publish_split():
    contract = text('backend/app/services/maintainability_contract.py')
    assert 'backend/app/services/question_bank/release_publish.py' in contract
    assert 'backend/app/services/question_bank/helpers.py' in contract
    assert 'backend/app/services/question_bank_service.py' in contract


def test_v64_3_no_new_alembic_revision():
    assert (ROOT / 'backend/alembic/versions/0052_v25_9_16_7_2_27_learning_behavior_logic_calibration.py').exists()
    assert not list((ROOT / 'backend/alembic/versions').glob('0053*.py'))
