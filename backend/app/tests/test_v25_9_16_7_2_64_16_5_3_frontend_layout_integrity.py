import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
VERSION = '25.9.16.7.2.64.16.5.3'

def read(path: str) -> str:
    return (ROOT / path).read_text(encoding='utf-8')

def test_version_and_database_boundary():
    package=json.loads(read('frontend/package.json')); lock=json.loads(read('frontend/package-lock.json'))
    assert f"app_version: str = '{VERSION}'" in read('backend/app/core/config.py')
    assert package['version']==VERSION and lock['version']==VERSION and lock['packages']['']['version']==VERSION
    assert f'APP_VERSION={VERSION}' in read('.env.production.example')
    assert f'NEXT_PUBLIC_APP_VERSION: ${{APP_VERSION:-{VERSION}}}' in read('docker-compose.prod.yml')
    assert not list((ROOT/'backend/alembic/versions').glob('0053*.py'))
    assert (ROOT/'backend/alembic/versions/0052_v25_9_16_7_2_27_learning_behavior_logic_calibration.py').exists()

def test_layout_integrity_stylesheet_is_loaded_last():
    layout=read('frontend/app/layout.tsx'); css=read('frontend/styles/layout-integrity.css')
    assert "import '../styles/layout-integrity.css'" in layout
    assert layout.rfind('layout-integrity.css')>layout.rfind('global-visual-polish.css')
    for token in ('--layout-section-gap','--layout-card-padding','.enterprise-page-header','.workspace-section-body','.enterprise-data-table th,','.side-drawer-body'): assert token in css

def test_active_frontend_css_has_no_negative_layout_margins():
    hits=[]; paths=sorted((ROOT/'frontend/styles').glob('*.css'))+[ROOT/'frontend/app/globals.css']
    for path in paths:
        lines=path.read_text(encoding='utf-8').splitlines()
        for index,line in enumerate(lines,1):
            if re.search(r'margin(?:-[a-z]+)?\s*:\s*-\d',line) and 'sr-only' not in ''.join(lines[max(0,index-3):index+1]): hits.append(f'{path.relative_to(ROOT)}:{index}:{line.strip()}')
    assert hits==[]

def test_readable_regions_use_flow_spacing_and_clear_dividers():
    css=read('frontend/styles/layout-integrity.css')
    assert 'flex-wrap: wrap' in css and 'gap: var(--layout-section-gap)' in css
    assert '.workspace-section-body > .enterprise-table-shell' in css and 'margin: 0 !important' in css
    assert 'border-bottom: 1px solid var(--layout-divider)' in css and 'border-right: 1px solid var(--layout-divider-soft)' in css
    assert '.visual-section-card::after' in css and '.dashboard-hero-glow' in css

def test_tables_keep_full_content_without_overlap_or_auto_hiding():
    table=read('frontend/components/table/EnterpriseDataTable.tsx'); hotfix=read('frontend/styles/production-ux-browser-hotfix.css'); integrity=read('frontend/styles/layout-integrity.css')
    assert 'data-column-contract="full-content"' in table and 'responsiveHiddenColumns' not in table
    assert 'display: table-cell !important' in hotfix
    assert 'overflow-wrap: anywhere' in integrity and 'scrollbar-gutter: stable' in integrity
    assert '.sticky-left::after' in integrity and '.sticky-right::before' in integrity

def test_entire_frontend_is_covered_by_shared_contract():
    pages=[p for p in (ROOT/'frontend/app').rglob('page.tsx') if 'ops/readiness' not in p.as_posix()]
    assert len(pages)>=30
    report=read('scripts/frontend-layout-integrity-report.sh')
    assert 'frontend-layout-integrity.json' in report and 'active_page_count' in report and 'negative_margin_free' in report
    for forbidden in ('INSERT INTO','DELETE FROM','docker compose down -v'): assert forbidden not in report

def test_no_bootstrap_jquery_or_business_contract_change():
    package=read('frontend/package.json').lower()
    assert 'bootstrap' not in package and 'react-bootstrap' not in package and 'jquery' not in package
    assignment=read('backend/app/services/academic/assignment_external.py')
    assert 'ASSIGNMENT_SCORE_EXTERNALIZED' in assignment and 'status_code=410' in assignment

def test_quiz_auto_map_runtime_symbols_are_imported_and_executable(monkeypatch):
    monkeypatch.setenv('DATABASE_URL','sqlite+pysqlite:///:memory:')
    import asyncio
    from types import SimpleNamespace
    from app.models.question_bank import Department, Subject, SubjectOffering
    from app.services.question_bank.quiz_creation import QuestionBankQuizCreationWorkflowService
    class FakeQuery:
        def __init__(self,rows):self.rows=rows
        def filter(self,*_args,**_kwargs):return self
        def order_by(self,*_args,**_kwargs):return self
        def first(self):return self.rows[0] if self.rows else None
        def all(self):return list(self.rows)
    subject=Subject(id='subject-1',department_id='department-1',code='COM1071',name='Tin học 1')
    department=Department(id='department-1',code='CNTT',name='Công nghệ thông tin')
    class FakeDb:
        def query(self,model):
            if model is Subject:return FakeQuery([subject])
            if model is SubjectOffering:return FakeQuery([])
            return FakeQuery([])
        def get(self,model,item_id):return department if model is Department and item_id==department.id else None
    class FakeService:
        db=FakeDb()
        @staticmethod
        def _chapter_display_name(chapter):return chapter.title
    workflow=QuestionBankQuizCreationWorkflowService(FakeService())
    section,score,reason=workflow._match_chapter_to_section(SimpleNamespace(title='Bài 1'),[{'block_id':'section-1','display_name':'Bài 1'}],set())
    assert section and section['block_id']=='section-1' and score==1.0 and reason=='Trùng tên Section/Bài'
    preview=asyncio.run(workflow.preview_quiz_auto_map(openedx_course_id='course-v1:FPT+COM1071+SU26'))
    assert preview['subject']['department_name']=='Công nghệ thông tin'
    assert preview['can_apply'] is False and 'version môn' in preview['message'].lower()

def test_page_title_is_in_topbar_and_page_layout_classes_are_on_main():
    app_shell=read('frontend/components/layout/AppShell.tsx'); page_header=read('frontend/components/layout/PageHeader.tsx'); page_context=read('frontend/components/layout/PageShellContext.tsx')
    assert '<h1>{pageChrome?.title || pageLabel(pathname)}</h1>' in app_shell
    assert 'className={`enterprise-content ${pageLayoutClass}`.trim()}' in app_shell
    assert 'enterprise-page-header-copy' not in page_header and 'enterprise-page-description' not in page_header
    assert 'enterprise-page-header-actions-only' in page_header
    assert 'return <>{children}</>' in page_context and 'useLayoutEffect' in page_context and 'useLayoutEffect' in page_header
    assert 'layoutRegistrationRef.current = registrationId' in app_shell

def test_row_actions_are_visible_and_not_hidden_in_ellipsis_menu():
    shared=read('frontend/app/bank/_components/shared.tsx')
    active='\n'.join(p.read_text(encoding='utf-8') for p in sorted((ROOT/'frontend').rglob('*.tsx')) if 'node_modules' not in p.parts and '.next' not in p.parts)
    assert 'entity-actions-trigger' not in shared and 'entity-actions-menu' not in shared
    assert '⋮' not in active and '•••' not in active and 'row-action-menu' not in active
    assert '<button type="button" className="btn small secondary" onClick={onEdit}>Sửa</button>' in shared
    assert '<button type="button" className="btn small danger-soft" onClick={onDelete}>Xóa</button>' in shared

def test_backend_runtime_name_audit_is_part_of_release_gates():
    script=read('scripts/backend-runtime-name-audit.sh'); review=read('scripts/claude-code-review-pack.sh'); uat=read('scripts/uat-build-gate.sh')
    assert 'symtable.symtable' in script and 'undefined_global_count' in script and 'quiz_imports_sequence_matcher' in script
    assert 'quiz_imports_department' in script and 'quiz_imports_normalize_difficulty' in script
    assert 'BACKEND_RUNTIME_NAME_AUDIT' in review and 'BACKEND_RUNTIME_NAME_AUDIT' in uat


def test_next_build_workers_and_output_tracing_are_bounded():
    config=read('frontend/next.config.js')
    assert "output: 'standalone'" in config
    assert 'cpus: 2' in config
    assert 'outputFileTracingRoot: __dirname' in config
