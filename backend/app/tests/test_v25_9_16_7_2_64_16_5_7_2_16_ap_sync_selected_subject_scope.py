from pathlib import Path
import ast

ROOT = Path(__file__).resolve().parents[3]
VERSION = '25.9.16.7.2.64.16.5.7.2.18'


def text(path: str) -> str:
    return (ROOT / path).read_text(encoding='utf-8')


def function_source(path: str, function_name: str) -> str:
    source = text(path)
    tree = ast.parse(source)
    lines = source.splitlines()
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == function_name:
            return '\n'.join(lines[node.lineno - 1: node.end_lineno])
    raise AssertionError(f'missing function {function_name} in {path}')


def test_backend_selected_subject_scope_is_db_driven_and_platform_filtered():
    source = function_source('backend/app/services/academic/ap_sync.py', '_selected_subject_scope')
    assert 'platforms_by_code' in source
    assert "values == {'cms'}" in source
    assert "values == {'udemy'}" in source
    assert 'AcademicSubjectDelivery.active.is_(True)' in source
    assert 'AcademicSubject.active.is_(True)' in source
    assert 'AcademicTerm.term_name' in source
    assert 'AcademicSubjectDelivery.branch' in source
    assert "'selected_subject_codes': sorted(selected)" in source
    assert 'client.get_subjects' not in source


def test_empty_ap_request_resolves_to_subject_management_selection_and_fails_closed_when_empty():
    source = function_source('backend/app/services/academic/ap_sync.py', '_effective_selected_subject_codes')
    assert "selected = set(selection['selected_subject_codes'])" in source
    assert 'if not selected:' in source
    assert 'chưa có môn nào được chọn CMS/Udemy' in source
    assert 'effective = sorted(selected)' in source
    assert 'code not in selected' in source
    assert 'Các mã chưa được chọn' in source


def test_enqueue_persists_explicit_selected_codes_before_fingerprint_and_worker_execution():
    source = function_source('backend/app/services/academic/ap_sync.py', 'enqueue_sync_from_ap_job')
    effective_index = source.index('effective_codes, selection = self._effective_selected_subject_codes')
    assign_index = source.index("request_json['subject_codes'] = effective_codes")
    fingerprint_index = source.index('request_fingerprint = self._ap_request_fingerprint(request_json)')
    assert effective_index < assign_index < fingerprint_index
    assert "'subject_selection': selection" in source
    assert "max(1, len(effective_codes))" in source


def test_sync_options_exposes_selected_subject_counts_without_loading_full_ap_subject_catalog():
    schema = text('backend/app/schemas/academic.py')
    workflow = function_source('backend/app/services/academic/ap_sync.py', 'get_sync_options')
    assert 'selected_subject_codes: list[str]' in schema
    assert 'selected_subject_count: int = 0' in schema
    assert 'cms_subject_count: int = 0' in schema
    assert 'udemy_subject_count: int = 0' in schema
    assert 'selection = self._selected_subject_scope' in workflow
    assert 'return {**options, **selection}' in workflow


def test_ap_sync_ui_sends_immutable_selected_subject_codes_and_blocks_empty_scope():
    page = text('frontend/app/ap-sync/page.tsx')
    types = text('frontend/types/index.ts')
    assert 'subject_codes: optionsByBranch[branch].selected_subject_codes || []' in page
    assert 'Môn được đồng bộ' in page
    assert 'các môn Chưa chọn không được gọi /get-data-cms' in page
    assert '!currentBranchOptions.selected_subject_count' in page
    assert 'totalSelectedSubjects === 0' in page
    assert 'selected_subject_codes: string[]' in types
    assert 'selected_subject_count: number' in types



def test_worker_never_falls_back_to_all_subjects_for_empty_new_or_legacy_jobs():
    worker = text('backend/app/worker.py')
    assert 'AP_SYNC_SELECTED_SUBJECT_SCOPE_EMPTY' in worker
    assert 'effective_codes, legacy_selection = workflow._effective_selected_subject_codes' in worker
    assert "request['subject_codes'] = effective_codes" in worker


def test_runtime_version_contract_for_selected_subject_release():
    assert (ROOT / 'VERSION').read_text().strip() == VERSION
    assert f"app_version: str = '{VERSION}'" in text('backend/app/core/config.py')
    assert f'"version": "{VERSION}"' in text('frontend/package.json')
    assert f"APP_VERSION = '{VERSION}'" in text('Jenkinsfile')
    assert VERSION in text('docker-compose.prod.yml')
