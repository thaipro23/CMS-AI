#!/usr/bin/env bash
set -euo pipefail
ROOT="${TUTOR_ROOT:-}"
if [ -z "$ROOT" ] && command -v tutor >/dev/null 2>&1; then
  ROOT="$(tutor config printroot)"
fi
EXPECTED_HOST_DIR="${OPENEDX_TRACKING_LOG_HOST_DIR:-${ROOT:+$ROOT/data/lms/logs}}"
CONTAINER_PATH="${OPENEDX_TRACKING_LOG_PATH:-/openedx-data/lms/logs/tracking.log}"
COMPOSE_FILE="${COMPOSE_FILE:-docker-compose.prod.yml}"
ENV_FILE="${ENV_FILE:-.env.production}"

echo "== Analytics tracking log doctor =="
echo "Tutor root: ${ROOT:-N/A}"
echo "Expected host dir: ${EXPECTED_HOST_DIR:-N/A}"
echo "Container path: $CONTAINER_PATH"
if [ -n "${EXPECTED_HOST_DIR:-}" ]; then
  ls -lah "$EXPECTED_HOST_DIR" || true
  if [ -f "$EXPECTED_HOST_DIR/tracking.log" ]; then
    echo "HOST_TRACKING_OK: $EXPECTED_HOST_DIR/tracking.log"
  else
    echo "HOST_TRACKING_MISSING: set OPENEDX_TRACKING_LOG_HOST_DIR=$(tutor config printroot)/data/lms/logs"
  fi
fi
if command -v docker >/dev/null 2>&1; then
  echo "-- backend container check --"
  docker compose -f "$COMPOSE_FILE" --env-file "$ENV_FILE" exec -T backend bash -lc "ls -lah /openedx-data/lms/logs || true; test -f '$CONTAINER_PATH' && echo CONTAINER_TRACKING_OK || echo CONTAINER_TRACKING_MISSING" || true
  echo "-- worker container check --"
  docker compose -f "$COMPOSE_FILE" --env-file "$ENV_FILE" exec -T worker bash -lc "test -f '$CONTAINER_PATH' && echo WORKER_TRACKING_OK || echo WORKER_TRACKING_MISSING" || true
fi
