from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
VERSION = '25.9.16.7.2.64.16.5.7.2.3'


def read(rel: str) -> str:
    return (ROOT / rel).read_text(encoding='utf-8')


def test_version_is_synchronized_for_visual_hotfix():
    targets = [
        'backend/app/core/config.py',
        'frontend/package.json',
        'frontend/package-lock.json',
        'e2e/package.json',
        'e2e/package-lock.json',
        'frontend/Dockerfile',
        'docker-compose.prod.yml',
        '.env.production.example',
        '.env.uat-http.example',
        '.github/workflows/ci.yml',
    ]
    assert all(VERSION in read(rel) for rel in targets)


def test_chapter_actions_replace_duplicate_kpis_and_remove_release_qa_panel():
    source = read('frontend/app/bank/_components/pages/ChapterWorkspacePage.tsx')
    assert 'Tạo câu hỏi (${usedQuestionCount}/${chapterQuestionLimit})' in source
    assert 'Duyệt câu hỏi (${stats.pending} câu chờ duyệt)' in source
    assert 'chapter-command-summary' not in source
    assert 'QA publish/rollback' not in source
    assert 'bank-release-audit-panel' not in source
    assert 'Kiểm tra bộ đề' not in source


def test_topbar_has_clickable_breadcrumb_contract_and_nested_bank_pages_use_it():
    shell = read('frontend/components/layout/AppShell.tsx')
    header = read('frontend/components/layout/PageHeader.tsx')
    context = read('frontend/components/layout/PageShellContext.tsx')
    assert 'enterprise-topbar-breadcrumbs' in shell
    assert '<Link href={item.href}>' in shell
    assert 'breadcrumbs?: PageBreadcrumb[]' in header
    assert 'breadcrumbs?: PageBreadcrumb[]' in context
    for rel in [
        'frontend/app/bank/_components/pages/DepartmentSubjectsPage.tsx',
        'frontend/app/bank/_components/pages/SubjectVersionsPage.tsx',
        'frontend/app/bank/_components/pages/SubjectVersionChaptersPage.tsx',
        'frontend/app/bank/_components/pages/ChapterWorkspacePage.tsx',
    ]:
        source = read(rel)
        assert 'breadcrumbs={[' in source
        assert '<ContextBackLink' not in source


def test_quiz_and_history_remove_duplicate_navigation_actions():
    quiz = read('frontend/app/bank/quiz/page.tsx')
    history = read('frontend/app/bank/_components/pages/BankHistoryPage.tsx')
    assert 'secondaryActions=' not in quiz
    assert '>Ngân hàng đề</Link>' not in quiz
    assert '>Lịch sử Quiz</Link>' not in quiz
    assert 'Tạo Quiz trên CMS' not in history
    assert 'primaryAction=' not in history


def test_teacher_identity_is_text_only_and_filters_are_not_sticky():
    page = read('frontend/app/teacher-management/page.tsx')
    css = read('frontend/styles/frontend-visual-ergonomics-hotfix.css')
    assert '<span className="teacher-avatar">' not in page
    assert 'teacher-identity-text-only' in page
    assert '.teacher-management-page .teacher-filter-bar' in css
    assert 'position: static !important' in css
    assert '.teacher-management-page .teacher-avatar { display: none !important; }' in css


def test_main_content_scroll_and_readable_weight_contract_are_last():
    layout = read('frontend/app/layout.tsx')
    css = read('frontend/styles/frontend-visual-ergonomics-hotfix.css')
    assert layout.rfind("import '../styles/frontend-visual-ergonomics-hotfix.css'") > layout.rfind("import '../styles/full-frontend-design-contract.css'")
    assert 'overflow-y: auto !important' in css
    assert '.enterprise-content.student-management-page' in css
    assert '.question-review-dialog .question-prompt' in css
    assert 'font-weight: 600 !important' in css
    assert 'grid-template-columns: repeat(2, minmax(0, 1fr)) !important' in css
