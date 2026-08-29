#!/usr/bin/env bash
set -euo pipefail

API_BASE_URL="${API_BASE_URL:-${BACKEND_URL:-http://localhost:8000/api}}"
TOKEN="${TOKEN:-}"
CLASS_ID="${CLASS_ID:-}"
COURSE_ID="${COURSE_ID:-}"
CAMPUS="${CAMPUS:-}"
BRANCH="${BRANCH:-poly}"
LIMIT="${LIMIT:-20}"
SAMPLE_LIMIT="${SAMPLE_LIMIT:-5}"

if [[ -z "$TOKEN" ]]; then
  echo "ERROR: set TOKEN=<Bearer token without the Bearer prefix>" >&2
  exit 2
fi

AUTH_HEADER="Authorization: Bearer ${TOKEN}"

urlencode() {
  python -c 'import sys, urllib.parse; print(urllib.parse.quote(sys.argv[1]))' "$1"
}

call_json() {
  local title="$1"
  local url="$2"
  echo
  echo "== ${title} =="
  if command -v jq >/dev/null 2>&1; then
    curl -fsS "$url" -H "$AUTH_HEADER" | jq
  else
    curl -fsS "$url" -H "$AUTH_HEADER"
  fi
}

query="limit=${LIMIT}"
pilot_query="sample_limit=${SAMPLE_LIMIT}"
if [[ -n "$CLASS_ID" ]]; then
  enc=$(urlencode "$CLASS_ID")
  query="${query}&class_id=${enc}"
  pilot_query="${pilot_query}&class_id=${enc}"
fi
if [[ -n "$COURSE_ID" ]]; then
  enc=$(urlencode "$COURSE_ID")
  query="${query}&course_id=${enc}"
  pilot_query="${pilot_query}&course_id=${enc}"
fi
if [[ -n "$CAMPUS" ]]; then
  enc=$(urlencode "$CAMPUS")
  pilot_query="${pilot_query}&campus=${enc}"
fi
if [[ -n "$BRANCH" ]]; then
  enc=$(urlencode "$BRANCH")
  pilot_query="${pilot_query}&branch=${enc}"
fi

call_json "Build" "${API_BASE_URL}/health/build"
call_json "Production readiness" "${API_BASE_URL}/health/readiness"
call_json "RBAC scope audit" "${API_BASE_URL}/rbac/scope-audit"
call_json "Analytics SLA" "${API_BASE_URL}/analytics/ops/sla?limit=${LIMIT}"
call_json "Analytics pilot acceptance" "${API_BASE_URL}/analytics/ops/pilot-acceptance?${pilot_query}"

if [[ -n "$CLASS_ID" ]]; then
  call_json "Analytics class doctor" "${API_BASE_URL}/analytics/classes/$(urlencode "$CLASS_ID")/doctor"
fi

echo
echo "UAT acceptance smoke completed. Review blocker_count, ready_for_pilot, sla_status, and class doctor data_gap before broad rollout."
