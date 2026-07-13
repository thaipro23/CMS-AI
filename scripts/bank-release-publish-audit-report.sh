#!/usr/bin/env bash
set -Eeuo pipefail

API_BASE_URL="${API_BASE_URL:-https://api-ai.cms-test.poly.edu.vn/api}"
TOKEN="${TOKEN:-}"
RELEASE_ID="${RELEASE_ID:-}"
OUT_DIR="${OUT_DIR:-/tmp/ai-bank-release-publish-audit-$(date +%Y%m%d-%H%M%S)}"

mkdir -p "$OUT_DIR"

if [[ -z "$TOKEN" ]]; then
  echo "ERROR: TOKEN is required" >&2
  exit 2
fi
if [[ -z "$RELEASE_ID" ]]; then
  echo "ERROR: RELEASE_ID is required" >&2
  exit 2
fi

curl_json() {
  local path="$1"
  local out="$2"
  curl -fsS "$API_BASE_URL$path" \
    -H "Authorization: Bearer $TOKEN" \
    -H 'Accept: application/json' \
    -o "$out"
}

AUDIT_JSON="$OUT_DIR/bank-release-publish-audit.json"
curl_json "/question-bank-v2/releases/$RELEASE_ID/publish-audit" "$AUDIT_JSON"

python - "$AUDIT_JSON" "$OUT_DIR/BANK_RELEASE_PUBLISH_AUDIT_SUMMARY.md" <<'PY'
import json
import sys
from pathlib import Path
src = Path(sys.argv[1])
out = Path(sys.argv[2])
data = json.loads(src.read_text())
counts = data.get('counts') or {}
blockers = data.get('blockers') or []
warnings = data.get('warnings') or []
next_actions = data.get('next_actions') or []
lines = [
    '# Bank Release Publish Audit',
    '',
    f"- Release: `{data.get('release_code') or data.get('release_id')}`",
    f"- Status: `{data.get('audit_status')}`",
    f"- Message: {data.get('message') or ''}",
    f"- Read-only: `{data.get('read_only')}`",
    f"- Mutation performed: `{data.get('mutation_performed')}`",
    '',
    '## Counts',
]
for key in sorted(counts):
    lines.append(f'- {key}: {counts[key]}')
lines.extend(['', '## Blockers'])
if blockers:
    for item in blockers:
        lines.append(f"- `{item.get('code')}`: {item.get('message')}")
else:
    lines.append('- None')
lines.extend(['', '## Warnings'])
if warnings:
    for item in warnings:
        lines.append(f"- `{item.get('code')}`: {item.get('message')}")
else:
    lines.append('- None')
lines.extend(['', '## Next actions'])
if next_actions:
    for item in next_actions:
        lines.append(f'- {item}')
else:
    lines.append('- None')
out.write_text('\n'.join(lines) + '\n')
print(out)
PY

echo "Bank release publish audit exported to: $OUT_DIR"
