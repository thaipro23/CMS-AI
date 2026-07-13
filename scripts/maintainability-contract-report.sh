#!/usr/bin/env bash
set -Eeuo pipefail

API_BASE_URL="${API_BASE_URL:-https://api-ai.cms-test.poly.edu.vn/api}"
TOKEN="${TOKEN:-}"
EXPECTED_VERSION="${EXPECTED_VERSION:-25.9.16.7.2.64.12}"
OUT_DIR="${OUT_DIR:-/tmp/ai-maintainability-contract-$(date +%Y%m%d-%H%M%S)}"
mkdir -p "$OUT_DIR"

if [[ -z "$TOKEN" ]]; then
  echo "TOKEN is required" >&2
  exit 2
fi

curl -fsS "$API_BASE_URL/health/maintainability-contract" \
  -H "Authorization: Bearer $TOKEN" \
  -H 'Accept: application/json' \
  -o "$OUT_DIR/maintainability-contract.json"

python - <<'PY' "$OUT_DIR/maintainability-contract.json" "$OUT_DIR/MAINTAINABILITY_CONTRACT_SUMMARY.md" "$EXPECTED_VERSION"
import json, sys
src, dst, expected = sys.argv[1:]
data = json.load(open(src, encoding='utf-8'))
with open(dst, 'w', encoding='utf-8') as fh:
    fh.write('# Maintainability Contract Summary\n\n')
    fh.write(f"Status: **{data.get('status')}**\n\n")
    fh.write(f"Version: `{data.get('version')}` · Expected: `{expected}`\n\n")
    fh.write(f"Blockers: **{data.get('blocker_count', 0)}** · Warnings: **{data.get('warning_count', 0)}**\n\n")
    fh.write(f"Summary: {data.get('summary_label') or ''}\n\n")
    fh.write('## Contract Modules\n\n')
    fh.write('| Module | Exists |\n|---|---|\n')
    for item in data.get('contract_modules') or []:
        fh.write(f"| `{item.get('path')}` | {item.get('exists')} |\n")
    fh.write('\n## Large Files\n\n')
    fh.write('| Severity | File | Lines | Threshold | Reason |\n|---|---|---:|---:|---|\n')
    for item in data.get('file_metrics') or []:
        fh.write(f"| {item.get('severity')} | `{item.get('path')}` | {item.get('lines')} | {item.get('threshold')} | {item.get('reason')} |\n")
    fh.write('\n## Next Actions\n\n')
    for action in data.get('next_actions') or []:
        fh.write(f'- {action}\n')
    fh.write('\n## Read-only Guarantees\n\n')
    for item in data.get('read_only_guarantees') or []:
        fh.write(f'- {item}\n')
print(dst)
PY

echo "Maintainability contract report written to $OUT_DIR"
