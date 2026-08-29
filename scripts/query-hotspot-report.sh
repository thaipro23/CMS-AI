#!/usr/bin/env bash
set -Eeuo pipefail

API_BASE_URL="${API_BASE_URL:-https://api-ai.cms-test.poly.edu.vn/api}"
TOKEN="${TOKEN:-}"
EXPECTED_VERSION="${EXPECTED_VERSION:-25.9.16.7.2.64.16.5.7.2.18}"
MAX_ITEMS="${MAX_ITEMS:-200}"
OUT_DIR="${OUT_DIR:-/tmp/ai-query-hotspots-$(date +%Y%m%d-%H%M%S)}"
mkdir -p "$OUT_DIR"

if [[ -z "$TOKEN" ]]; then
  echo "TOKEN is required" >&2
  exit 2
fi

curl -fsS "$API_BASE_URL/health/query-hotspots?max_items=$MAX_ITEMS" \
  -H "Authorization: Bearer $TOKEN" \
  -H 'Accept: application/json' \
  -o "$OUT_DIR/query-hotspots.json"

python - <<'PY' "$OUT_DIR/query-hotspots.json" "$OUT_DIR/QUERY_HOTSPOT_SUMMARY.md" "$EXPECTED_VERSION"
import json, sys
src, dst, expected = sys.argv[1:]
data = json.load(open(src, encoding='utf-8'))
items = data.get('items') or []
with open(dst, 'w', encoding='utf-8') as fh:
    fh.write('# Query Hotspot Summary\n\n')
    fh.write(f"Status: **{data.get('status')}**\n\n")
    fh.write(f"Version: `{data.get('version')}` · Expected: `{expected}`\n\n")
    fh.write(f"Blockers: **{data.get('blocker_count', 0)}** · Warnings: **{data.get('warning_count', 0)}** · Info: **{data.get('info_count', 0)}**\n\n")
    fh.write('## Hotspots\n\n')
    if not items:
        fh.write('Không phát hiện hotspot theo static scan.\n')
    else:
        fh.write('| Severity | File | Line | Reason | Code |\n')
        fh.write('|---|---|---:|---|---|\n')
        for item in items[:100]:
            code = (item.get('code') or '').replace('|', '\\|')
            fh.write(f"| {item.get('severity')} | `{item.get('file')}` | {item.get('line')} | {item.get('reason')} | `{code}` |\n")
    fh.write('\n## Next actions\n\n')
    for action in data.get('next_actions') or []:
        fh.write(f'- {action}\n')
    fh.write('\n## Read-only guarantees\n\n')
    for item in data.get('read_only_guarantees') or []:
        fh.write(f'- {item}\n')
print(dst)
PY

echo "Query hotspot report written to $OUT_DIR"
