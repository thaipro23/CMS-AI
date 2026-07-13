from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
VERSION = '25.9.16.7.2.64.13'


def text(path: str) -> str:
    return (ROOT / path).read_text(encoding='utf-8')


def test_v64_8_version_and_docs():
    assert f"app_version: str = '{VERSION}'" in text('backend/app/core/config.py')
    assert f'"version": "{VERSION}"' in text('frontend/package.json')
    assert f'NEXT_PUBLIC_APP_VERSION: ${{APP_VERSION:-{VERSION}}}' in text('docker-compose.prod.yml')
    assert 'Teacher Report Cache/Training Report Workflow Split' in text('README.md')
    assert 'teacher-report-cache-training-workflow-split.zip' in text('RUN_CURRENT.md')
    assert text('CHANGELOG.md').startswith('## v25.9.16.7.2.64.13 — Academic AP Sync + External Assignment Workflow Split')
    assert (ROOT / 'docs/RELEASE_v25.9.16.7.2.64.13_TEACHER_REPORT_CACHE_TRAINING_WORKFLOW_SPLIT.md').exists()
    assert (ROOT / 'docs/CLAUDE_CODE_REVIEW_HANDOFF_V25_9_16_7_2_64_13.md').exists()


def test_teacher_report_workflow_is_extracted_and_delegated():
    service = text('backend/app/services/academic_service.py')
    workflow = text('backend/app/services/academic/teacher_report.py')
    assert 'from app.services.academic.teacher_report import AcademicTeacherReportWorkflowService' in service
    assert 'def _training_teacher_report_workflow(self)' in service
    assert 'class AcademicTeacherReportWorkflowService' in workflow
    for name in [
        '_teacher_report_scope_key',
        '_teacher_report_summary_from_items',
        '_training_teacher_report_lite_fast',
        '_training_teacher_report_from_cache',
        'rebuild_training_teacher_report_cache',
        'training_teacher_report',
    ]:
        assert f'def {name}' in workflow
        assert f'_training_teacher_report_workflow().{name}' in service or f'AcademicTeacherReportWorkflowService.{name}' in service


def test_academic_service_no_longer_hosts_teacher_report_bodies():
    service = text('backend/app/services/academic_service.py')
    tail = service.split('def _training_teacher_report_workflow', 1)[1].split('def _upsert_mapping', 1)[0]
    assert 'AcademicTeacherReportSummary(' not in tail
    assert 'teacher_buckets: dict[str, dict[str, Any]]' not in tail
    assert 'fast-lite report for the teacher-management list' not in tail
    assert 'return self._training_teacher_report_workflow().training_teacher_report' in tail
    assert 'return self._training_teacher_report_workflow().rebuild_training_teacher_report_cache' in tail


def test_teacher_report_workflow_preserves_cache_lite_export_semantics():
    workflow = text('backend/app/services/academic/teacher_report.py')
    assert 'Fast exact-lite report for the teacher-management list' in workflow
    assert "'cache': {'status': 'lite'" in workflow
    assert 'AcademicTeacherReportSummary' in workflow
    assert 'rebuild_training_teacher_report_cache' in workflow
    assert 'include_students' in workflow
    assert 'student_watch_rows' in workflow
    assert 'summary_scope' in workflow
    assert 'current_page' in workflow
    assert 'filtered' in workflow


def test_worker_and_routes_still_call_academic_service_contract():
    route = text('backend/app/api/routes/academic.py')
    worker = text('backend/app/worker.py')
    assert 'AcademicService(db).training_teacher_report(' in route
    assert 'service.rebuild_training_teacher_report_cache(worker_user' in worker
    assert 'service.training_teacher_report(' in worker


def test_maintainability_contract_tracks_teacher_report_workflow_split():
    contract = text('backend/app/services/maintainability_contract.py')
    assert 'backend/app/services/academic/teacher_report.py' in contract
    assert 'backend/app/services/academic/identity.py' in contract
    assert 'backend/app/services/academic/sync_enrollment.py' in contract
    assert 'backend/app/services/academic/access.py' in contract
    assert 'backend/app/services/academic/roster.py' in contract
    assert 'backend/app/services/academic_service.py' in contract


def test_v64_8_no_new_alembic_revision():
    assert (ROOT / 'backend/alembic/versions/0052_v25_9_16_7_2_27_learning_behavior_logic_calibration.py').exists()
    assert not list((ROOT / 'backend/alembic/versions').glob('0053*.py'))
