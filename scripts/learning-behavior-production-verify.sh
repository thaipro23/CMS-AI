#!/usr/bin/env bash
set -euo pipefail

API_BASE_URL="${API_BASE_URL:-http://127.0.0.1:8000}"
AUTH_HEADER="${AUTH_HEADER:-}"
BRANCH="${BRANCH:-poly}"
TERM_ID="${TERM_ID:-}"
CAMPUS="${CAMPUS:-}"
SUBJECT_ID="${SUBJECT_ID:-}"
CLASS_ID="${CLASS_ID:-}"
CLASSIFICATION="${CLASSIFICATION:-all}"

API="${API_BASE_URL%/}"
if [[ "$API" != */api ]]; then
  API="$API/api"
fi

need() {
  local name="$1"
  local value="$2"
  if [[ -z "$value" ]]; then
    echo "[FAIL] Missing $name" >&2
    exit 2
  fi
}

need "AUTH_HEADER" "$AUTH_HEADER"
need "TERM_ID" "$TERM_ID"
need "CAMPUS" "$CAMPUS"
need "SUBJECT_ID" "$SUBJECT_ID"

curl_json() {
  local url="$1"
  curl -fsS -H "$AUTH_HEADER" "$url"
}

check_json_file() {
  local path="$1"
  local label="$2"
  python3 - "$path" "$label" <<'PY'
import json, sys
path, label = sys.argv[1:3]
with open(path, encoding='utf-8') as f:
    data=json.load(f)
if isinstance(data, dict) and data.get('error'):
    raise SystemExit(f'{label}: API_ERROR {data.get("error")}')
text=json.dumps(data, ensure_ascii=False)
for forbidden in ['gian lận', 'cheating', 'treo máy chắc chắn', 'vi phạm chắc chắn']:
    if forbidden.lower() in text.lower():
        raise SystemExit(f'{label}: forbidden wording found: {forbidden}')
print(f'{label}=OK')
PY
}

echo "== Learning behavior production verify =="
echo "API=$API"
echo "branch=$BRANCH term_id=$TERM_ID campus=$CAMPUS subject_id=$SUBJECT_ID class_id=${CLASS_ID:-none}"

subjects_url="$API/academic/teacher/subjects?term_id=$(python3 -c 'import sys,urllib.parse; print(urllib.parse.quote(sys.argv[1]))' "$TERM_ID")&branch=$BRANCH&campus=$CAMPUS&page=1&page_size=200"
echo "[1/4] subject list page_size=200"
curl_json "$subjects_url" >/tmp/ai-lb-subjects.json
check_json_file /tmp/ai-lb-subjects.json SUBJECTS
python3 - <<'PY'
import json
with open('/tmp/ai-lb-subjects.json', encoding='utf-8') as f: data=json.load(f)
print('subjects_items=', len(data.get('items') or []), 'total=', data.get('total'))
assert int(data.get('page_size') or 200) <= 200
PY

encoded_subject=$(python3 -c 'import sys,urllib.parse; print(urllib.parse.quote(sys.argv[1], safe=""))' "$SUBJECT_ID")
overview_url="$API/analytics/subjects/$encoded_subject/classes/learning-behavior/overview?term_id=$(python3 -c 'import sys,urllib.parse; print(urllib.parse.quote(sys.argv[1]))' "$TERM_ID")&branch=$BRANCH&campus=$CAMPUS&limit=200&offset=0"
if [[ "$CLASSIFICATION" != "all" ]]; then overview_url="$overview_url&classification=$CLASSIFICATION"; fi
if [[ -n "$CLASS_ID" ]]; then overview_url="$overview_url&class_id=$(python3 -c 'import sys,urllib.parse; print(urllib.parse.quote(sys.argv[1], safe=""))' "$CLASS_ID")"; fi

echo "[2/4] class behavior overview limit=200"
curl_json "$overview_url" >/tmp/ai-lb-class-overview.json
check_json_file /tmp/ai-lb-class-overview.json CLASS_OVERVIEW
python3 - <<'PY'
import json
with open('/tmp/ai-lb-class-overview.json', encoding='utf-8') as f: data=json.load(f)
items=data.get('items') or []
summary=data.get('summary') or {}
print('class_items=', len(items), 'total=', data.get('total'), 'total_students=', summary.get('total_students'), 'safe_policy=', data.get('safe_policy'))
assert len(items) <= 200
assert data.get('safe_policy') == 'signals_only_not_violation'
PY

if [[ -n "$CLASS_ID" ]]; then
  encoded_class=$(python3 -c 'import sys,urllib.parse; print(urllib.parse.quote(sys.argv[1], safe=""))' "$CLASS_ID")
  echo "[3/4] selected class summary"
  curl_json "$API/analytics/classes/$encoded_class/learning-behavior/summary" >/tmp/ai-lb-class-summary.json
  check_json_file /tmp/ai-lb-class-summary.json CLASS_SUMMARY
  python3 - <<'PY'
import json
with open('/tmp/ai-lb-class-summary.json', encoding='utf-8') as f: data=json.load(f)
print('summary_total_students=', data.get('total_students'), 'likely=', data.get('likely_real_learning_count'), 'review=', (data.get('possible_idle_count') or 0)+(data.get('possible_suspicious_count') or 0))
assert data.get('disclaimer')
PY
  echo "[4/4] selected class result rows"
  curl_json "$API/analytics/classes/$encoded_class/learning-behavior?limit=200&offset=0" >/tmp/ai-lb-class-rows.json
  check_json_file /tmp/ai-lb-class-rows.json CLASS_ROWS
  python3 - <<'PY'
import json
with open('/tmp/ai-lb-class-rows.json', encoding='utf-8') as f: data=json.load(f)
print('row_items=', len(data.get('items') or []), 'total=', data.get('total'))
assert len(data.get('items') or []) <= 200
PY
else
  echo "[3/4] selected class summary=skip set CLASS_ID"
  echo "[4/4] selected class rows=skip set CLASS_ID"
fi

echo "[PASS] learning behavior production verify completed"
