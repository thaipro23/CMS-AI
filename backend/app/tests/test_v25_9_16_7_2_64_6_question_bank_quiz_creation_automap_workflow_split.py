from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
VERSION = '25.9.16.7.2.64.12'


def text(path: str) -> str:
    return (ROOT / path).read_text(encoding='utf-8')


def test_v64_6_version_and_docs():
    assert f"app_version: str = '{VERSION}'" in text('backend/app/core/config.py')
    assert f'"version": "{VERSION}"' in text('frontend/package.json')
    assert f'NEXT_PUBLIC_APP_VERSION: ${{APP_VERSION:-{VERSION}}}' in text('docker-compose.prod.yml')
    assert 'Question Bank Quiz Creation/Auto-map Workflow Split' in text('README.md')
    assert 'question-bank-quiz-creation-automap-workflow-split.zip' in text('RUN_CURRENT.md')
    assert text('CHANGELOG.md').startswith('## v25.9.16.7.2.64.12 — Academic AP Sync + External Assignment Workflow Split')
    assert (ROOT / 'docs/RELEASE_v25.9.16.7.2.64.12_QUESTION_BANK_QUIZ_CREATION_AUTOMAP_WORKFLOW_SPLIT.md').exists()
    assert (ROOT / 'docs/CLAUDE_CODE_REVIEW_HANDOFF_V25_9_16_7_2_64_12.md').exists()


def test_question_bank_quiz_creation_workflow_is_extracted_and_delegated():
    service = text('backend/app/services/question_bank_service.py')
    workflow = text('backend/app/services/question_bank/quiz_creation.py')
    assert 'from app.services.question_bank.quiz_creation import QuestionBankQuizCreationWorkflowService' in service
    assert 'def _quiz_creation_workflow(self) -> QuestionBankQuizCreationWorkflowService' in service
    assert 'class QuestionBankQuizCreationWorkflowService' in workflow
    assert 'async def preview_quiz_auto_map' in workflow
    assert 'async def apply_quiz_auto_map' in workflow
    assert 'def _build_release_quiz_plan' in workflow
    assert 'def preview_quiz_from_release' in workflow
    assert 'async def create_quiz_from_release' in workflow
    assert 'return await self._quiz_creation_workflow().preview_quiz_auto_map' in service
    assert 'return await self._quiz_creation_workflow().apply_quiz_auto_map' in service
    assert 'return self._quiz_creation_workflow()._build_release_quiz_plan' in service
    assert 'return self._quiz_creation_workflow().preview_quiz_from_release' in service
    assert 'return await self._quiz_creation_workflow().create_quiz_from_release' in service


def test_question_bank_service_no_longer_hosts_quiz_creation_bodies():
    service = text('backend/app/services/question_bank_service.py')
    preview_body = service.split('async def preview_quiz_auto_map', 1)[1].split('async def apply_quiz_auto_map', 1)[0]
    apply_body = service.split('async def apply_quiz_auto_map', 1)[1].split('def _validation_result', 1)[0]
    create_body = service.split('async def create_quiz_from_release', 1)[1].split('def create_quiz_blueprint', 1)[0]
    assert 'await get_openedx_connector().get_course_blocks' not in preview_body
    assert 'CourseQuizInstance(' not in create_body
    assert 'connector.create_quiz_node' not in create_body
    assert 'connector.insert_problem_banks' not in create_body
    assert 'mapping = self.db.query(EdxCourseMapping)' not in apply_body
    assert 'return await self._quiz_creation_workflow()' in preview_body
    assert 'return await self._quiz_creation_workflow()' in apply_body
    assert 'return await self._quiz_creation_workflow()' in create_body


def test_quiz_creation_workflow_preserves_openedx_timer_problem_bank_semantics():
    workflow = text('backend/app/services/question_bank/quiz_creation.py')
    assert 'def __getattr__(self, name)' in workflow
    assert 'return getattr(self._service, name)' in workflow
    assert 'get_openedx_connector().get_course_blocks' in workflow
    assert 'connector.create_quiz_node' in workflow
    assert 'connector.upsert_quiz_timer_config' in workflow
    assert 'connector.insert_problem_banks' in workflow
    assert 'Quiz tự luyện không dùng native Timed Exam' in workflow
    assert 'cleanup_legacy_ai_randomized_blocks' in workflow
    assert 'assessment_type = \'final_test\'' in workflow
    assert 'QuestionBankQuizCreationWorkflowService._quiz_action_requires_release' in workflow


def test_maintainability_contract_tracks_question_bank_quiz_creation_workflow_split():
    contract = text('backend/app/services/maintainability_contract.py')
    assert 'backend/app/services/question_bank/quiz_creation.py' in contract
    assert 'backend/app/services/question_bank/release_publish.py' in contract
    assert 'backend/app/services/question_bank/helpers.py' in contract
    assert 'backend/app/services/question_bank_service.py' in contract


def test_v64_6_no_new_alembic_revision():
    assert (ROOT / 'backend/alembic/versions/0052_v25_9_16_7_2_27_learning_behavior_logic_calibration.py').exists()
    assert not list((ROOT / 'backend/alembic/versions').glob('0053*.py'))
