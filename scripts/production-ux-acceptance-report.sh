#!/usr/bin/env bash
set -Eeuo pipefail

ROOT_DIR="${ROOT_DIR:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
OUT_DIR="${OUT_DIR:-$ROOT_DIR/.runtime/production-ux-acceptance-$(date +%Y%m%d-%H%M%S)}"
EXPECTED_VERSION="${EXPECTED_VERSION:-25.9.16.7.2.64.16.5.1}"
mkdir -p "$OUT_DIR"

python - "$ROOT_DIR" "$EXPECTED_VERSION" "$OUT_DIR/production-ux-source-contract.json" <<'PY'
import json, sys
from pathlib import Path
root, expected, output = Path(sys.argv[1]), sys.argv[2], Path(sys.argv[3])

def read(path):
    return (root / path).read_text(encoding='utf-8')

checks = {
    'version': expected in read('backend/app/core/config.py') and expected in read('frontend/package.json'),
    'full_content_table_contract': 'data-column-contract="full-content"' in read('frontend/components/table/EnterpriseDataTable.tsx'),
    'natural_width_table': 'table-layout: auto !important' in read('frontend/styles/production-ux-browser-hotfix.css'),
    'no_automatic_column_hiding': 'responsiveHiddenColumns' not in read('frontend/components/table/EnterpriseDataTable.tsx'),
    'indeterminate_selection': '.indeterminate = somePageSelected' in read('frontend/components/table/EnterpriseDataTable.tsx'),
    'mobile_drawer_inert_fallback': "toggleAttribute('inert'" in read('frontend/components/layout/AppShell.tsx'),
    'safari_match_media_fallback': 'media.addListener(updateMobile)' in read('frontend/components/layout/AppShell.tsx'),
    'pagination_semantics': 'aria-current' in read('frontend/components/ui/PaginationControls.tsx'),
    'forced_colors': '@media (forced-colors: active)' in read('frontend/styles/production-ux-acceptance.css'),
    'reduced_motion': '@media (prefers-reduced-motion: reduce)' in read('frontend/styles/production-ux-acceptance.css'),
    'safe_area': 'safe-area-inset-bottom' in read('frontend/styles/production-ux-acceptance.css'),
    'no_bootstrap': 'bootstrap' not in read('frontend/package.json').lower(),
}
result = {
    'version': expected,
    'status': 'READY_FOR_BROWSER_UAT' if all(checks.values()) else 'BLOCKED',
    'passed': sum(checks.values()),
    'total': len(checks),
    'checks': checks,
    'browser_matrix': [
        'Chrome desktop: 1440x900 và 1366x768',
        'Edge desktop: 1366x768',
        'Safari iPhone: 390x844',
        'Chrome Android: 360x800',
        'iPad/Safari: 768x1024',
        'Bàn phím: skip link, sidebar, drawer, table, column menu và pagination',
        'Windows High Contrast / forced colors',
        'prefers-reduced-motion',
        'RBAC bằng tài khoản thật cho từng vai trò',
    ],
}
output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
if result['status'] == 'BLOCKED':
    raise SystemExit(2)
PY

python - "$OUT_DIR/production-ux-source-contract.json" "$OUT_DIR/PRODUCTION_UX_BROWSER_UAT.md" <<'PY'
import json, sys
data = json.load(open(sys.argv[1], encoding='utf-8'))
lines = [
    '# Production UX Browser UAT', '',
    f"- Version: `{data['version']}`",
    f"- Source contract: **{data['status']}**",
    f"- Static checks: {data['passed']}/{data['total']}", '',
    '## Browser matrix',
]
lines.extend(f'- [ ] {item}' for item in data['browser_matrix'])
lines += ['', '## Acceptance',
          '- [ ] Không có body horizontal scroll.',
          '- [ ] Bảng giữ đầy đủ nội dung; cột tự co giãn/xuống dòng và chỉ cuộn ngang trong container khi thực sự cần.',
          '- [ ] Sidebar/drawer không để focus lọt ra nền.',
          '- [ ] Escape đóng drawer và focus quay về nút mở.',
          '- [ ] Pagination và column menu dùng được hoàn toàn bằng bàn phím.',
          '- [ ] Không có raw API error hoặc diagnostics UI trong production.',
          '- [ ] Menu và action đúng phạm vi RBAC thực tế.']
open(sys.argv[2], 'w', encoding='utf-8').write('\n'.join(lines) + '\n')
PY

echo "Wrote $OUT_DIR/production-ux-source-contract.json"
echo "Wrote $OUT_DIR/PRODUCTION_UX_BROWSER_UAT.md"
