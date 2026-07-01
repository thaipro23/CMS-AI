#!/usr/bin/env bash
set -euo pipefail

API_BASE="${API_BASE:-http://localhost:8000/api}"
AUTH_HEADER="${AUTH_HEADER:-}"
CLASS_ID="${CLASS_ID:-}"
COURSE_ID="${COURSE_ID:-}"
FAIL_ON_BLOCKERS="${FAIL_ON_BLOCKERS:-true}"

curl_json() {
  local url="$1"
  if [[ -n "$AUTH_HEADER" ]]; then
    curl -fsS -H "$AUTH_HEADER" "$url"
  else
    curl -fsS "$url"
  fi
}

query="limit=20"
[[ -n "$CLASS_ID" ]] && query+="&class_id=$(python3 -c 'import urllib.parse,os; print(urllib.parse.quote(os.environ["CLASS_ID"]))')"
[[ -n "$COURSE_ID" ]] && query+="&course_id=$(python3 -c 'import urllib.parse,os; print(urllib.parse.quote(os.environ["COURSE_ID"]))')"

rollout_file="/tmp/analytics-rollout-control.json"
monitoring_file="/tmp/analytics-monitoring.json"
production_file="/tmp/analytics-production-readiness.json"

echo "[1/3] Rollout control"
curl_json "${API_BASE%/}/analytics/ops/rollout-control?${query}" > "$rollout_file"
cat "$rollout_file"
echo

echo "[2/3] Analytics monitoring"
curl_json "${API_BASE%/}/analytics/ops/monitoring${query:+?$query}" > "$monitoring_file"
cat "$monitoring_file"
echo

echo "[3/3] Production readiness"
curl_json "${API_BASE%/}/analytics/ops/production-readiness" > "$production_file"
cat "$production_file"
echo

python3 - <<'PY'
import json, os, sys
from pathlib import Path
rollout = json.loads(Path('/tmp/analytics-rollout-control.json').read_text())
monitoring = json.loads(Path('/tmp/analytics-monitoring.json').read_text())
production = json.loads(Path('/tmp/analytics-production-readiness.json').read_text())
print('Rollout:', rollout.get('rollout_status'), 'mode=', rollout.get('mode'), 'in_scope=', (rollout.get('counters') or {}).get('in_rollout'))
print('Monitoring:', monitoring.get('monitoring_status'), 'stuck_jobs=', monitoring.get('stuck_analytics_job_count'), 'stale_snapshots=', monitoring.get('stale_snapshot_count'))
print('Production:', production.get('readiness'), 'blockers=', production.get('blocker_count'), 'warnings=', production.get('warning_count'))
if os.environ.get('FAIL_ON_BLOCKERS', 'true').lower() == 'true':
    if rollout.get('rollout_status') == 'DISABLED':
        print('FAIL: rollout đang tắt.')
        sys.exit(2)
    if monitoring.get('monitoring_status') == 'BLOCKED':
        print('FAIL: monitoring có blocker.')
        sys.exit(3)
    if int(production.get('blocker_count') or 0) > 0:
        print('FAIL: production readiness còn blocker.')
        sys.exit(4)
print('PASS: rollout/monitoring không có blocker bắt buộc. Nhận định học online vẫn là tín hiệu mềm, không phải kết luận vi phạm.')
PY
