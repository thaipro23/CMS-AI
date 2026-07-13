#!/usr/bin/env bash
set -euo pipefail

API_BASE_URL="${API_BASE_URL:-http://localhost:8000/api}"
OUTPUT_DIR="${OUTPUT_DIR:-./artifacts/uat-ux-acceptance}"
AUTH_HEADER="${AUTH_HEADER:-}"
mkdir -p "$OUTPUT_DIR"

curl_args=(-fsS)
if [[ -n "$AUTH_HEADER" ]]; then
  curl_args+=(-H "$AUTH_HEADER")
fi
curl "${curl_args[@]}" "$API_BASE_URL/health/uat-ux-acceptance" > "$OUTPUT_DIR/uat-ux-acceptance.json"
python - "$OUTPUT_DIR/uat-ux-acceptance.json" "$OUTPUT_DIR/UAT_UX_ACCEPTANCE_SUMMARY.md" <<'PY'
import json, sys
source, output = sys.argv[1:]
data = json.load(open(source, encoding='utf-8'))
lines = [
    '# UAT UX Acceptance Summary', '',
    f"- Version: `{data.get('version', 'unknown')}`",
    f"- Status: **{data.get('status', 'UNKNOWN')}**",
    f"- Passed: {data.get('passed_count', 0)}/{data.get('check_count', 0)}",
    f"- Blockers: {data.get('blocker_count', 0)}",
    f"- Warnings: {data.get('warning_count', 0)}", '',
    '## Browser UAT checklist',
]
for item in data.get('browser_uat_checklist') or []:
    lines.append(f'- [ ] {item}')
open(output, 'w', encoding='utf-8').write('\n'.join(lines) + '\n')
if data.get('status') == 'BLOCKED':
    raise SystemExit(2)
PY

echo "Wrote $OUTPUT_DIR/uat-ux-acceptance.json"
echo "Wrote $OUTPUT_DIR/UAT_UX_ACCEPTANCE_SUMMARY.md"
