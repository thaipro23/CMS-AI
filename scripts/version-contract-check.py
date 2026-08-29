#!/usr/bin/env python3
from pathlib import Path
import json
import sys

ROOT = Path(__file__).resolve().parents[1]
VERSION = (ROOT / 'VERSION').read_text().strip()
checks = {
    'backend/app/core/config.py': VERSION,
    'frontend/Dockerfile': VERSION,
    'docker-compose.prod.yml': VERSION,
    'deploy/k8s/base/kustomization.yaml': VERSION,
    'deploy/k8s/jobs/kustomization.yaml': VERSION,
    'deploy/k8s/jobs/migrate.yaml': VERSION,
    'scripts/build-k8s-images.sh': VERSION,
    '.env.example': VERSION,
    '.env.production.example': VERSION,
    'Jenkinsfile': VERSION,
    'README.md': VERSION,
    'RUN_CURRENT.md': VERSION,
}
errors=[]
for rel, expected in checks.items():
    text=(ROOT/rel).read_text()
    if expected not in text:
        errors.append(f'{rel}: missing {expected}')
for rel in ['frontend/package.json','frontend/package-lock.json','e2e/package.json','e2e/package-lock.json']:
    data=json.loads((ROOT/rel).read_text())
    if data.get('version') != VERSION:
        errors.append(f'{rel}: version={data.get("version")!r}')
    root_pkg=(data.get('packages') or {}).get('')
    if root_pkg is not None and root_pkg.get('version') != VERSION:
        errors.append(f'{rel}: packages[""].version={root_pkg.get("version")!r}')
# Active build/runtime files must not retain the immediately previous/fallback tags.
for rel in checks:
    text=(ROOT/rel).read_text()
    for stale in ('25.9.16.7.2.64.16.5.7.2.15','25.9.16.7.2.64.16.5.7.2.14','25.9.16.7.2.64.16.5.7.2.11'):
        if stale in text:
            errors.append(f'{rel}: stale version {stale}')
if errors:
    print('VERSION_CONTRACT_FAILED')
    print('\n'.join(errors))
    sys.exit(1)
print(f'VERSION_CONTRACT_OK {VERSION}')
