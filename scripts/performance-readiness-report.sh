#!/usr/bin/env bash
set -Eeuo pipefail

API_BASE_URL="${API_BASE_URL:-https://api-ai.cms-test.poly.edu.vn/api}"
TOKEN="${TOKEN:-}"
EXPECTED_VERSION="${EXPECTED_VERSION:-25.9.16.7.2.64.16.5.7.1.1}"
OUT_DIR="${OUT_DIR:-/tmp/ai-performance-readiness-$(date +%Y%m%d-%H%M%S)}"
mkdir -p "$OUT_DIR"

if [[ -z "$TOKEN" ]]; then
  echo "TOKEN is required" >&2
  exit 2
fi

curl_json() {
  local path="$1" out="$2"
  curl -fsS "$API_BASE_URL$path" \
    -H "Authorization: Bearer $TOKEN" \
    -H 'Accept: application/json' \
    -o "$out"
}

curl_json '/health/performance-readiness' "$OUT_DIR/performance-readiness.json"

python - <<'PY' "$OUT_DIR/performance-readiness.json" "$OUT_DIR/PERFORMANCE_READINESS_SUMMARY.md"
import json, sys
src, dst = sys.argv[1:]
data = json.load(open(src, encoding='utf-8'))
checks = data.get('checks') or []
sections = data.get('sections') or []
with open(dst, 'w', encoding='utf-8') as fh:
    fh.write('# Performance Readiness Summary\n\n')
    fh.write(f"Status: **{data.get('status')}**\n\n")
    fh.write(f"Version: `{data.get('version')}` · Expected: `{__import__('os').environ.get('EXPECTED_VERSION', '')}`\n\n")
    fh.write(f"Blockers: **{data.get('blocker_count', 0)}** · Warnings: **{data.get('warning_count', 0)}**\n\n")
    fh.write('## Sections\n\n')
    fh.write('| Section | Status | Blockers | Warnings | Checks |\n')
    fh.write('|---|---|---:|---:|---:|\n')
    for item in sections:
        fh.write(f"| {item.get('title') or item.get('key')} | {item.get('status')} | {item.get('blocker_count', 0)} | {item.get('warning_count', 0)} | {item.get('check_count', 0)} |\n")
    fh.write('\n## Issues\n\n')
    issues = [c for c in checks if c.get('severity') in {'BLOCKER', 'WARNING'}]
    if not issues:
        fh.write('Không có blocker/cảnh báo hiệu năng.\n')
    else:
        fh.write('| Severity | Code | Message | Action |\n')
        fh.write('|---|---|---|---|\n')
        for item in issues:
            fh.write(f"| {item.get('severity')} | `{item.get('code')}` | {item.get('message') or ''} | {item.get('action') or ''} |\n")
    fh.write('\n## Read-only guarantees\n\n')
    for item in data.get('read_only_guarantees') or []:
        fh.write(f'- {item}\n')
print(dst)
PY

echo "Performance readiness report written to $OUT_DIR"
