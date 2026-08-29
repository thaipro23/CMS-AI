from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
VERSION = '25.9.16.7.2.64.13'


def text(path: str) -> str:
    return (ROOT / path).read_text(encoding='utf-8')


def test_v64_3_version_and_docs():
    assert f"app_version: str = '{VERSION}'" in text('backend/app/core/config.py')
    assert f'"version": "{VERSION}"' in text('frontend/package.json')
    assert f'NEXT_PUBLIC_APP_VERSION: ${{APP_VERSION:-{VERSION}}}' in text('docker-compose.prod.yml')
    assert 'Question Bank Quiz Creation/Auto-map Workflow Split' in text('README.md')
    assert 'RUN_V25_9_16_7_2_64_13.md' in text('README.md')
    assert text('CHANGELOG.md').startswith('## v25.9.16.7.2.64.13 — Academic AP Sync + External Assignment Workflow Split')
    assert (ROOT / 'docs/RELEASE_v25.9.16.7.2.64.13_QUESTION_BANK_QUIZ_CREATION_AUTOMAP_WORKFLOW_SPLIT.md').exists()
    assert (ROOT / 'docs/CLAUDE_CODE_REVIEW_HANDOFF_V25_9_16_7_2_64_13.md').exists()


def test_academic_access_workflow_is_extracted_and_delegated():
    service = text('backend/app/services/academic_service.py')
    access = text('backend/app/services/academic/access.py')
    assert 'from app.services.academic.access import AcademicAccessWorkflowService' in service
    assert 'def _access_workflow(self) -> AcademicAccessWorkflowService' in service
    assert 'return self._access_workflow().access_decision(user)' in service
    assert 'return self._access_workflow().assert_can_access_class(user, class_id)' in service
    assert 'class AcademicAccessWorkflowService' in access
    assert 'Quiz Bank roles do not grant class/student access' in access
    assert 'accessible_campus_codes' in access
    assert 'AcademicTeacherAssignment.class_id == class_id' in access


def test_academic_roster_workflow_is_extracted_and_delegated():
    service = text('backend/app/services/academic_service.py')
    roster = text('backend/app/services/academic/roster.py')
    assert 'from app.services.academic.roster import AcademicRosterWorkflowService' in service
    assert 'return AcademicRosterWorkflowService(self.db, parent=self).list_class_students' in service
    assert 'class AcademicRosterWorkflowService' in roster
    assert 'def list_class_students' in roster
    assert 'assignment_scores_for_class' in roster
    assert 'deadline_overrides_for_class' in roster
    assert 'def _apply_learning_status_filter' in roster
    assert 'AcademicStudentLearningSnapshot.progress_percent < self.parent._low_progress_threshold()' in roster


def test_academic_service_no_longer_contains_roster_query_body():
    service = text('backend/app/services/academic_service.py')
    list_method = service.split('def list_class_students', 1)[1].split('@staticmethod\n    def _percent_to_grade10', 1)[0]
    assert 'AcademicRosterWorkflowService' in list_method
    assert 'self.db.query(AcademicStudent, AcademicClassStudent, OpenEdXUserMapping' not in list_method
    assert 'query.order_by(AcademicStudent.student_code.asc().nullslast()' not in list_method


def test_maintainability_contract_tracks_academic_workflow_split_modules():
    contract = text('backend/app/services/maintainability_contract.py')
    assert 'backend/app/services/academic/access.py' in contract
    assert 'backend/app/services/academic/roster.py' in contract
    assert 'academic sync/enrollment mutation' in contract


def test_v64_3_no_new_alembic_revision():
    assert (ROOT / 'backend/alembic/versions/0052_v25_9_16_7_2_27_learning_behavior_logic_calibration.py').exists()
    assert not list((ROOT / 'backend/alembic/versions').glob('0053*.py'))
