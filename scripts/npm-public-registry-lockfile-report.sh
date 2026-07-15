#!/usr/bin/env bash
set -Eeuo pipefail
VERSION="25.9.16.7.2.64.16.5.7.2.3"
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
OUT_DIR="${1:-$ROOT/.runtime/npm-public-registry}"
mkdir -p "$OUT_DIR"
python - "$ROOT" "$OUT_DIR/npm-public-registry-lockfile.json" <<'PY'
import json
import sys
from pathlib import Path
from urllib.parse import urlparse

root = Path(sys.argv[1])
output = Path(sys.argv[2])
lockfiles = [root / 'frontend/package-lock.json', root / 'e2e/package-lock.json']
internal_markers = (
    'applied-caas-gateway',
    'internal.api.openai.org',
    '/artifactory/api/npm/',
)
allowed_host = 'registry.npmjs.org'
results = []
blocked = []
for lockfile in lockfiles:
    data = json.loads(lockfile.read_text(encoding='utf-8'))
    resolved_urls = []
    for name, package in (data.get('packages') or {}).items():
        if isinstance(package, dict) and isinstance(package.get('resolved'), str):
            resolved_urls.append((name, package['resolved']))
    wrong = []
    for package_name, url in resolved_urls:
        lowered = url.lower()
        host = (urlparse(url).hostname or '').lower()
        if any(marker in lowered for marker in internal_markers) or host != allowed_host:
            wrong.append({'package': package_name, 'url': url, 'host': host})
    record = {
        'lockfile': str(lockfile.relative_to(root)),
        'resolved_count': len(resolved_urls),
        'wrong_registry_count': len(wrong),
        'wrong_registry': wrong[:50],
    }
    results.append(record)
    blocked.extend(wrong)

npmrc_results = []
for rel in ('frontend/.npmrc', 'e2e/.npmrc'):
    source = (root / rel).read_text(encoding='utf-8')
    ok = 'registry=https://registry.npmjs.org/' in source
    npmrc_results.append({'file': rel, 'public_registry': ok})
    if not ok:
        blocked.append({'package': rel, 'url': 'missing public registry config', 'host': ''})

payload = {
    'status': 'READY' if not blocked else 'BLOCKED',
    'public_registry': 'https://registry.npmjs.org/',
    'lockfiles': results,
    'npmrc': npmrc_results,
    'blocked_count': len(blocked),
}
output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
print(json.dumps(payload, ensure_ascii=False, indent=2))
if blocked:
    raise SystemExit(1)
PY
