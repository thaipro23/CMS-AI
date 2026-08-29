#!/usr/bin/env bash
set -euo pipefail
COMPOSE_FILE="${COMPOSE_FILE:-docker-compose.prod.yml}"
ENV_FILE="${ENV_FILE:-.env.production}"
API_BASE="${API_BASE:-https://api-ai.cms-test.poly.edu.vn/api}"
AUTH_HEADER="${AUTH_HEADER:-}"

echo "== Production test verify =="
docker compose -f "$COMPOSE_FILE" --env-file "$ENV_FILE" config >/tmp/ai-server-compose-rendered.yml
echo "COMPOSE_CONFIG_OK"
docker compose -f "$COMPOSE_FILE" --env-file "$ENV_FILE" ps
bash ./scripts/analytics-tracking-log-doctor.sh || true

curl_json() {
  local url="$1"
  if [ -n "$AUTH_HEADER" ]; then
    curl -fsS -H "$AUTH_HEADER" "$url"
  else
    curl -fsS "$url"
  fi
}

echo "-- health --"
curl_json "$API_BASE/health" >/tmp/ai-health.json && echo "HEALTH_OK"
curl_json "$API_BASE/health/analytics" >/tmp/ai-analytics-health.json && echo "ANALYTICS_HEALTH_OK"
if [ -n "$AUTH_HEADER" ]; then
  curl_json "$API_BASE/analytics/ops/rollout-control" >/tmp/ai-rollout.json && echo "ROLLOUT_OK"
  curl_json "$API_BASE/analytics/ops/monitoring" >/tmp/ai-monitoring.json && echo "MONITORING_OK"
fi
echo "PASS production test verify completed"
