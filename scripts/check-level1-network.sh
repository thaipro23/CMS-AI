#!/usr/bin/env bash
set -euo pipefail
NETWORK="${OPENEDX_SHARED_NETWORK:-tutor_local_default}"
echo "Checking Docker network: ${NETWORK}"
docker network inspect "${NETWORK}" >/dev/null

echo "\nContainers on ${NETWORK}:"
docker network inspect "${NETWORK}" --format '{{range $id, $c := .Containers}}{{println $c.Name}}{{end}}' | sort

echo "\nAI containers:"
docker ps --format 'table {{.Names}}\t{{.Status}}\t{{.Ports}}' | grep -E '(^NAMES|ai-|tutor_local-caddy)' || true

echo "\nTesting backend from inside ai-backend:"
docker exec ai-backend python - <<'PY'
import urllib.request
print(urllib.request.urlopen('http://127.0.0.1:8000/api/health', timeout=5).read().decode())
PY

echo "\nTesting Docker DNS from Tutor Caddy to AI containers:"
docker exec tutor_local-caddy-1 sh -lc 'wget -qO- http://ai-backend:8000/api/health || true; echo; wget -qO- http://ai-frontend:3000 | head -c 200 || true; echo'
