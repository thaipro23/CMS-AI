#!/usr/bin/env bash
set -euo pipefail

COMPOSE_FILE="${COMPOSE_FILE:-docker-compose.prod.yml}"
ENV_FILE="${ENV_FILE:-.env.production}"
PROJECT_DIR="${PROJECT_DIR:-$(pwd)}"
SERVICES="${SERVICES:-backend worker frontend}"

cd "$PROJECT_DIR"

if [[ ! -f "$COMPOSE_FILE" ]]; then
  echo "[FAIL] Missing $COMPOSE_FILE in $PROJECT_DIR" >&2
  exit 2
fi
if [[ ! -f "$ENV_FILE" ]]; then
  echo "[FAIL] Missing $ENV_FILE in $PROJECT_DIR" >&2
  exit 2
fi

echo "== AI Server production build verification =="
echo "Project: $PROJECT_DIR"
echo "Compose: $COMPOSE_FILE"
echo "Env: $ENV_FILE"
echo "Services: $SERVICES"

echo "\n[1/6] docker compose config"
docker compose -f "$COMPOSE_FILE" --env-file "$ENV_FILE" config >/tmp/ai-server-compose-config.$$ 
wc -l /tmp/ai-server-compose-config.$$ | awk '{print "compose_config_lines="$1}'
rm -f /tmp/ai-server-compose-config.$$

echo "\n[2/6] build images"
docker compose -f "$COMPOSE_FILE" --env-file "$ENV_FILE" build $SERVICES

echo "\n[3/6] start services"
docker compose -f "$COMPOSE_FILE" --env-file "$ENV_FILE" up -d --force-recreate $SERVICES

echo "\n[4/6] wait backend health"
for i in $(seq 1 40); do
  if docker compose -f "$COMPOSE_FILE" --env-file "$ENV_FILE" exec -T backend python - <<'PY' >/dev/null 2>&1
import urllib.request
urllib.request.urlopen('http://127.0.0.1:8000/api/health', timeout=5).read()
PY
  then
    echo "backend_health=ok"
    break
  fi
  if [[ "$i" == "40" ]]; then
    echo "[FAIL] backend health did not become ready" >&2
    docker compose -f "$COMPOSE_FILE" --env-file "$ENV_FILE" logs --tail=120 backend >&2 || true
    exit 3
  fi
  sleep 3
done

echo "\n[5/6] backend identity + db"
docker compose -f "$COMPOSE_FILE" --env-file "$ENV_FILE" exec -T backend python - <<'PY'
import json, urllib.request
for path in ['/api/health/build', '/api/health/db', '/api/health/openedx-connector/config', '/api/health/analytics']:
    with urllib.request.urlopen('http://127.0.0.1:8000' + path, timeout=10) as r:
        data = json.loads(r.read().decode('utf-8'))
    print(path, json.dumps(data, ensure_ascii=False, sort_keys=True))
PY

echo "\n[6/6] service status"
docker compose -f "$COMPOSE_FILE" --env-file "$ENV_FILE" ps

echo "\n[PASS] production build verification completed"
