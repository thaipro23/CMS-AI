#!/usr/bin/env bash
set -euo pipefail

API_BASE_URL="${API_BASE_URL:-https://api-ai.cms-test.poly.edu.vn/api}"
TOKEN="${TOKEN:-}"
OUT_DIR="${OUT_DIR:-/tmp/ai-rollnumber-identity-migration-$(date +%Y%m%d-%H%M%S)}"
CLASS_ID="${CLASS_ID:-}"
TERM_ID="${TERM_ID:-}"
CAMPUS="${CAMPUS:-}"
BRANCH="${BRANCH:-poly}"
SUBJECT_ID="${SUBJECT_ID:-}"
STATUS_FILTER="${STATUS_FILTER:-all}"
PAGE_SIZE="${PAGE_SIZE:-500}"

mkdir -p "$OUT_DIR"

if [[ -z "$TOKEN" ]]; then
  echo "TOKEN is required" >&2
  exit 2
fi

query="status_filter=${STATUS_FILTER}&page_size=${PAGE_SIZE}"
[[ -n "$CLASS_ID" ]] && query+="&class_id=${CLASS_ID}"
[[ -n "$TERM_ID" ]] && query+="&term_id=${TERM_ID}"
[[ -n "$CAMPUS" ]] && query+="&campus=${CAMPUS}"
[[ -n "$BRANCH" ]] && query+="&branch=${BRANCH}"
[[ -n "$SUBJECT_ID" ]] && query+="&subject_id=${SUBJECT_ID}"

curl_json() {
  local url="$1"
  local out="$2"
  curl -fsS "$url" -H "Authorization: Bearer ${TOKEN}" -H 'Accept: application/json' -o "$out"
}

report_json="$OUT_DIR/rollnumber-identity-migration.json"
curl_json "${API_BASE_URL%/}/academic/identity/rollnumber-migration?${query}" "$report_json"

python3 - "$report_json" "$OUT_DIR/ROLLNUMBER_IDENTITY_MIGRATION_SUMMARY.md" <<'PY'
import json, sys
src, dst = sys.argv[1], sys.argv[2]
with open(src, 'r', encoding='utf-8') as f:
    data = json.load(f)
counts = data.get('counts') or {}
sev = data.get('severity_counts') or {}
lines = []
lines.append('# RollNumber Identity Migration Report')
lines.append('')
lines.append(f"Status: **{data.get('status')}**")
lines.append(f"Message: {data.get('message')}")
lines.append('')
lines.append('## Scope')
for k, v in (data.get('scope') or {}).items():
    lines.append(f'- {k}: {v}')
lines.append('')
lines.append('## Counts')
lines.append(f"- scanned: {data.get('scanned')}")
lines.append(f"- total matched rows: {data.get('total')}")
lines.append(f"- blockers: {sev.get('blocker', 0)}")
lines.append(f"- warnings: {sev.get('warning', 0)}")
lines.append(f"- info: {sev.get('info', 0)}")
for k in sorted(counts):
    lines.append(f"- {k}: {counts[k]}")
lines.append('')
lines.append('## Next actions')
for action in data.get('next_actions') or []:
    lines.append(f'- {action}')
lines.append('')
lines.append('## Sample rows')
for item in (data.get('items') or [])[:20]:
    lines.append(f"- {item.get('class_code')} | {item.get('student_code')} | {item.get('ap_username')} -> {item.get('canonical_username')} | status={item.get('status')} | openedx={item.get('openedx_username')}")
lines.append('')
lines.append('Read-only report: no mapping/user/snapshot mutation was performed.')
with open(dst, 'w', encoding='utf-8') as f:
    f.write('\n'.join(lines) + '\n')
PY

echo "RollNumber identity migration report exported to: $OUT_DIR"
echo "- $report_json"
echo "- $OUT_DIR/ROLLNUMBER_IDENTITY_MIGRATION_SUMMARY.md"
