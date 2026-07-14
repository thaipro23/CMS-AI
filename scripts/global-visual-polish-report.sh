#!/usr/bin/env bash
set -Eeuo pipefail

ROOT_DIR="${ROOT_DIR:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
OUT_DIR="${OUT_DIR:-$ROOT_DIR/.runtime/global-visual-polish-$(date +%Y%m%d-%H%M%S)}"
EXPECTED_VERSION="${EXPECTED_VERSION:-25.9.16.7.2.64.16.5.3}"
mkdir -p "$OUT_DIR"

python - "$ROOT_DIR" "$EXPECTED_VERSION" "$OUT_DIR/global-visual-polish.json" <<'PY'
import json, sys
from pathlib import Path
root, expected, output = Path(sys.argv[1]), sys.argv[2], Path(sys.argv[3])

def read(path):
    return (root / path).read_text(encoding='utf-8')

layout = read('frontend/app/layout.tsx')
css = read('frontend/styles/global-visual-polish.css')
visual = read('frontend/components/ui/VisualIcon.tsx')
page_header = read('frontend/components/layout/PageHeader.tsx')
app_shell = read('frontend/components/layout/AppShell.tsx')
table = read('frontend/components/table/EnterpriseDataTable.tsx')
training = read('frontend/components/training/TrainingWorkspace.tsx')
operations = read('frontend/components/operations/OperationsWorkspace.tsx')
notices = read('frontend/components/ui/InlineNotice.tsx') + read('frontend/components/ui/ActionMessage.tsx')
package = read('frontend/package.json').lower()
active_pages = [p for p in (root / 'frontend/app').rglob('page.tsx') if 'ops/readiness' not in p.as_posix()]
redirect_pages = [p for p in active_pages if 'redirect(' in p.read_text(encoding='utf-8')]
checks = {
    'version': expected in read('backend/app/core/config.py') and expected in read('frontend/package.json'),
    'visual_css_precedes_integrity_layer': "import '../styles/global-visual-polish.css'" in layout and layout.rfind('layout-integrity.css') > layout.rfind('global-visual-polish.css') > layout.rfind('production-ux-browser-hotfix.css'),
    'topbar_page_icon': '<VisualIcon' in app_shell and 'enterprise-topbar-page-icon' in app_shell and '<h1>{pageChrome?.title || pageLabel(pathname)}</h1>' in app_shell and 'enterprise-page-header-copy' not in page_header,
    'semantic_icon_resolver': 'inferVisualMeta' in visual and "words: ['sinh viên'" in visual,
    'kpi_icons': '<VisualIcon' in training and '<VisualIcon' in operations,
    'notice_icons': notices.count('<VisualIcon') >= 2,
    'table_header_icon': 'enterprise-table-summary-icon' in table and '<VisualIcon' in table,
    'full_content_table': 'data-column-contract="full-content"' in table and 'responsiveHiddenColumns' not in table,
    'rounded_visual_cards': '--visual-card-radius' in css and '.visual-section-card' in css,
    'all_page_global_coverage': len(active_pages) >= 25 and "global-visual-polish.css" in layout,
    'no_bootstrap_or_jquery': 'bootstrap' not in package and 'jquery' not in package,
    'sidebar_dark_workspace_light': '--sidebar-bg' in read('frontend/styles/enterprise-visual-foundation.css') and "d.dataset.theme='light'" in layout,
}
result = {
    'version': expected,
    'status': 'READY' if all(checks.values()) else 'BLOCKED',
    'passed': sum(checks.values()),
    'total': len(checks),
    'checks': checks,
    'active_page_files': len(active_pages),
    'redirect_page_files': len(redirect_pages),
    'visual_contract': [
        'Sidebar tối; topbar và workspace sáng.',
        'Topbar page title, KPI, section, notice, empty state và table summary có SVG icon.',
        'Card bo tròn nhẹ, border nhạt, shadow thấp và nền semantic.',
        'Bảng giữ đầy đủ cột mặc định, tự co giãn/xuống dòng và chỉ cuộn trong container.',
        'Không thêm Bootstrap, React-Bootstrap, jQuery hoặc Metronic.',
    ],
}
output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
if result['status'] != 'READY':
    raise SystemExit(2)
PY

echo "Wrote $OUT_DIR/global-visual-polish.json"
