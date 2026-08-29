import os
from pathlib import Path

os.environ.setdefault('DATABASE_URL', 'sqlite+pysqlite:///:memory:')

from app.services.ux_acceptance import UxAcceptanceService

ROOT = Path(__file__).resolve().parents[3]
VERSION = '25.9.16.7.2.64.14'


def text(path: str) -> str:
    return (ROOT / path).read_text(encoding='utf-8')


def test_v64_14_version_package_and_database_boundary():
    assert f"app_version: str = '{VERSION}'" in text('backend/app/core/config.py')
    assert f'"version": "{VERSION}"' in text('frontend/package.json')
    assert f'APP_VERSION={VERSION}' in text('.env.production.example')
    assert f'NEXT_PUBLIC_APP_VERSION: ${{APP_VERSION:-{VERSION}}}' in text('docker-compose.prod.yml')
    assert 'Training/Ops UX Completion + UAT UX Acceptance Gate' in text('README.md')
    assert not list((ROOT / 'backend/alembic/versions').glob('0053*.py'))
    assert (ROOT / 'backend/alembic/versions/0052_v25_9_16_7_2_27_learning_behavior_logic_calibration.py').exists()


def test_v64_14_training_and_ops_indexes_use_shared_enterprise_contract():
    expected = {
        'frontend/app/teacher-management/page.tsx': 'useAcademicTableState',
        'frontend/app/student-management/page.tsx': 'useAcademicTableState',
        'frontend/app/jobs/page.tsx': 'useOpsTableState',
        'frontend/app/audit/page.tsx': 'useOpsTableState',
    }
    for path, hook in expected.items():
        source = text(path)
        assert 'EnterpriseDataTable' in source
        assert hook in source
        assert 'loading=' in source
        assert 'emptyTitle=' in source
        assert 'onPageChange=' in source
        assert 'onPageSizeChange=' in source
        assert 'density' in source

    jobs = text('frontend/app/jobs/page.tsx')
    assert "status === 'active'" in jobs
    assert "row.status !== status" in jobs
    assert 'page > totalPages' in text('frontend/app/teacher-management/page.tsx')
    assert 'page > totalPages' in text('frontend/app/student-management/page.tsx')


def test_v64_14_url_state_hooks_cover_required_filters():
    academic = text('frontend/hooks/useAcademicTableState.ts')
    ops = text('frontend/hooks/useOpsTableState.ts')
    for token in ('q', 'status', 'page', 'page_size', 'density', 'term_id', 'branch', 'campus'):
        assert token in academic
    for token in ('q', 'status', 'group', 'error_type', 'actor_id', 'page', 'page_size', 'density'):
        assert token in ops


def test_v64_14_audit_search_export_reuses_rbac_visibility():
    route = text('backend/app/api/routes/audit.py')
    api = text('frontend/lib/api.ts')
    page = text('frontend/app/audit/page.tsx')
    assert 'def _apply_audit_filters' in route
    assert 'def _visible_audit_row' in route
    assert 'def _csv_cell' in route and "{'=', '+', '-', '@'}" in route
    assert 'search: str | None' in route
    assert "@router.get('/export.csv')" in route
    assert 'text/csv' in route and "buffer.write('\\ufeff')" in route
    assert 'downloadAuditLogsCsv' in api
    assert 'downloadAuditLogsCsv' in page


def test_v64_14_status_and_progress_are_not_color_only():
    badge = text('frontend/components/ui/StatusBadge.tsx')
    jobs = text('frontend/app/jobs/page.tsx')
    table = text('frontend/components/table/EnterpriseDataTable.tsx')
    assert 'status-icon' in badge
    assert 'aria-hidden="true"' in badge
    assert 'role="progressbar"' in jobs
    assert 'aria-valuenow' in jobs
    assert 'tabIndex={0}' in table
    assert 'có thể cuộn ngang' in table


def test_v64_14_ux_acceptance_gate_is_read_only_and_visible():
    service = text('backend/app/services/ux_acceptance.py')
    health = text('backend/app/api/routes/health.py')
    ops = text('frontend/app/ops/readiness/page.tsx')
    api = text('frontend/lib/api/readiness.ts')
    script = text('scripts/uat-ux-acceptance-report.sh')
    assert 'static_source_scan_no_db_no_external_calls_no_mutation' in service
    assert "@router.get('/health/uat-ux-acceptance'" in health
    assert 'getUxAcceptance' in api and 'getUxAcceptance' in ops
    assert 'UAT UX acceptance' in ops
    assert 'API_BASE_URL' in script and '/health/uat-ux-acceptance' in script

    report = UxAcceptanceService(ROOT).report()
    assert report['status'] == 'READY'
    assert report['blocker_count'] == 0
    assert report['warning_count'] == 0
    assert report['passed_count'] == report['check_count']
    assert report['safe_policy'] == 'static_source_scan_no_db_no_external_calls_no_mutation'


def test_v64_14_production_gate_and_maintainability_track_ux_contract():
    production = text('backend/app/services/production_pilot_final.py')
    maintainability = text('backend/app/services/maintainability_contract.py')
    assert 'UxAcceptanceService' in production
    assert "'uat_ux_acceptance'" in production
    assert '/api/health/uat-ux-acceptance' in production
    for path in (
        'backend/app/services/ux_acceptance.py',
        'frontend/hooks/useAcademicTableState.ts',
        'frontend/hooks/useOpsTableState.ts',
        'scripts/uat-ux-acceptance-report.sh',
    ):
        assert path in maintainability


def test_v64_14_preserves_bank_and_assignment_boundaries():
    academic = text('backend/app/api/routes/academic.py')
    assignment_service = text('backend/app/services/academic/assignment_external.py')
    student_page = text('frontend/app/student-management/page.tsx')
    context = text('AI_SERVER_PROJECT_CONTEXT_V25_9_16_7_2_64_14.md')
    assert 'reject_assignment_score_write' in academic
    assert 'ASSIGNMENT_SCORE_EXTERNALIZED' in assignment_service and 'status_code=410' in assignment_service
    assert 'Workflow Assignment' not in student_page
    assert 'Release và Quiz là workflow đầu ra' in context
    assert 'một Phiên bản môn cuối theo học kỳ' in context
