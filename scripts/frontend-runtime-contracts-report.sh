#!/usr/bin/env bash
set -Eeuo pipefail

ROOT_DIR="${ROOT_DIR:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
OUT_DIR="${1:-${OUT_DIR:-$ROOT_DIR/.runtime/frontend-runtime-contracts}}"
EXPECTED_VERSION="${EXPECTED_VERSION:-25.9.16.7.2.64.16.5.7.2.2}"
mkdir -p "$OUT_DIR"

python - "$ROOT_DIR" "$OUT_DIR" "$EXPECTED_VERSION" <<'PY'
from __future__ import annotations
import json
import re
import sys
from pathlib import Path

root = Path(sys.argv[1])
out = Path(sys.argv[2])
version = sys.argv[3]

def read(path: str) -> str:
    return (root / path).read_text(encoding='utf-8')

def check(code: str, ok: bool, message: str, severity: str = 'BLOCKER'):
    return {'code': code, 'ok': bool(ok), 'severity': 'INFO' if ok else severity, 'message': message}

dialog = read('frontend/components/ui/AccessibleDialog.tsx')
feedback = read('frontend/components/ui/FeedbackProvider.tsx')
layout = read('frontend/app/layout.tsx')
table = read('frontend/components/table/EnterpriseDataTable.tsx')
pagination = read('frontend/components/ui/PaginationControls.tsx')
frontend_sources = '\n'.join(path.read_text(encoding='utf-8') for path in (root / 'frontend').rglob('*.tsx') if 'node_modules' not in path.parts and '.next' not in path.parts)
raw_dialogs = []
for path in (root / 'frontend').rglob('*.tsx'):
    if 'node_modules' in path.parts or '.next' in path.parts or path.name == 'AccessibleDialog.tsx':
        continue
    source = path.read_text(encoding='utf-8')
    if 'role="dialog"' in source or 'aria-modal="true"' in source or 'modal-backdrop' in source or 'bank-popup-backdrop' in source:
        raw_dialogs.append(str(path.relative_to(root)))
route_files = ['frontend/app/loading.tsx', 'frontend/app/error.tsx', 'frontend/app/not-found.tsx', 'frontend/app/global-error.tsx']
checks = [
    check('VERSION_SYNC', version in read('frontend/package.json') and version in read('backend/app/core/config.py'), 'Runtime versions are synchronized.'),
    check('SHARED_ACCESSIBLE_DIALOG', all(token in dialog for token in ['dialogStack', 'FOCUSABLE_SELECTOR', "event.key === 'Escape'", "event.key !== 'Tab'", 'previousActive', 'lockBodyScroll()', 'unlockBodyScroll()']), 'Shared dialog traps focus, closes with Escape, restores focus and locks body scroll.'),
    check('NESTED_DIALOG_STACK', 'dialogStack.push(token)' in dialog and 'dialogStack.splice(index, 1)' in dialog and 'isTopmost' in dialog, 'Nested dialogs are coordinated through a topmost stack.'),
    check('DIALOG_LABEL_CONTRACT', 'aria-labelledby={titleId}' in dialog and 'aria-describedby={description ? descriptionId : undefined}' in dialog, 'Dialogs bind accessible title and optional description.'),
    check('NO_RAW_DIALOG_IMPLEMENTATIONS', not raw_dialogs, f'All active dialogs use the shared primitive. Remaining: {raw_dialogs}'),
    check('NO_NATIVE_ALERT_CONFIRM', not re.search(r'\bwindow\.(?:alert|confirm)\s*\(|(?<![\w.])(?:alert|confirm)\s*\(', frontend_sources), 'Frontend does not use native alert/confirm.'),
    check('FEEDBACK_PROVIDER', 'FeedbackProvider' in layout and 'confirmAction' in feedback and 'feedback-toast-region' in feedback, 'Toast and confirmation feedback is centralized.'),
    check('ROUTE_STATE_FILES', all((root / path).exists() for path in route_files), 'App Router has loading, error, global-error and not-found boundaries.'),
    check('TABLE_DEFAULT_VISIBLE', "column.defaultVisible !== false" in table and 'Mặc định' in table, 'Enterprise table executes defaultVisible and can reset defaults.'),
    check('TABLE_TRUNCATE_LINES', 'truncate-lines-${layout.column.truncateLines}' in table and 'truncateLines?: 1 | 2 | 3' in table, 'Enterprise table executes truncateLines.'),
    check('TABLE_SORT_CONTRACT', 'onSortChange?:' in table and 'aria-sort=' in table and 'enterprise-sort-button' in table, 'Enterprise table exposes an accessible server-side sort contract.'),
    check('PAGE_SIZE_TEN', '<option value={10}>10/trang</option>' in pagination, 'Pagination supports the 10-row option consistently.'),
    check('RUNTIME_CSS_LAST', "import '../styles/frontend-runtime-contracts.css'" in layout and layout.rfind('frontend-runtime-contracts.css') > layout.rfind('layout-integrity.css'), 'Runtime contracts CSS loads after legacy layers.'),
]
blockers = [item for item in checks if not item['ok'] and item['severity'] == 'BLOCKER']
warnings = [item for item in checks if not item['ok'] and item['severity'] == 'WARNING']
payload = {
    'version': version,
    'report_type': 'frontend_runtime_contracts',
    'status': 'READY' if not blockers and not warnings else ('BLOCKED' if blockers else 'READY_WITH_WARNINGS'),
    'passed': sum(1 for item in checks if item['ok']),
    'blocker_count': len(blockers),
    'warning_count': len(warnings),
    'raw_dialog_files': raw_dialogs,
    'checks': checks,
}
(out / 'frontend-runtime-contracts.json').write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding='utf-8')
print(json.dumps(payload, ensure_ascii=False, indent=2))
raise SystemExit(1 if blockers else 0)
PY
