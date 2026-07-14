import json
import os
from pathlib import Path

os.environ.setdefault('DATABASE_URL', 'sqlite+pysqlite:///:memory:')

ROOT = Path(__file__).resolve().parents[3]
VERSION = '25.9.16.7.2.64.16.2'


def text(path: str) -> str:
    return (ROOT / path).read_text(encoding='utf-8')


def test_v64_16_2_version_and_database_boundary():
    package = json.loads(text('frontend/package.json'))
    assert f"app_version: str = '{VERSION}'" in text('backend/app/core/config.py')
    assert package['version'] == VERSION
    assert f'APP_VERSION={VERSION}' in text('.env.production.example')
    assert f'NEXT_PUBLIC_APP_VERSION: ${{APP_VERSION:-{VERSION}}}' in text('docker-compose.prod.yml')
    assert f'ARG NEXT_PUBLIC_APP_VERSION={VERSION}' in text('frontend/Dockerfile')
    assert not list((ROOT / 'backend/alembic/versions').glob('0053*.py'))
    assert (ROOT / 'backend/alembic/versions/0052_v25_9_16_7_2_27_learning_behavior_logic_calibration.py').exists()


def test_v64_16_2_quiz_page_is_three_step_full_width_workbench():
    page = text('frontend/app/bank/quiz/page.tsx')
    assert "EnterpriseDataTable" in page
    assert 'quiz-workflow-steps' in page
    assert 'Map khóa học' in page
    assert 'Chọn phạm vi' in page
    assert 'Tạo trên CMS' in page
    assert 'tableId="bank-quiz-course-mappings"' in page
    assert 'tableId="bank-quiz-course-history"' in page
    assert 'quiz-workbench-grid' not in page
    assert 'quiz-settings-panel' not in page
    assert 'difficulty_medium: quizConfig.medium' in page
    assert page.count('difficulty_medium: quizConfig.medium') == 2  # preview + apply


def test_v64_16_2_quiz_mapping_prioritizes_decision_columns():
    page = text('frontend/app/bank/quiz/page.tsx')
    for token in (
        "key: 'chapter'", "key: 'cms_mapping'", "key: 'action'",
        "key: 'readiness'", "key: 'actions'",
    ):
        assert token in page
    assert "key: 'match'" in page and "defaultVisible: false" in page
    assert 'Không tạo' in page
    assert 'missingRequirementLabel' in page


def test_v64_16_2_bank_hierarchy_uses_compact_page_and_column_contract():
    routes = (
        'frontend/app/bank/_components/pages/DepartmentsPage.tsx',
        'frontend/app/bank/_components/pages/DepartmentSubjectsPage.tsx',
        'frontend/app/bank/_components/pages/SubjectVersionsPage.tsx',
        'frontend/app/bank/_components/pages/SubjectVersionChaptersPage.tsx',
    )
    for route in routes:
        source = text(route)
        assert '<PageHeader' in source, route
        assert '<QuickSearchBox' not in source, route
        assert "kind: 'index'" in source, route
        assert "kind: 'number'" in source, route
        assert "kind: 'actions'" in source, route
        assert 'stickyOffset:' not in source, route
        assert "priority: 'optional'" in source, route


def test_v64_16_2_question_rows_are_preview_first_without_inline_approve_button():
    table = text('frontend/app/bank/_components/BankQuestionEnterpriseTable.tsx')
    assert 'question-row-actions-review-first' in table
    assert 'Mở duyệt' in table
    assert 'onApprove(row)' not in table
    assert "key: 'concept'" in table and 'defaultVisible: false' in table
    assert "key: 'source'" in table and 'defaultVisible: false' in table
    assert '•••' in table


def test_v64_16_2_history_is_inline_tabbed_workspace_not_modal_tables():
    page = text('frontend/app/bank/_components/pages/BankHistoryPage.tsx')
    assert 'useUrlTableState' in page
    assert 'history-view-tabs' in page
    assert 'tableId="bank-history-quizzes"' in page
    assert 'tableId="bank-history-releases"' in page
    assert '<Modal' not in page
    assert '<EnterpriseDataTable' in page


def test_v64_16_2_css_contract_is_loaded():
    layout = text('frontend/app/layout.tsx')
    css = text('frontend/styles/bank-workflow-ux.css')
    assert "import '../styles/bank-workflow-ux.css'" in layout
    for token in (
        '.quiz-workflow-steps', '.quiz-course-form', '.quiz-summary-strip',
        '.quiz-mapping-action-bar', '.history-view-tabs',
        '.question-row-actions-review-first',
    ):
        assert token in css


def test_v64_16_2_keeps_business_boundaries():
    package = text('frontend/package.json').lower()
    assert 'bootstrap' not in package
    assert 'react-bootstrap' not in package
    assignment = text('backend/app/services/academic/assignment_external.py')
    assert 'ASSIGNMENT_SCORE_EXTERNALIZED' in assignment and 'status_code=410' in assignment
    release = text('backend/app/services/question_bank/release_publish.py')
    assert 'BankReleaseQuestion' in release
    rbac = text('backend/app/services/business_rbac.py')
    for role in ('SYSTEM_ADMIN', 'DEPARTMENT_HEAD', 'SUBJECT_OWNER', 'QUESTION_REVIEWER', 'CAMPUS_OWNER', 'TEACHER_ASSIGNED'):
        assert role in rbac
