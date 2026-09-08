from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]


def test_get_data_cms_posts_campus_code_contract():
    source = (ROOT / 'backend/app/services/ap_academic_sync.py').read_text(encoding='utf-8')
    start = source.index('    def get_division(')
    end = source.index('\n\n\n\nclass AcademicImportService', start)
    get_division = source[start:end]

    assert "'campus_code': _clean(campus)" in get_division
    assert "'campus': _clean(campus)" not in get_division
    assert "'term_name': _clean(term_name)" in get_division
    assert "'subject_code': _clean(subject_code).upper()" in get_division


def test_premises_remains_manual_and_has_no_api_refresh_button():
    layout = (ROOT / 'frontend/app/premises/layout.tsx').read_text(encoding='utf-8')
    page = (ROOT / 'frontend/app/premises/page.tsx').read_text(encoding='utf-8')

    assert 'Cập nhật cơ sở' not in layout
    assert 'getAcademicApSyncOptions' not in layout
    assert 'saveAcademicCampus' not in layout
    assert 'Thêm cơ sở thủ công' in page
    assert 'hệ thống không lấy cơ sở từ AP' in page


def test_ap_sync_campus_scope_is_authoritative_from_dash_premises():
    source = (ROOT / 'backend/app/services/ap_academic_sync.py').read_text(encoding='utf-8')

    resolve_start = source.index('    def _resolve_campuses(')
    resolve_end = source.index('    def _configured_subject_codes(', resolve_start)
    resolve = source[resolve_start:resolve_end]
    assert "configured = [item['value'] for item in self._campus_master_values(branch=branch)]" in resolve
    assert 'APAcademicClient().get_campuses' not in resolve

    options_start = source.index('    def get_ap_sync_options(')
    options_end = source.index('    def sync_from_ap(', options_start)
    options = source[options_start:options_end]
    assert 'campuses = self._campus_master_values(branch=normalized_branch)' in options
    assert 'APAcademicClient().get_campuses' not in options

    frontend = (ROOT / 'frontend/app/ap-sync/page.tsx').read_text(encoding='utf-8')
    assert 'Lấy từ danh mục cơ sở Dash CMS' in frontend
