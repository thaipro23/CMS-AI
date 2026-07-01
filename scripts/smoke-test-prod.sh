#!/usr/bin/env bash
set -euo pipefail

COMPOSE_FILE="${COMPOSE_FILE:-docker-compose.prod.yml}"
ENV_FILE="${ENV_FILE:-.env.production}"
PROJECT_DIR="${PROJECT_DIR:-$(pwd)}"
API_BASE_URL="${API_BASE_URL:-}"
AUTH_HEADER="${AUTH_HEADER:-}"
CLASS_ID="${CLASS_ID:-}"
COURSE_ID="${COURSE_ID:-}"
TUTOR_COURSE_ID="${TUTOR_COURSE_ID:-$COURSE_ID}"
EXPECTED_CONNECTOR_VERSION="${EXPECTED_CONNECTOR_VERSION:-25.9.16.5.98}"

cd "$PROJECT_DIR"

echo "== AI Server smoke test pack =="

echo "\n[1/10] container status"
docker compose -f "$COMPOSE_FILE" --env-file "$ENV_FILE" ps

echo "\n[2/10] backend health/db/config"
docker compose -f "$COMPOSE_FILE" --env-file "$ENV_FILE" exec -T backend python - <<'PY'
import json, urllib.request
for path in ['/api/health', '/api/health/build', '/api/health/db', '/api/health/openedx-connector/config', '/api/health/analytics']:
    with urllib.request.urlopen('http://127.0.0.1:8000' + path, timeout=10) as r:
        data = json.loads(r.read().decode('utf-8'))
    print(path, json.dumps(data, ensure_ascii=False, sort_keys=True))
PY


echo "\n[3/10] analytics ops read-only status"
docker compose -f "$COMPOSE_FILE" --env-file "$ENV_FILE" exec -T backend python - <<'PY'
import json, urllib.request
with urllib.request.urlopen('http://127.0.0.1:8000/api/health/analytics', timeout=10) as r:
    data = json.loads(r.read().decode('utf-8'))
print(json.dumps(data, ensure_ascii=False, sort_keys=True))
assert data.get('safe_policy') == 'signals_only_not_violation'
PY

echo "\n[4/10] frontend container can render root"
docker compose -f "$COMPOSE_FILE" --env-file "$ENV_FILE" exec -T frontend sh -lc "node -e \"fetch('http://127.0.0.1:3000').then(r=>{console.log('frontend_status='+r.status); if(r.status>=500) process.exit(1)}).catch(e=>{console.error(e); process.exit(1)})\""

echo "\n[5/10] worker import check"
docker compose -f "$COMPOSE_FILE" --env-file "$ENV_FILE" exec -T worker python - <<'PY'
from app.worker import celery_app
print('celery_app=', celery_app.main)
PY

echo "\n[6/10] Open edX connector active version"
if command -v tutor >/dev/null 2>&1; then
  tutor local run lms python - <<PY
import importlib, sys
m = importlib.import_module('openedx_ai_connector.student_insight')
version = getattr(m, 'CONNECTOR_VERSION', None)
contract = getattr(m, 'CONNECTOR_CONTRACT_VERSION', None)
print('CONNECTOR_VERSION=', version)
print('CONNECTOR_CONTRACT_VERSION=', contract)
if str(version) != '${EXPECTED_CONNECTOR_VERSION}':
    print('EXPECTED_CONNECTOR_VERSION=${EXPECTED_CONNECTOR_VERSION}', file=sys.stderr)
    sys.exit(4)
PY
else
  echo "tutor_not_found=skip"
fi

echo "\n[7/10] optional API class detail"
if [[ -n "$API_BASE_URL" && -n "$AUTH_HEADER" && -n "$CLASS_ID" ]]; then
  curl -fsS -H "$AUTH_HEADER" "$API_BASE_URL/api/academic/classes/$CLASS_ID/students?page=1&page_size=5" | python -m json.tool >/tmp/class-students-smoke.json
  python - <<'PY'
import json
with open('/tmp/class-students-smoke.json', encoding='utf-8') as f:
    data=json.load(f)
print('class_students_keys=', sorted(data.keys())[:20])
print('items_len=', len(data.get('items') or data.get('students') or []))
PY
else
  echo "skip: set API_BASE_URL, AUTH_HEADER, CLASS_ID to test authenticated class APIs"
fi

echo "\n[8/10] optional connector denominator sanity"
if command -v tutor >/dev/null 2>&1 && [[ -n "$TUTOR_COURSE_ID" ]]; then
  tutor local run lms python - <<PY
from opaque_keys.edx.keys import CourseKey
from openedx_ai_connector.student_insight import _completion_denominator_block_snapshot
s = _completion_denominator_block_snapshot(CourseKey.from_string('${TUTOR_COURSE_ID}'))
print('eligible_total=', s.get('eligible_total'))
print('subsection_total=', s.get('subsection_total'))
print('non_container_blocks=', s.get('non_container_blocks'))
print('denominator_source=', s.get('denominator_source'))
PY
else
  echo "skip: set COURSE_ID/TUTOR_COURSE_ID to check connector denominator"
fi


echo "\n[9/10] optional authenticated analytics dashboard"
if [[ -n "$API_BASE_URL" && -n "$AUTH_HEADER" ]]; then
  curl -fsS -H "$AUTH_HEADER" "$API_BASE_URL/api/analytics/ops/status" | python -m json.tool >/tmp/analytics-ops-smoke.json
  curl -fsS -H "$AUTH_HEADER" "$API_BASE_URL/api/analytics/ops/production-readiness" | python -m json.tool >/tmp/analytics-production-readiness-smoke.json
  curl -fsS -H "$AUTH_HEADER" "$API_BASE_URL/api/analytics/ops/rollout-control?limit=5" | python -m json.tool >/tmp/analytics-rollout-control-smoke.json
  curl -fsS -H "$AUTH_HEADER" "$API_BASE_URL/api/analytics/ops/monitoring" | python -m json.tool >/tmp/analytics-monitoring-smoke.json
  pilot_url="$API_BASE_URL/api/analytics/ops/pilot-acceptance?sample_limit=5"
  [[ -n "$CLASS_ID" ]] && pilot_url="$pilot_url&class_id=$CLASS_ID"
  [[ -n "$COURSE_ID" ]] && pilot_url="$pilot_url&course_id=$COURSE_ID"
  curl -fsS -H "$AUTH_HEADER" "$pilot_url" | python -m json.tool >/tmp/analytics-pilot-acceptance-smoke.json
  quality_url="$API_BASE_URL/api/analytics/ops/data-quality"
  plan_url="$API_BASE_URL/api/analytics/backfill/plan?limit=5"
  if [[ -n "$CLASS_ID" ]]; then
    quality_url="$quality_url?class_id=$CLASS_ID"
    plan_url="$plan_url&class_id=$CLASS_ID"
  fi
  if [[ -n "$COURSE_ID" ]]; then
    if [[ "$quality_url" == *"?"* ]]; then quality_url="$quality_url&course_id=$COURSE_ID"; else quality_url="$quality_url?course_id=$COURSE_ID"; fi
    plan_url="$plan_url&course_id=$COURSE_ID"
  fi
  curl -fsS -H "$AUTH_HEADER" "$quality_url" | python -m json.tool >/tmp/analytics-quality-smoke.json
  curl -fsS -H "$AUTH_HEADER" "$plan_url" | python -m json.tool >/tmp/analytics-backfill-plan-smoke.json
  python - <<'PY'
import json
for path in ['/tmp/analytics-ops-smoke.json', '/tmp/analytics-production-readiness-smoke.json', '/tmp/analytics-rollout-control-smoke.json', '/tmp/analytics-monitoring-smoke.json', '/tmp/analytics-pilot-acceptance-smoke.json', '/tmp/analytics-quality-smoke.json', '/tmp/analytics-backfill-plan-smoke.json']:
    with open(path, encoding='utf-8') as f:
        data=json.load(f)
    print(path, 'version=', data.get('version'), 'safe_policy=', data.get('safe_policy'))
    assert data.get('safe_policy') == 'signals_only_not_violation'
PY
else
  echo "skip: set API_BASE_URL and AUTH_HEADER to test authenticated analytics APIs"
fi

echo "\n[10/10] recent logs tail"
docker compose -f "$COMPOSE_FILE" --env-file "$ENV_FILE" logs --tail=40 backend worker frontend | sed -n '1,160p'

echo "\n[PASS] smoke test pack completed"
