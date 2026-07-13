from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
VERSION = '25.9.16.7.2.64.12'


def text(path: str) -> str:
    return (ROOT / path).read_text(encoding='utf-8')


def test_v64_4_version_and_docs():
    assert f"app_version: str = '{VERSION}'" in text('backend/app/core/config.py')
    assert f'"version": "{VERSION}"' in text('frontend/package.json')
    assert f'NEXT_PUBLIC_APP_VERSION: ${{APP_VERSION:-{VERSION}}}' in text('docker-compose.prod.yml')
    assert 'Question Bank Quiz Creation/Auto-map Workflow Split' in text('README.md')
    assert 'question-bank-quiz-creation-automap-workflow-split.zip' in text('RUN_CURRENT.md')
    assert text('CHANGELOG.md').startswith('## v25.9.16.7.2.64.12 — Academic AP Sync + External Assignment Workflow Split')
    assert (ROOT / 'docs/RELEASE_v25.9.16.7.2.64.12_QUESTION_BANK_QUIZ_CREATION_AUTOMAP_WORKFLOW_SPLIT.md').exists()
    assert (ROOT / 'docs/CLAUDE_CODE_REVIEW_HANDOFF_V25_9_16_7_2_64_12.md').exists()


def test_analytics_workflow_modules_are_extracted_and_delegated():
    service = text('backend/app/services/learning_analytics/analytics_core_service.py')
    operations = text('backend/app/services/learning_analytics/operations.py')
    results = text('backend/app/services/learning_analytics/results.py')
    assert 'from app.services.learning_analytics.operations import LearningAnalyticsOperationsWorkflowService' in service
    assert 'from app.services.learning_analytics.results import LearningAnalyticsResultsWorkflowService' in service
    assert 'def _analytics_operations_workflow(self) -> LearningAnalyticsOperationsWorkflowService' in service
    assert 'def _analytics_results_workflow(self) -> LearningAnalyticsResultsWorkflowService' in service
    assert 'return self._analytics_operations_workflow().analytics_sla_report' in service
    assert 'return self._analytics_operations_workflow().pilot_acceptance_report' in service
    assert 'return self._analytics_operations_workflow().analytics_uat_evidence_pack' in service
    assert 'return self._analytics_results_workflow().learning_dashboard' in service
    assert 'return self._analytics_results_workflow().class_result_doctor' in service
    assert 'class LearningAnalyticsOperationsWorkflowService' in operations
    assert 'def analytics_sla_report' in operations
    assert 'def pilot_acceptance_report' in operations
    assert 'def analytics_uat_evidence_pack' in operations
    assert 'class LearningAnalyticsResultsWorkflowService' in results
    assert 'def learning_dashboard' in results
    assert 'def analytics_course_class_mapping_reliability_report' in results
    assert 'def behavior_rows' in results


def test_analytics_core_no_longer_hosts_large_report_bodies():
    service = text('backend/app/services/learning_analytics/analytics_core_service.py')
    sla_body = service.split('def analytics_sla_report', 1)[1].split('def pilot_acceptance_report', 1)[0]
    dashboard_body = service.split('def learning_dashboard', 1)[1].split('def export_learning_behavior_csv', 1)[0]
    doctor_body = service.split('def class_result_doctor', 1)[1].split('def behavior_summary', 1)[0]
    assert 'stuck_jobs' not in sla_body
    assert 'class_gap_items' not in sla_body
    assert 'by_class' not in dashboard_body
    assert 'snapshot_count' not in doctor_body
    assert 'analytics_results_workflow' in dashboard_body


def test_workflow_modules_preserve_parent_delegation_and_safe_boundaries():
    operations = text('backend/app/services/learning_analytics/operations.py')
    results = text('backend/app/services/learning_analytics/results.py')
    assert 'def __getattr__(self, name: str) -> Any' in operations
    assert 'return getattr(self.parent, name)' in operations
    assert 'def __getattr__(self, name: str) -> Any' in results
    assert 'return getattr(self.parent, name)' in results
    assert 'never scans raw tracking.log' in operations or 'never scans\n        tracking.log' in operations
    assert 'Read-only learning result' in results


def test_maintainability_contract_tracks_analytics_workflow_split():
    contract = text('backend/app/services/maintainability_contract.py')
    assert 'backend/app/services/learning_analytics/operations.py' in contract
    assert 'backend/app/services/learning_analytics/results.py' in contract
    assert 'backend/app/services/learning_analytics/presentation.py' in contract
    assert 'backend/app/services/learning_analytics/analytics_core_service.py' in contract


def test_v64_4_no_new_alembic_revision():
    assert (ROOT / 'backend/alembic/versions/0052_v25_9_16_7_2_27_learning_behavior_logic_calibration.py').exists()
    assert not list((ROOT / 'backend/alembic/versions').glob('0053*.py'))
