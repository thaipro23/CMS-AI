from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
VERSION = '25.9.16.7.2.64.16.5.1'


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding='utf-8')


def test_version_and_database_boundary():
    assert f"app_version: str = '{VERSION}'" in read('backend/app/core/config.py')
    assert f'"version": "{VERSION}"' in read('frontend/package.json')
    migrations = sorted((ROOT / 'backend/alembic/versions').glob('*.py'))
    assert migrations[-1].name == '0052_v25_9_16_7_2_27_learning_behavior_logic_calibration.py'
    assert not any(path.name.startswith('0053') for path in migrations)


def test_quiz_auto_map_imports_department_model():
    source = read('backend/app/services/question_bank/quiz_creation.py')
    import_block = source.split('from app.models.question_bank import (', 1)[1].split(')', 1)[0]
    assert 'Department,' in import_block
    assert 'self.db.get(Department, subject.department_id)' in source


def test_sidebar_has_no_helper_text_or_session_footer():
    source = read('frontend/components/layout/AppShell.tsx')
    assert 'description: string' not in source
    assert 'item.description' not in source
    assert 'enterprise-sidebar-session' not in source
    assert '<small>FPT Polytechnic</small>' not in source
    assert '<span className="enterprise-user-summary"><b>{ROLE_LABELS[role]}</b></span>' in source


def test_table_keeps_full_content_and_uses_natural_widths():
    source = read('frontend/components/table/EnterpriseDataTable.tsx')
    css = read('frontend/styles/production-ux-browser-hotfix.css')
    assert ':columns:full-v2' in source
    assert 'const defaultKeys = useMemo(() => columns.map' in source
    assert 'responsiveHiddenColumns' not in source
    assert 'enterprise-responsive-details-row' not in source
    assert 'data-column-contract="full-content"' in source
    assert 'table-layout: auto !important' in css
    assert 'display: table-cell !important' in css
    assert '-webkit-line-clamp: unset !important' in css


def test_bank_breadcrumbs_do_not_repeat_current_page_label():
    subjects = read('frontend/app/bank/_components/pages/DepartmentSubjectsPage.tsx')
    versions = read('frontend/app/bank/_components/pages/SubjectVersionsPage.tsx')
    chapters = read('frontend/app/bank/_components/pages/SubjectVersionChaptersPage.tsx')
    assert "{ label: department?.name || 'Bộ môn' }]}" in subjects
    assert "title=\"Môn học\"" in subjects
    assert "{ label: subject?.code || 'Môn' }]}" in versions
    assert "title=\"Phiên bản môn\"" in versions
    assert "{ label: offering?.code || 'Phiên bản môn' }]}" in chapters
    assert "title=\"Bài học\"" in chapters


def test_hotfix_css_is_loaded_last():
    layout = read('frontend/app/layout.tsx')
    assert layout.index("production-ux-browser-hotfix.css") > layout.index("production-ux-acceptance.css")
