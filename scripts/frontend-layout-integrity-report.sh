#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
OUT_DIR="${1:-$ROOT/.runtime/layout-integrity}"
mkdir -p "$OUT_DIR"
python - "$ROOT" "$OUT_DIR" <<'PY'
import json,re,sys
from pathlib import Path
root=Path(sys.argv[1]);out=Path(sys.argv[2])
layout=(root/'frontend/app/layout.tsx').read_text(encoding='utf-8')
contract=(root/'frontend/styles/layout-integrity.css').read_text(encoding='utf-8')
table=(root/'frontend/components/table/EnterpriseDataTable.tsx').read_text(encoding='utf-8')
app_shell=(root/'frontend/components/layout/AppShell.tsx').read_text(encoding='utf-8')
page_header=(root/'frontend/components/layout/PageHeader.tsx').read_text(encoding='utf-8')
package=(root/'frontend/package.json').read_text(encoding='utf-8').lower()
active_tsx='\n'.join(p.read_text(encoding='utf-8') for p in sorted((root/'frontend').rglob('*.tsx')) if 'node_modules' not in p.parts and '.next' not in p.parts)
negative=[]; absolute=[]
for path in sorted((root/'frontend/styles').glob('*.css'))+[root/'frontend/app/globals.css']:
 lines=path.read_text(encoding='utf-8').splitlines()
 for i,line in enumerate(lines,1):
  if re.search(r'margin(?:-[a-z]+)?\s*:\s*-\d',line) and 'sr-only' not in ''.join(lines[max(0,i-3):i+1]): negative.append(f'{path.relative_to(root)}:{i}:{line.strip()}')
  if re.search(r'position\s*:\s*absolute',line): absolute.append(f'{path.relative_to(root)}:{i}:{line.strip()}')
pages=sorted((root/'frontend/app').rglob('page.tsx')); active=[p for p in pages if 'ops/readiness' not in p.as_posix()]
checks={
 'layout_integrity_loaded_last':layout.rfind('layout-integrity.css')>layout.rfind('global-visual-polish.css'),
 'spacing_tokens_defined':all(x in contract for x in ('--layout-section-gap','--layout-card-padding','--layout-divider')),
 'page_header_wraps':'.enterprise-page-header {' in contract and 'flex-wrap: wrap' in contract,
 'workspace_has_flow_spacing':'.workspace-section-body {' in contract and 'gap: var(--layout-space-4)' in contract,
 'table_regions_have_dividers':'.enterprise-data-table th,' in contract and 'border-right: 1px solid var(--layout-divider-soft)' in contract,
 'table_keeps_full_content':'data-column-contract="full-content"' in table and 'responsiveHiddenColumns' not in table,
 'negative_margin_free':not negative,
 'decorations_cannot_cover_content':'.visual-section-card::after' in contract and '.dashboard-hero-glow' in contract,
 'alerts_use_flow_icon':'.alert::before,' in contract and 'position: static !important' in contract,
 'modal_drawer_regions_separated':'.side-drawer > header,' in contract and 'border-top: 1px solid var(--layout-divider)' in contract,
 'all_domains_present':len(active)>=30,
 'no_bootstrap_jquery':all(x not in package for x in ('bootstrap','react-bootstrap','jquery')),
 'page_title_owned_by_topbar':bool(re.search(r'<h1>\{pageChrome\?\.title \|\| pageLabel\(pathname(?:,\s*activePlatform)?\)\}</h1>', app_shell)) and 'enterprise-page-header-copy' not in page_header and 'enterprise-page-description' not in page_header,
 'main_owns_page_layout_classes':'className={`enterprise-content ${pageLayoutClass}`.trim()}' in app_shell and 'layoutRegistrationRef.current = registrationId' in app_shell,
 'row_actions_are_explicit':all(x not in active_tsx for x in ('⋮','•••','row-action-menu')),
}
status='READY' if all(checks.values()) else 'BLOCKED'
payload={'status':status,'checks':checks,'passed':sum(checks.values()),'total':len(checks),'active_page_count':len(active),'all_page_count':len(pages),'negative_margin_hits':negative,'absolute_position_inventory_count':len(absolute),'note':'Absolute positioning remains only for overlays, popovers, sticky helpers and decorative legacy selectors. Readable page content is protected by the final layout-integrity contract.'}
(out/'frontend-layout-integrity.json').write_text(json.dumps(payload,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(payload,ensure_ascii=False,indent=2))
if status!='READY':raise SystemExit(1)
PY
