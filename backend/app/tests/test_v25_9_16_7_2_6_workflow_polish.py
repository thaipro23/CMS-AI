from pathlib import Path


def root() -> Path:
    return Path(__file__).resolve().parents[3]


def test_semester_edit_picks_exact_block_rows():
    page = (root() / 'frontend' / 'app' / 'semesters' / 'page.tsx').read_text(encoding='utf-8')
    assert 'function pickBlocksForTermForm' in page
    assert 'blockNoHint(block)' in page
    assert 'const sourceBlocks = pickBlocksForTermForm(full.blocks || [])' in page
    assert 'Number(block.sort_order || 0) === wanted' in page


def test_empty_chapter_cleanup_detaches_runtime_bank_version_metadata():
    service = (root() / 'backend' / 'app' / 'services' / 'question_bank_service.py').read_text(encoding='utf-8')
    assert "real_content_keys = {'materials', 'chunks', 'concepts', 'families', 'questions', 'releases'}" in service
    assert 'BankVersionDiff.from_bank_version_id == version.id' in service
    assert 'QuestionBankVersion.based_on_version_id == version.id' in service
    assert 'Không thể xóa {entity_label} vì vẫn còn dữ liệu liên kết' in service
    assert 'bank version: 1' not in service


def test_bank_status_wording_and_visible_borders_are_polished():
    shared = (root() / 'frontend' / 'app' / 'bank' / '_components' / 'shared.tsx').read_text(encoding='utf-8')
    css = (root() / 'frontend' / 'app' / 'globals.css').read_text(encoding='utf-8')
    assert 'Chưa làm' not in shared
    assert 'Chưa làm hết' not in shared
    assert 'Đã public thư viện' not in shared
    assert "ready: 'Sẵn sàng chốt'" in shared
    assert "empty: 'Chưa có dữ liệu'" in shared
    assert "published: 'Đã đưa lên CMS'" in shared
    assert "value === 'ready'" in shared and 'status-ready' in shared
    assert 'v25.9.16.7.2.6 — Bank status wording + visible card borders' in css
    assert '.entity-card.bank-status-card.status-ready' in css


def test_jobs_and_audit_are_separated_and_ap_jobs_visible_by_default():
    jobs = (root() / 'frontend' / 'app' / 'jobs' / 'page.tsx').read_text(encoding='utf-8')
    audit = (root() / 'frontend' / 'app' / 'audit' / 'page.tsx').read_text(encoding='utf-8')
    assert "const [status, setStatus] = useState('all')" in jobs
    assert 'Jobs / Việc xử lý' in jobs
    assert 'AP sync gần đây' in jobs
    assert '<option value="all">Tất cả</option><option value="active">Đang chạy</option>' in jobs
    assert 'Audit / Nhật ký hoạt động' in audit
    assert "'academic.sync.ap.run': 'Chạy đồng bộ AP'" in audit
    assert ".replace('academic.', 'Đào tạo · ')" in audit


def test_stable_vertical_scrollbar_guard_present():
    css = (root() / 'frontend' / 'app' / 'globals.css').read_text(encoding='utf-8')
    assert 'html { overflow-y: scroll; scrollbar-gutter: stable; }' in css
    assert 'body { min-height: 100dvh; }' in css
