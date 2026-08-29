from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
VERSION = '25.9.16.7.2.64.13'


def text(path: str) -> str:
    return (ROOT / path).read_text(encoding='utf-8')


def test_v64_12_version_sync_and_no_migration():
    assert f"app_version: str = '{VERSION}'" in text('backend/app/core/config.py')
    assert f'"version": "{VERSION}"' in text('frontend/package.json')
    assert f'NEXT_PUBLIC_APP_VERSION: ${{APP_VERSION:-{VERSION}}}' in text('docker-compose.prod.yml')
    assert 'Bank Workflow UX Completion' in text('README.md')
    assert not list((ROOT / 'backend/alembic/versions').glob('0053*.py'))
    assert (ROOT / 'backend/alembic/versions/0052_v25_9_16_7_2_27_learning_behavior_logic_calibration.py').exists()


def test_v64_12_bank_hierarchy_is_five_levels_and_output_workflows_are_separate():
    shell = text('frontend/components/layout/AppShell.tsx')
    release = text('docs/RELEASE_v25.9.16.7.2.64.12_ENTERPRISE_NAVIGATION_DATATABLE_UX_FOUNDATION.md')
    assert 'Bộ môn → Môn → Phiên bản → Bài → Câu hỏi' in shell
    assert 'Bộ môn → Môn học → Phiên bản môn theo học kỳ → Bài/Chapter → Câu hỏi' in release
    assert 'Release và Quiz không phải node điều hướng trong cây Bank' in release
    assert "label: 'Tạo Quiz từ bộ đề'" in shell
    assert "group: 'bank'" in shell


def test_v64_12_one_subject_version_per_term_guard():
    service = text('backend/app/services/question_bank_service.py')
    assert 'func.upper(SubjectOffering.term) == term_code.upper()' in service
    assert 'Mỗi học kỳ chỉ có một phiên bản môn cuối' in service
    assert 'SubjectOffering.id != item.id' in service


def test_v64_12_shared_navigation_and_table_foundation_exists():
    breadcrumbs = text('frontend/components/navigation/Breadcrumbs.tsx')
    table = text('frontend/components/table/EnterpriseDataTable.tsx')
    states = text('frontend/components/table/TableStates.tsx')
    url_state = text('frontend/hooks/useUrlTableState.ts')
    css = text('frontend/styles/enterprise-ui.css')
    assert 'export function Breadcrumbs' in breadcrumbs
    assert 'export function EnterpriseDataTable' in table
    assert 'Cột hiển thị' in table and 'Mật độ' in table
    assert 'Chọn tất cả bản ghi trên trang' in table
    assert 'TableEmptyState' in states and 'TableErrorState' in states and 'TableLoadingState' in states
    assert 'page_size' in url_state and 'density' in url_state and "router.replace" in url_state
    assert '.enterprise-table-scroll' in css and 'overflow: auto' in css
    assert '.sticky-left' in css and '.sticky-right' in css


def test_v64_12_bank_departments_uses_foundation_and_url_state():
    page = text('frontend/app/bank/_components/pages/DepartmentsPage.tsx')
    route = text('frontend/app/bank/departments/page.tsx')
    shared = text('frontend/app/bank/_components/shared.tsx')
    assert 'useUrlTableState' in page
    assert '<EnterpriseDataTable' in page
    assert 'tableId="bank-departments"' in page
    assert 'sticky' in page
    assert 'Suspense' in route
    assert '<Breadcrumbs' in shared


def test_v64_12_maintainability_contract_tracks_new_modules():
    service = text('backend/app/services/maintainability_contract.py')
    for path in [
        'frontend/components/navigation/Breadcrumbs.tsx',
        'frontend/components/table/EnterpriseDataTable.tsx',
        'frontend/components/table/TableStates.tsx',
        'frontend/hooks/useUrlTableState.ts',
        'frontend/styles/enterprise-ui.css',
    ]:
        assert path in service
