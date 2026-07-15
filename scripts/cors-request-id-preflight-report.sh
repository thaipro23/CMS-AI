#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
OUT_DIR="${1:-/tmp/ai-cors-request-id-preflight}"
mkdir -p "$OUT_DIR"
cd "$ROOT"

python - <<'PY' > "$OUT_DIR/cors-request-id-preflight.json"
import ast
import json
from pathlib import Path
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.testclient import TestClient

root = Path.cwd()
source = (root / 'backend/app/main.py').read_text(encoding='utf-8')
tree = ast.parse(source)
headers = None
for node in tree.body:
    if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == '_base_cors_headers' for t in node.targets):
        headers = ast.literal_eval(node.value)
        break
assert isinstance(headers, list), '_base_cors_headers missing'

origin = 'http://ai.cms-test.poly.edu.vn'
app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=[origin],
    allow_credentials=True,
    allow_methods=['GET', 'POST', 'PUT', 'PATCH', 'DELETE', 'OPTIONS'],
    allow_headers=headers,
    expose_headers=['X-Request-ID', 'X-Process-Time-Ms'],
)
response = TestClient(app).options(
    '/api/auth/openedx-session/exchange',
    headers={
        'Origin': origin,
        'Access-Control-Request-Method': 'POST',
        'Access-Control-Request-Headers': 'content-type,x-request-id',
    },
)
checks = {
    'request_id_allowed_in_source': 'X-Request-ID' in headers,
    'request_id_exposed_in_source': "expose_headers=['X-Request-ID', 'X-Process-Time-Ms']" in source,
    'preflight_status_200': response.status_code == 200,
    'origin_reflected': response.headers.get('access-control-allow-origin') == origin,
    'credentials_allowed': response.headers.get('access-control-allow-credentials') == 'true',
    'request_id_allowed_in_response': 'x-request-id' in response.headers.get('access-control-allow-headers', '').lower(),
}
result = {
    'status': 'READY' if all(checks.values()) else 'BLOCKED',
    'passed': sum(checks.values()),
    'total': len(checks),
    'checks': checks,
    'response_status': response.status_code,
    'response_headers': dict(response.headers),
}
print(json.dumps(result, ensure_ascii=False, indent=2))
if result['status'] != 'READY':
    raise SystemExit(1)
PY

python - "$OUT_DIR/cors-request-id-preflight.json" <<'PY'
import json, sys
result=json.load(open(sys.argv[1], encoding='utf-8'))
print(f"CORS request-id preflight: {result['status']} — {result['passed']}/{result['total']}")
PY
