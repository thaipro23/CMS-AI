#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VERSION="${EXPECTED_VERSION:-25.9.16.7.2.64.16.5.7.2.18}"
pass=0
fail=0
check() {
  local label="$1"; shift
  if "$@"; then printf 'PASS  %s\n' "$label"; pass=$((pass+1)); else printf 'FAIL  %s\n' "$label"; fail=$((fail+1)); fi
}
contains() { grep -Fq -- "$2" "$1"; }

check 'current backend version' contains "$ROOT/backend/app/core/config.py" "$VERSION"
check 'npm is pinned' contains "$ROOT/frontend/Dockerfile" 'ARG NPM_VERSION=10.9.2'
check 'npm cache mount exists' contains "$ROOT/frontend/Dockerfile" '--mount=type=cache,id=ai-server-frontend-npm'
check 'npm ci has retry loop' contains "$ROOT/frontend/Dockerfile" 'while ! npm ci'
check 'hardened runtime ignores locked fields' contains "$ROOT/backend/app/services/runtime_settings.py" 'Ignoring locked runtime setting'
check 'invalid runtime values are ignored' contains "$ROOT/backend/app/services/runtime_settings.py" 'Ignoring invalid runtime setting'
check 'UAT also locks runtime security settings' contains "$ROOT/backend/app/services/runtime_settings.py" 'if is_hardened_deployment():'
check 'backend healthcheck avoids shell heredoc' python -c "import yaml; d=yaml.safe_load(open('$ROOT/docker-compose.prod.yml')); assert d['services']['backend']['healthcheck']['test'][0] == 'CMD'"
check 'backend warmup is extended' contains "$ROOT/docker-compose.prod.yml" 'start_period: 90s'
check 'gunicorn output is captured' contains "$ROOT/docker-compose.prod.yml" '--capture-output'

printf '\nResult: %s pass, %s fail\n' "$pass" "$fail"
if (( fail > 0 )); then exit 1; fi
printf 'READY — UAT build/backend health hotfix %s\n' "$VERSION"
