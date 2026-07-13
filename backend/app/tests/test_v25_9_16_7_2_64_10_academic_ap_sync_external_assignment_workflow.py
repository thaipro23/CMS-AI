
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
VERSION = '25.9.16.7.2.64.12'


def text(path: str) -> str:
    return (ROOT / path).read_text(encoding='utf-8')


def test_v64_10_version_and_docs():
    assert f"app_version: str = '{VERSION}'" in text('backend/app/core/config.py')
    assert f'"version": "{VERSION}"' in text('frontend/package.json')
    assert f'NEXT_PUBLIC_APP_VERSION: ${{APP_VERSION:-{VERSION}}}' in text('docker-compose.prod.yml')
    assert 'Academic AP Sync + External Assignment Workflow Split' in text('README.md')
    assert 'RUN_V25_9_16_7_2_64_12.md' in text('README.md')
    assert text('CHANGELOG.md').startswith('## v25.9.16.7.2.64.12 — Academic AP Sync + External Assignment Workflow Split')


def test_ap_sync_workflow_is_split_from_route():
    workflow = text('backend/app/services/academic/ap_sync.py')
    route = text('backend/app/api/routes/academic.py')
    assert 'class AcademicAPSyncWorkflowService' in workflow
    assert 'def enqueue_sync_from_ap_job' in workflow
    assert 'academic_ap_sync_task.delay(run.id)' in workflow
    assert 'def sync_from_ap' in workflow
    assert 'AcademicAPSyncWorkflowService(db).enqueue_sync_from_ap_job(payload, user=user)' in route
    assert 'AcademicAPSyncWorkflowService(db).sync_from_ap(payload, user=user)' in route
    assert 'AcademicAPSyncWorkflowService(db).sync_from_json(payload, user=user)' in route
    assert 'AcademicAPSyncWorkflowService(db).get_sync_options' in route


def test_assignment_score_entry_is_externalized_backend():
    rbac = text('backend/app/services/business_rbac.py')
    route = text('backend/app/api/routes/academic.py')
    facade = text('backend/app/services/academic/assignment_external.py')
    assert 'academic.manage_assignment_scores' not in rbac
    assert 'def can_manage_assignment_scores_for_campus' in rbac
    assert 'return False' in rbac
    assert 'ASSIGNMENT_SCORE_EXTERNALIZED' in facade
    assert 'status_code=410' in facade
    assert 'reject_assignment_score_write()' in route
    assert "metadata_json = {'source': 'manual_ui_assignment_defense_workflow'" not in route
    assert "action='academic.assignment_defense_score.save'" not in route


def test_assignment_score_entry_is_removed_from_frontend():
    page = text('frontend/app/student-management/classes/[classId]/page.tsx')
    app_context = text('frontend/context/AppContext.tsx')
    assert "saveAcademicClassAssignmentDefenseScores" not in page
    assert "Workflow Assignment" not in page
    assert 'Assignment: đọc từ hệ thống ngoài' in page
    assert 'canManageAssignmentScores = false' in page
    assert 'manage_assignment_scores' not in app_context


def test_maintainability_contract_tracks_new_modules():
    service = text('backend/app/services/maintainability_contract.py')
    assert 'backend/app/services/academic/ap_sync.py' in service
    assert 'backend/app/services/academic/assignment_external.py' in service


def test_no_new_alembic_revision():
    assert not list((ROOT / 'backend/alembic/versions').glob('0053*.py'))
    assert (ROOT / 'backend/alembic/versions/0052_v25_9_16_7_2_27_learning_behavior_logic_calibration.py').exists()
