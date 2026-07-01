#!/usr/bin/env bash
set -euo pipefail

API_BASE="${API_BASE:-http://localhost:8000/api}"
AUTH_HEADER="${AUTH_HEADER:-}"
CLASS_ID="${CLASS_ID:-}"
COURSE_ID="${COURSE_ID:-}"
CAMPUS="${CAMPUS:-}"
BRANCH="${BRANCH:-}"
SAMPLE_LIMIT="${SAMPLE_LIMIT:-5}"
FAIL_ON_WARNINGS="${FAIL_ON_WARNINGS:-false}"

curl_json() {
  local url="$1"
  if [[ -n "$AUTH_HEADER" ]]; then
    curl -fsS -H "$AUTH_HEADER" "$url"
  else
    curl -fsS "$url"
  fi
}

query="sample_limit=${SAMPLE_LIMIT}"
[[ -n "$CLASS_ID" ]] && query+="&class_id=$(python3 -c 'import urllib.parse,os; print(urllib.parse.quote(os.environ["CLASS_ID"]))')"
[[ -n "$COURSE_ID" ]] && query+="&course_id=$(python3 -c 'import urllib.parse,os; print(urllib.parse.quote(os.environ["COURSE_ID"]))')"
[[ -n "$CAMPUS" ]] && query+="&campus=$(python3 -c 'import urllib.parse,os; print(urllib.parse.quote(os.environ["CAMPUS"]))')"
[[ -n "$BRANCH" ]] && query+="&branch=$(python3 -c 'import urllib.parse,os; print(urllib.parse.quote(os.environ["BRANCH"]))')"

health_file="/tmp/analytics-health.json"
prod_file="/tmp/analytics-production-readiness.json"
pilot_file="/tmp/analytics-pilot-acceptance.json"

echo "[1/3] Checking analytics health..."
curl_json "${API_BASE%/}/health/analytics" > "$health_file" || curl_json "${API_BASE%/}/../health/analytics" > "$health_file"
cat "$health_file"
echo

echo "[2/3] Checking production readiness..."
curl_json "${API_BASE%/}/analytics/ops/production-readiness" > "$prod_file"
cat "$prod_file"
echo

echo "[3/3] Checking pilot acceptance..."
curl_json "${API_BASE%/}/analytics/ops/pilot-acceptance?${query}" > "$pilot_file"
cat "$pilot_file"
echo

python3 - <<'PY'
import json, os, sys
from pathlib import Path
pilot = json.loads(Path('/tmp/analytics-pilot-acceptance.json').read_text())
status = pilot.get('pilot_status')
ready = bool(pilot.get('ready_for_pilot'))
blockers = pilot.get('blocker_codes') or []
warnings = pilot.get('warning_codes') or []
print(f"Pilot status: {status}")
print(f"Ready for pilot: {ready}")
print(f"Blockers: {len(blockers)} {blockers}")
print(f"Warnings: {len(warnings)} {warnings}")
if not ready:
    print('FAIL: chưa đủ điều kiện pilot production. Xem next_actions trong JSON.')
    sys.exit(2)
if os.environ.get('FAIL_ON_WARNINGS', 'false').lower() == 'true' and warnings:
    print('FAIL: còn cảnh báo và FAIL_ON_WARNINGS=true.')
    sys.exit(3)
print('PASS: có thể pilot hẹp theo phạm vi đã chọn. Nhận định vẫn là tín hiệu mềm, cần giáo viên/quản lý xác minh.')
PY
