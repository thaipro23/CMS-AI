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

echo "\n[1/8] container status"
docker compose -f "$COMPOSE_FILE" --env-file "$ENV_FILE" ps

echo "\n[2/8] backend health/db/config"
docker compose -f "$COMPOSE_FILE" --env-file "$ENV_FILE" exec -T backend python - <<'PY'
import json, urllib.request
for path in ['/api/health', '/api/health/build', '/api/health/db', '/api/health/openedx-connector/config']:
    with urllib.request.urlopen('http://127.0.0.1:8000' + path, timeout=10) as r:
        data = json.loads(r.read().decode('utf-8'))
    print(path, json.dumps(data, ensure_ascii=False, sort_keys=True))
PY

echo "\n[3/8] frontend container can render root"
docker compose -f "$COMPOSE_FILE" --env-file "$ENV_FILE" exec -T frontend sh -lc "node -e \"fetch('http://127.0.0.1:3000').then(r=>{console.log('frontend_status='+r.status); if(r.status>=500) process.exit(1)}).catch(e=>{console.error(e); process.exit(1)})\""

echo "\n[4/8] worker import check"
docker compose -f "$COMPOSE_FILE" --env-file "$ENV_FILE" exec -T worker python - <<'PY'
from app.worker import celery_app
print('celery_app=', celery_app.main)
PY

echo "\n[5/8] Open edX connector active version"
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

echo "\n[6/8] optional API class detail"
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

echo "\n[7/8] optional connector denominator sanity"
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

echo "\n[8/8] recent logs tail"
docker compose -f "$COMPOSE_FILE" --env-file "$ENV_FILE" logs --tail=40 backend worker frontend | sed -n '1,160p'

echo "\n[PASS] smoke test pack completed"
