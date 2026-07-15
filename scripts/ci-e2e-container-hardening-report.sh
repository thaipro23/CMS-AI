#!/usr/bin/env bash
set -Eeuo pipefail
ROOT_DIR="${ROOT_DIR:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
OUT_DIR="${1:-${OUT_DIR:-$ROOT_DIR/.runtime/ci-e2e-container-hardening}}"
EXPECTED_VERSION="${EXPECTED_VERSION:-25.9.16.7.2.64.16.5.7.1}"
mkdir -p "$OUT_DIR"
python - "$ROOT_DIR" "$OUT_DIR" "$EXPECTED_VERSION" <<'PY'
from __future__ import annotations
import json, sys
from pathlib import Path
import yaml
root=Path(sys.argv[1]); out=Path(sys.argv[2]); version=sys.argv[3]
def read(p): return (root/p).read_text(encoding='utf-8')
def check(code, ok, message): return {'code':code,'ok':bool(ok),'severity':'INFO' if ok else 'BLOCKER','message':message}
workflow=read('.github/workflows/ci.yml')
backend=read('backend/Dockerfile.prod')
frontend=read('frontend/Dockerfile')
package=json.loads(read('frontend/package.json'))
compose=yaml.safe_load(read('docker-compose.prod.yml'))
services=compose['services']
app_services=['backend','worker','worker-heavy','worker-analytics','beat','frontend']
checks=[
 check('VERSION_SYNC', version in read('backend/app/core/config.py') and version==package['version'], 'Application versions are synchronized.'),
 check('CI_WORKFLOW', all(x in workflow for x in ['backend-quality','frontend:','browser-e2e','container-hardening']), 'CI has backend, frontend, browser and container jobs.'),
 check('POSTGRES_REDIS_INTEGRATION', 'pgvector/pgvector:pg16' in workflow and 'redis:7-alpine' in workflow and 'alembic -c alembic.ini upgrade head' in workflow, 'CI provisions PostgreSQL/Redis and applies migrations.'),
 check('PLAYWRIGHT_CONTRACT', (root/'e2e/package.json').exists() and '@playwright/test' in json.loads(read('e2e/package.json')).get('devDependencies',{}) and (root/'e2e/playwright.config.ts').exists() and (root/'e2e/tests/production-smoke.spec.ts').exists(), 'Playwright browser smoke tests are versioned.'),
 check('FRONTEND_QUALITY', all(k in package['scripts'] for k in ['lint','typecheck','build','test:e2e:ci']), 'Frontend exposes lint, typecheck, build and E2E commands.'),
 check('BACKEND_MULTI_STAGE', ' AS wheels' in backend and 'requirements-runtime.txt' in backend and 'USER ${APP_UID}:${APP_GID}' in backend, 'Backend production image is multi-stage and non-root.'),
 check('BACKEND_NO_BUILD_TOOLCHAIN', 'pip wheel' in backend and '! command -v gcc' in workflow, 'Runtime image excludes the build toolchain and CI verifies it.'),
 check('FRONTEND_NON_ROOT', 'USER ${APP_UID}:${APP_GID}' in frontend and 'chmod -R a-w /app' in frontend, 'Frontend runtime is non-root and immutable.'),
 check('MIGRATION_JOB', 'migrate' in services and services['migrate'].get('restart')=='no' and 'alembic' in ' '.join(services['migrate'].get('command',[])), 'Migration runs as a deployment job, not in every API replica.'),
 check('BACKEND_NO_INLINE_MIGRATION', 'alembic' not in ' '.join(services['backend'].get('command',[])), 'Backend startup does not race Alembic migrations.'),
 check('RUNTIME_VOLUME_INIT', 'runtime-init' in services and 'runtime_data:/app/.runtime' in services['runtime-init'].get('volumes',[]), 'Writable runtime volume ownership is initialized explicitly.'),
 check('APP_HARDENING', all(services[n].get('user')=='10001:10001' and services[n].get('read_only') is True and 'ALL' in services[n].get('cap_drop',[]) and 'no-new-privileges:true' in services[n].get('security_opt',[]) and services[n].get('pids_limit') for n in app_services), 'All application services run non-root with read-only rootfs, dropped capabilities and PID limits.'),
 check('RESOURCE_LIMITS', all(services[n].get('mem_limit') and services[n].get('cpus') for n in app_services), 'Application services have explicit CPU and memory ceilings.'),
 check('HEALTHCHECKS', all(services[n].get('healthcheck') for n in app_services), 'All long-running application services have healthchecks.'),
 check('DEPENDABOT', (root/'.github/dependabot.yml').exists(), 'Automated dependency update configuration is present.'),
 check('INTEGRATION_TESTS', (root/'backend/app/tests/integration/test_ci_runtime_smoke.py').exists() and 'integration' in read('backend/pytest.ini'), 'PostgreSQL and Redis integration tests are versioned.'),
]
blockers=[c for c in checks if not c['ok']]
payload={'version':version,'report_type':'ci_e2e_container_hardening','status':'READY' if not blockers else 'BLOCKED','passed':sum(c['ok'] for c in checks),'blocker_count':len(blockers),'checks':checks}
(out/'ci-e2e-container-hardening.json').write_text(json.dumps(payload,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(payload,ensure_ascii=False,indent=2))
raise SystemExit(1 if blockers else 0)
PY
