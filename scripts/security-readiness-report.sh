#!/usr/bin/env bash
set -Eeuo pipefail

API_BASE_URL="${API_BASE_URL:-https://api-ai.cms-test.poly.edu.vn/api}"
TOKEN="${TOKEN:-}"
EXPECTED_VERSION="${EXPECTED_VERSION:-25.9.16.7.2.64.16.5.7.1.1}"
OUT_DIR="${OUT_DIR:-/tmp/ai-security-readiness-$(date +%Y%m%d-%H%M%S)}"
mkdir -p "$OUT_DIR"

if [[ -z "$TOKEN" ]]; then
  echo "TOKEN is required" >&2
  exit 2
fi

curl -fsS "$API_BASE_URL/health/security-readiness" \
  -H "Authorization: Bearer $TOKEN" \
  -H 'Accept: application/json' \
  -o "$OUT_DIR/security-readiness.json"

python - <<'PY' "$OUT_DIR/security-readiness.json" "$OUT_DIR/SECURITY_READINESS_SUMMARY.md"
import json, os, sys
src, dst = sys.argv[1:]
data = json.load(open(src, encoding='utf-8'))
checks = data.get('checks') or []
sections = data.get('sections') or []
issues = [c for c in checks if c.get('severity') in {'BLOCKER', 'WARNING'} and not c.get('ok')]
with open(dst, 'w', encoding='utf-8') as fh:
    fh.write('# Security Readiness Summary\n\n')
    fh.write(f"Status: **{data.get('status')}**\n\n")
    fh.write(f"Version: `{data.get('version')}` · Expected: `{os.environ.get('EXPECTED_VERSION', '')}`\n\n")
    fh.write(f"Environment: `{data.get('app_env')}`\n\n")
    fh.write(f"Blockers: **{data.get('blocker_count', 0)}** · Warnings: **{data.get('warning_count', 0)}**\n\n")
    primary = data.get('primary_blocker') or {}
    if primary:
        fh.write(f"Primary blocker: `{primary.get('code')}` — {primary.get('message')}\n\n")
    fh.write('## Sections\n\n')
    fh.write('| Section | Status | Blockers | Warnings | Checks |\n')
    fh.write('|---|---|---:|---:|---:|\n')
    for item in sections:
        fh.write(f"| {item.get('title') or item.get('key')} | {item.get('status')} | {item.get('blocker_count', 0)} | {item.get('warning_count', 0)} | {item.get('check_count', 0)} |\n")
    fh.write('\n## Issues\n\n')
    if not issues:
        fh.write('Không có blocker/cảnh báo security.\n')
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

echo "Security readiness report written to $OUT_DIR"
