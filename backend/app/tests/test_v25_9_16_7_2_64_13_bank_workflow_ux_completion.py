from io import BytesIO
import os
from pathlib import Path

from openpyxl import load_workbook

os.environ.setdefault('DATABASE_URL', 'sqlite+pysqlite:///:memory:')

from app.services.question_bank.import_export import build_import_template, parse_import_workbook

ROOT = Path(__file__).resolve().parents[3]
VERSION = '25.9.16.7.2.64.13'


def text(path: str) -> str:
    return (ROOT / path).read_text(encoding='utf-8')


def test_v64_13_version_docs_and_no_migration():
    assert f"app_version: str = '{VERSION}'" in text('backend/app/core/config.py')
    assert f'"version": "{VERSION}"' in text('frontend/package.json')
    assert 'Bank Workflow UX Completion' in text('README.md')
    assert 'Bộ môn → Môn học → một Phiên bản môn cuối theo học kỳ → Bài/Chapter → Câu hỏi' in text('docs/RELEASE_v25.9.16.7.2.64.13_BANK_WORKFLOW_UX_COMPLETION.md')
    assert not list((ROOT / 'backend/alembic/versions').glob('0053*.py'))


def test_v64_13_hierarchy_pages_use_enterprise_table_and_url_state():
    for path in [
        'frontend/app/bank/_components/pages/DepartmentSubjectsPage.tsx',
        'frontend/app/bank/_components/pages/SubjectVersionsPage.tsx',
        'frontend/app/bank/_components/pages/SubjectVersionChaptersPage.tsx',
    ]:
        source = text(path)
        assert 'EnterpriseDataTable' in source
        assert 'useUrlTableState' in source
        assert 'pageSize' in source
        assert 'sticky' in source


def test_v64_13_question_table_server_paging_selection_and_preview():
    route = text('backend/app/api/routes/question_bank_v2.py')
    page = text('frontend/app/bank/_components/pages/ChapterWorkspacePage.tsx')
    table = text('frontend/app/bank/_components/BankQuestionEnterpriseTable.tsx')
    assert "@router.get('/bank-versions/{bank_version_id}/questions/page'" in route
    assert 'getBankVersionQuestionOffsetPage' in page
    assert 'Chọn toàn bộ' in page and 'kết quả lọc' in page
    assert 'BankQuestionEnterpriseTable' in page
    assert 'Xem trước câu hỏi' in page
    assert 'Xem trước Release' in page
    assert 'Chọn tất cả bản ghi trên trang' in text('frontend/components/table/EnterpriseDataTable.tsx')
    assert 'sticky' in table


def test_v64_13_import_preview_error_export_and_worker_contract():
    route = text('backend/app/api/routes/question_bank_v2.py')
    worker = text('backend/app/worker.py')
    service = text('backend/app/services/question_bank/import_export.py')
    modal = text('frontend/app/bank/_components/BankQuestionImportModal.tsx')
    assert 'questions/import-template.xlsx' in route
    assert 'questions/import-preview' in route
    assert 'questions/import-errors/{preview_token}.xlsx' in route
    assert 'questions/import-job' in route
    assert 'timedelta(hours=2)' in route
    assert 'bank_question_import_task' in worker
    assert "status='pending_review'" in service
    assert 'validate_import_archive' in service
    assert 'Tải file lỗi Excel' in modal
    assert 'Kiểm tra dữ liệu' in modal and 'Xác nhận import' in modal


def test_v64_13_import_template_and_validation_are_strict():
    raw = build_import_template()
    wb = load_workbook(BytesIO(raw))
    ws = wb['questions']
    ws.append(['Câu hợp lệ?', 'A', 'B', 'C', 'D', 'A', 'impossible', '', '', '', ''])
    output = BytesIO()
    wb.save(output)
    parsed = parse_import_workbook(output.getvalue())
    assert parsed['total_rows'] == 1
    assert parsed['valid_count'] == 0
    assert parsed['error_count'] == 1
    assert any(item['code'] == 'INVALID_DIFFICULTY' for item in parsed['errors'])


def test_v64_13_release_preview_uses_release_snapshot_membership():
    route = text('backend/app/api/routes/question_bank_v2.py')
    schema = text('backend/app/schemas/question_bank.py')
    api = text('frontend/lib/api.ts')
    assert "@router.get('/releases/{release_id}/preview'" in route
    assert 'BankReleaseQuestion.bank_release_id == release.id' in route
    assert 'class BankReleasePreviewOut' in schema
    assert 'getBankReleasePreview' in api


def test_v64_13_bulk_actions_and_danger_confirmations():
    schema = text('backend/app/schemas/question_bank.py')
    service = text('backend/app/services/question_bank/generation_review.py')
    page = text('frontend/app/bank/_components/pages/ChapterWorkspacePage.tsx')
    assert 'apply_to_filtered' in schema
    assert 'total_filtered > 2000' in service
    assert "setConfirmation('bulk_reject')" in page
    assert "setConfirmation('release_create')" in page
    assert "setConfirmation('release_publish')" in page
    assert '<ConfirmDialog' in page


def test_v64_13_maintainability_tracks_new_modules():
    source = text('backend/app/services/maintainability_contract.py')
    for path in [
        'backend/app/services/question_bank/import_export.py',
        'frontend/hooks/useBankQuestionTableState.ts',
        'frontend/app/bank/_components/BankQuestionEnterpriseTable.tsx',
        'frontend/app/bank/_components/BankQuestionImportModal.tsx',
    ]:
        assert path in source
