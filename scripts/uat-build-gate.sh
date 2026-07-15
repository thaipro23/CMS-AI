#!/usr/bin/env bash
set -Eeuo pipefail

ROOT_DIR="${ROOT_DIR:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
OUT_DIR="${OUT_DIR:-$ROOT_DIR/.runtime/uat-build-gate-$(date +%Y%m%d-%H%M%S)}"
EXPECTED_VERSION="${EXPECTED_VERSION:-25.9.16.7.2.64.16.5.7.1}"
STRICT="${STRICT:-0}"
RUN_FRONTEND_BUILD="${RUN_FRONTEND_BUILD:-0}"
RUN_FRONTEND_INSTALL="${RUN_FRONTEND_INSTALL:-0}"
RUN_BACKEND_TESTS="${RUN_BACKEND_TESTS:-1}"
RUN_REVIEW_PACK="${RUN_REVIEW_PACK:-0}"
mkdir -p "$OUT_DIR"
cd "$ROOT_DIR"

log() { printf '[uat-build-gate] %s\n' "$*"; }
: > "$OUT_DIR/checks.tsv"

record_status() {
  local level="$1" code="$2" message="$3" evidence="${4:-}"
  printf '%s\t%s\t%s\t%s\n' "$level" "$code" "$message" "$evidence" >> "$OUT_DIR/checks.tsv"
}

run_and_record() {
  local code="$1" message="$2" evidence="$3"
  shift 3
  log "$message"
  if "$@" > "$OUT_DIR/$evidence" 2>&1; then
    record_status PASS "$code" "$message" "$evidence"
  else
    record_status FAIL "$code" "$message" "$evidence"
  fi
}

warn_or_fail_when_strict() {
  local code="$1" message="$2" evidence="${3:-}"
  if [[ "$STRICT" == "1" ]]; then
    record_status FAIL "$code" "$message" "$evidence"
  else
    record_status WARN "$code" "$message" "$evidence"
  fi
}

log "Writing UAT build gate evidence to $OUT_DIR"

# Version synchronization gate. This must pass before Docker build/deploy.
VERSION_TARGETS=(
  "backend/app/core/config.py"
  "frontend/package.json"
  "docker-compose.prod.yml"
  ".env.example"
  ".env.production.example"
  "frontend/Dockerfile"
  "frontend/package-lock.json"
  "scripts/frontend-build-verify.sh"
  "scripts/uat-runtime-verify.sh"
  "scripts/performance-readiness-report.sh"
  "scripts/query-hotspot-report.sh"
  "scripts/maintainability-contract-report.sh"
  "scripts/security-readiness-report.sh"
  "scripts/security-attack-simulation-report.sh"
  "scripts/performance-worker-reliability-report.sh"
  "scripts/frontend-runtime-contracts-report.sh"
  "scripts/ci-e2e-container-hardening-report.sh"
  "scripts/pilot-release-candidate-report.sh"
  "scripts/pilot-operations-runbook.sh"
  "scripts/openedx-publish-verify.sh"
  "scripts/load-test-hot-endpoints.sh"
  "scripts/production-pilot-final-gate.sh"
  "README.md"
  "RUN_CURRENT.md"
)
for f in "${VERSION_TARGETS[@]}"; do
  if [[ ! -f "$f" ]]; then
    record_status FAIL VERSION_TARGET_MISSING "$f is missing"
  elif grep -q "$EXPECTED_VERSION" "$f"; then
    record_status PASS VERSION_SYNC "$f contains $EXPECTED_VERSION"
  else
    record_status FAIL VERSION_SYNC "$f does not contain $EXPECTED_VERSION"
  fi
done

# Enterprise UX foundation module gate.
UX_FOUNDATION_FILES=(
  "frontend/components/navigation/Breadcrumbs.tsx"
  "frontend/components/table/EnterpriseDataTable.tsx"
  "frontend/components/table/TableStates.tsx"
  "frontend/hooks/useUrlTableState.ts"
  "frontend/styles/enterprise-ui.css"
)
for f in "${UX_FOUNDATION_FILES[@]}"; do
  if [[ -f "$f" ]]; then
    record_status PASS UX_FOUNDATION_MODULE "$f exists"
  else
    record_status FAIL UX_FOUNDATION_MODULE_MISSING "$f is missing"
  fi
done

# Alembic revision chain guard. Migration 0053 is intentional for diff idempotency.
if [[ -f backend/alembic/versions/0053_v25_9_16_7_2_64_16_5_4_diff_idempotency.py ]]; then
  record_status PASS ALEMBIC_HEAD_KNOWN "Latest known migration 0053 is present"
else
  record_status FAIL ALEMBIC_HEAD_KNOWN "Expected latest migration 0053 is missing"
fi
find backend/alembic/versions -maxdepth 1 -type f \( -name '0054_*.py' -o -name '0055_*.py' \) 2>/dev/null | sort > "$OUT_DIR/newer-migrations.txt" || true
if [[ -s "$OUT_DIR/newer-migrations.txt" ]]; then
  record_status FAIL ALEMBIC_UNEXPECTED_NEWER "Unexpected migration newer than 0053 exists" "newer-migrations.txt"
else
  record_status PASS ALEMBIC_NO_UNEXPECTED_NEWER "No migration newer than 0053 detected"
fi

# Backend syntax/import-light gate. compileall does not require PostgreSQL connection.
run_and_record PY_COMPILE "python -m compileall backend/app" py_compile.log python -m compileall -q backend/app

# Backend dependency and targeted test gate. In a real UAT environment psycopg must be installed.
python - <<'PY' > "$OUT_DIR/python-dependency-check.json" 2>&1
import importlib.util, json
required = ['fastapi', 'sqlalchemy', 'psycopg', 'pytest']
print(json.dumps({name: bool(importlib.util.find_spec(name)) for name in required}, indent=2))
PY
if python - <<'PY' >/dev/null 2>&1
import importlib.util
raise SystemExit(0 if importlib.util.find_spec('pytest') and importlib.util.find_spec('psycopg') else 1)
PY
then
  if [[ "$RUN_BACKEND_TESTS" == "1" ]]; then
    run_and_record BACKEND_TARGETED_TESTS "pytest targeted versioned/static tests" backend-targeted-tests.log \
      env PYTHONPATH=backend python -m pytest -q \
      backend/app/tests/test_v25_9_16_7_2_64_16_5_4_production_security_closure.py \
      backend/app/tests/test_v25_9_16_7_2_64_16_5_5_performance_worker_reliability.py \
      backend/app/tests/test_v25_9_16_7_2_64_16_5_7_release_contract.py \
      backend/app/tests/test_v25_9_15_3_version_diff_carry_over_retire.py
  else
    record_status WARN BACKEND_TARGETED_TESTS_SKIPPED "RUN_BACKEND_TESTS=0; backend pytest gate skipped" "python-dependency-check.json"
  fi
else
  warn_or_fail_when_strict BACKEND_TEST_DEPS_MISSING "pytest/psycopg not available; install backend requirements before UAT sign-off" "python-dependency-check.json"
fi

# CI, browser E2E and container hardening gate.
if ./scripts/ci-e2e-container-hardening-report.sh "$OUT_DIR/ci-e2e-container-hardening" > "$OUT_DIR/ci-e2e-container-hardening.log" 2>&1; then
  record_status PASS CI_E2E_CONTAINER_HARDENING "CI/E2E/container hardening contract passed" "ci-e2e-container-hardening/ci-e2e-container-hardening.json"
else
  record_status FAIL CI_E2E_CONTAINER_HARDENING "CI/E2E/container hardening contract failed" "ci-e2e-container-hardening.log"
fi

# Runtime import/name and frontend layout integrity gates.
if ./scripts/backend-runtime-name-audit.sh "$OUT_DIR/backend-runtime-name-audit" > "$OUT_DIR/backend-runtime-name-audit.log" 2>&1; then
  record_status PASS BACKEND_RUNTIME_NAME_AUDIT "Backend runtime symbol audit passed" "backend-runtime-name-audit/backend-runtime-name-audit.json"
else
  record_status FAIL BACKEND_RUNTIME_NAME_AUDIT "Backend runtime symbol audit failed" "backend-runtime-name-audit.log"
fi
if ./scripts/frontend-layout-integrity-report.sh "$OUT_DIR/frontend-layout-integrity" > "$OUT_DIR/frontend-layout-integrity.log" 2>&1; then
  record_status PASS FRONTEND_LAYOUT_INTEGRITY "Frontend spacing/overlap contract passed" "frontend-layout-integrity/frontend-layout-integrity.json"
else
  record_status FAIL FRONTEND_LAYOUT_INTEGRITY "Frontend spacing/overlap contract failed" "frontend-layout-integrity.log"
fi

# Production security P0/P1 closure gate.
if ./scripts/production-security-closure-report.sh "$OUT_DIR/production-security-closure" > "$OUT_DIR/production-security-closure.log" 2>&1; then
  record_status PASS PRODUCTION_SECURITY_CLOSURE "Production security P0/P1 source contract passed" "production-security-closure/production-security-closure.json"
else
  record_status FAIL PRODUCTION_SECURITY_CLOSURE "Production security P0/P1 source contract failed" "production-security-closure.log"
fi


# Performance/API/Celery reliability gate.
if ./scripts/performance-worker-reliability-report.sh "$OUT_DIR/performance-worker-reliability" > "$OUT_DIR/performance-worker-reliability.log" 2>&1; then
  record_status PASS PERFORMANCE_WORKER_RELIABILITY "Performance/API/Celery reliability contract passed" "performance-worker-reliability/performance-worker-reliability.json"
else
  record_status FAIL PERFORMANCE_WORKER_RELIABILITY "Performance/API/Celery reliability contract failed" "performance-worker-reliability.log"
fi

# Frontend runtime, modal and route-state contracts.
if ./scripts/frontend-runtime-contracts-report.sh "$OUT_DIR/frontend-runtime-contracts" > "$OUT_DIR/frontend-runtime-contracts.log" 2>&1; then
  record_status PASS FRONTEND_RUNTIME_CONTRACTS "Frontend modal/error/table runtime contract passed" "frontend-runtime-contracts/frontend-runtime-contracts.json"
else
  record_status FAIL FRONTEND_RUNTIME_CONTRACTS "Frontend modal/error/table runtime contract failed" "frontend-runtime-contracts.log"
fi

# Frontend typecheck/build. v25.9.16.7.2.64.16.5.7.1 delegates the deep
# frontend verification to scripts/frontend-build-verify.sh so package-lock,
# Dockerfile build args, tsc, next build and standalone output are validated
# consistently in one report.
if [[ "$RUN_FRONTEND_BUILD" == "1" ]]; then
  if OUT_DIR="$OUT_DIR/frontend-build-verify" EXPECTED_VERSION="$EXPECTED_VERSION" RUN_NPM_CI="$RUN_FRONTEND_INSTALL" RUN_FRONTEND_BUILD=1 ./scripts/frontend-build-verify.sh > "$OUT_DIR/frontend-build-verify.log" 2>&1; then
    record_status PASS FRONTEND_BUILD_VERIFY "frontend-build-verify.sh passed" "frontend-build-verify/frontend-build-summary.json"
  else
    record_status FAIL FRONTEND_BUILD_VERIFY "frontend-build-verify.sh failed" "frontend-build-verify.log"
  fi
else
  cat > "$OUT_DIR/frontend-build-instructions.txt" <<'TXT'
Frontend build was not executed because RUN_FRONTEND_BUILD=0.
Run on UAT before sign-off:

cd /opt/ai-server
OUT_DIR=/tmp/ai-frontend-build-$(date +%Y%m%d-%H%M%S) \
EXPECTED_VERSION=25.9.16.7.2.64.16.5.7.1 \
RUN_NPM_CI=1 \
RUN_FRONTEND_BUILD=1 \
./scripts/frontend-build-verify.sh

Or run the full gate:

OUT_DIR=/tmp/ai-server-uat-build-gate-$(date +%Y%m%d-%H%M%S) \
STRICT=1 \
RUN_FRONTEND_BUILD=1 \
RUN_FRONTEND_INSTALL=1 \
RUN_REVIEW_PACK=1 \
./scripts/uat-build-gate.sh
TXT
  warn_or_fail_when_strict FRONTEND_BUILD_VERIFY_SKIPPED "RUN_FRONTEND_BUILD=0; frontend build verification skipped" "frontend-build-instructions.txt"
fi

# Docker Compose config validation when Docker is available and production env exists.
if command -v docker >/dev/null 2>&1 && [[ -f .env.production ]]; then
  run_and_record DOCKER_COMPOSE_CONFIG "docker compose production config validation" docker-compose-config.log \
    docker compose -f docker-compose.prod.yml --env-file .env.production config
else
  record_status WARN DOCKER_COMPOSE_CONFIG_SKIPPED "Docker or .env.production not available in this runtime; validate on UAT" ""
fi

# Reuse Claude review static pack if requested.
if [[ "$RUN_REVIEW_PACK" == "1" ]]; then
  if OUT_DIR="$OUT_DIR/claude-code-review-pack" EXPECTED_VERSION="$EXPECTED_VERSION" ./scripts/claude-code-review-pack.sh > "$OUT_DIR/claude-code-review-pack.log" 2>&1; then
    record_status PASS CLAUDE_REVIEW_PACK "claude-code-review-pack.sh passed" "claude-code-review-pack/review-summary.json"
  else
    record_status FAIL CLAUDE_REVIEW_PACK "claude-code-review-pack.sh failed" "claude-code-review-pack.log"
  fi
else
  record_status WARN CLAUDE_REVIEW_PACK_SKIPPED "RUN_REVIEW_PACK=0; static review pack was not generated by this gate" ""
fi

python - <<'PY' "$OUT_DIR/checks.tsv" "$OUT_DIR/build-gate-summary.json" "$OUT_DIR/BUILD_GATE_SUMMARY.md"
import csv, json, sys
checks_path, json_path, md_path = sys.argv[1:]
rows = []
with open(checks_path, encoding='utf-8') as fh:
    for row in csv.reader(fh, delimiter='\t'):
        while len(row) < 4:
            row.append('')
        level, code, message, evidence = row[:4]
        rows.append({'level': level, 'code': code, 'message': message, 'evidence': evidence})
status = 'FAIL' if any(r['level'] == 'FAIL' for r in rows) else ('WARN' if any(r['level'] == 'WARN' for r in rows) else 'PASS')
summary = {
    'status': status,
    'failures': sum(r['level'] == 'FAIL' for r in rows),
    'warnings': sum(r['level'] == 'WARN' for r in rows),
    'passes': sum(r['level'] == 'PASS' for r in rows),
    'checks': rows,
}
with open(json_path, 'w', encoding='utf-8') as fh:
    json.dump(summary, fh, ensure_ascii=False, indent=2)
with open(md_path, 'w', encoding='utf-8') as fh:
    fh.write('# UAT Build Gate Summary\n\n')
    fh.write(f"Status: **{status}**\n\n")
    fh.write('| Level | Code | Message | Evidence |\n')
    fh.write('|---|---|---|---|\n')
    for r in rows:
        fh.write(f"| {r['level']} | `{r['code']}` | {r['message']} | {r['evidence']} |\n")
print(json.dumps(summary, ensure_ascii=False, indent=2))
PY

summary_status="$(python - <<'PY' "$OUT_DIR/build-gate-summary.json"
import json, sys
print(json.load(open(sys.argv[1], encoding='utf-8'))['status'])
PY
)"
log "Summary: $OUT_DIR/build-gate-summary.json"
if [[ "$summary_status" == "FAIL" ]]; then
  log "Completed with FAIL status."
  exit 1
fi
log "Completed with $summary_status status."
