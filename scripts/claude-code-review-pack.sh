#!/usr/bin/env bash
set -Eeuo pipefail

ROOT_DIR="${ROOT_DIR:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
OUT_DIR="${OUT_DIR:-$ROOT_DIR/.runtime/claude-code-review-pack-$(date +%Y%m%d-%H%M%S)}"
EXPECTED_VERSION="${EXPECTED_VERSION:-25.9.16.7.2.64.16.5.7.1.1}"
INCLUDE_BUILD_GATE="${INCLUDE_BUILD_GATE:-0}"
STRICT_BUILD_GATE="${STRICT_BUILD_GATE:-0}"
mkdir -p "$OUT_DIR"

cd "$ROOT_DIR"

log() { printf '[review-pack] %s\n' "$*"; }
failures=0
warnings=0

record_status() {
  local level="$1" code="$2" message="$3"
  printf '%s\t%s\t%s\n' "$level" "$code" "$message" >> "$OUT_DIR/checks.tsv"
  if [[ "$level" == "FAIL" ]]; then failures=$((failures+1)); fi
  if [[ "$level" == "WARN" ]]; then warnings=$((warnings+1)); fi
}
: > "$OUT_DIR/checks.tsv"

log "Writing code review artifact pack to $OUT_DIR"

# 1) Repository manifest: useful for Claude/human reviewers to verify the exact artifact.
python - <<'PY' > "$OUT_DIR/file-manifest.json"
import hashlib, json, os
from pathlib import Path
root = Path.cwd()
ignored = {'.git', 'node_modules', '.next', '__pycache__', '.pytest_cache', '.mypy_cache', '.runtime'}
items = []
for current, dirs, files in os.walk(root):
    dirs[:] = sorted(name for name in dirs if name not in ignored)
    base = Path(current)
    for name in sorted(files):
        path = base / name
        rel = path.relative_to(root).as_posix()
        data = path.read_bytes()
        items.append({
            'path': rel,
            'bytes': len(data),
            'sha256': hashlib.sha256(data).hexdigest(),
        })
print(json.dumps({'file_count': len(items), 'files': items}, ensure_ascii=False, indent=2))
PY

# 2) Version synchronization gate.
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

# 3) Confirm latest migration has not been silently changed.
if [[ -f backend/alembic/versions/0053_v25_9_16_7_2_64_16_5_4_diff_idempotency.py ]]; then
  record_status PASS ALEMBIC_HEAD_KNOWN "Latest known migration 0053 is present"
else
  record_status FAIL ALEMBIC_HEAD_KNOWN "Expected latest migration 0053 is missing"
fi
find backend/alembic/versions -maxdepth 1 -type f -name '0054_*.py' -o -name '0055_*.py' 2>/dev/null | sort > "$OUT_DIR/newer-migrations.txt" || true
if [[ -s "$OUT_DIR/newer-migrations.txt" ]]; then
  record_status WARN ALEMBIC_NEWER_FOUND "Newer migration files exist; verify down_revision chain"
else
  record_status PASS ALEMBIC_NO_UNEXPECTED_NEWER "No migration newer than 0053 detected"
fi

# 4) UI wording policy guard: source code must not display hard violation wording.
BANNED_UI_PATTERN='gian lận|cheating|vi phạm chắc chắn|treo máy chắc chắn|không học thật'
if grep -RInE "$BANNED_UI_PATTERN" frontend/app frontend/components frontend/lib backend/app \
    --exclude-dir='__pycache__' --exclude='*.pyc' --exclude='test_*' > "$OUT_DIR/banned-wording-source.txt"; then
  record_status FAIL BANNED_WORDING "Hard violation wording found in source code"
else
  record_status PASS BANNED_WORDING "No hard violation wording found in source code"
fi

# 5) Dangerous data-destroy command guard in executable scripts.
# Ignore apt/docker image layer cleanup and this script's own regex definition.
if grep -RInE 'docker compose .*down +-v|rm +-rf +/|DROP DATABASE|TRUNCATE TABLE' scripts backend frontend \
    --exclude-dir='node_modules' --exclude-dir='__pycache__' \
  | grep -Ev 'claude-code-review-pack\.sh|backend/app/tests/|rm -rf /var/lib/apt/lists/\*|rm -rf /wheels' > "$OUT_DIR/dangerous-commands.txt"; then
  record_status WARN DANGEROUS_COMMANDS "Potentially destructive commands found; reviewer should inspect"
else
  record_status PASS DANGEROUS_COMMANDS "No obvious destructive commands found in executable code/scripts"
fi

# 6) Request-path raw tracking.log guard. Routes should use materialized services, not raw log scans.
# Mere comments or path validation for the explicit ingest endpoint are recorded as evidence but not a warning.
grep -RInE 'tracking\.log|OPENEDX_TRACKING_LOG_PATH|TrackingLogReader|tracking_log_reader' backend/app/api/routes > "$OUT_DIR/routes-raw-trackinglog.txt" || true
if grep -RInE 'TrackingLogReader\(|tracking_log_reader\.|open\(.+tracking|read_text\(.+tracking' backend/app/api/routes > "$OUT_DIR/routes-raw-trackinglog-danger.txt"; then
  record_status WARN ROUTE_RAW_TRACKING_LOG_REFERENCE "Potential raw tracking.log scan in API route; inspect routes-raw-trackinglog-danger.txt"
else
  record_status PASS ROUTE_RAW_TRACKING_LOG_REFERENCE "No direct raw tracking.log scanner detected in API route files"
fi

# 7) Syntax compilation for backend source. Does not require DB driver.
if python -m compileall -q backend/app > "$OUT_DIR/py_compile.log" 2>&1; then
  record_status PASS PY_COMPILE "python -m compileall backend/app passed"
else
  record_status FAIL PY_COMPILE "python -m compileall backend/app failed; see py_compile.log"
fi

# 8) Shell syntax for release scripts.
if bash -n scripts/analytics-uat-evidence-pack.sh && bash -n scripts/analytics-uat-acceptance.sh && bash -n scripts/claude-code-review-pack.sh && bash -n scripts/uat-build-gate.sh && bash -n scripts/frontend-build-verify.sh && bash -n scripts/uat-runtime-verify.sh && bash -n scripts/performance-readiness-report.sh && bash -n scripts/query-hotspot-report.sh && bash -n scripts/maintainability-contract-report.sh && bash -n scripts/security-readiness-report.sh && bash -n scripts/security-attack-simulation-report.sh && bash -n scripts/production-security-closure-report.sh && bash -n scripts/performance-worker-reliability-report.sh && bash -n scripts/frontend-runtime-contracts-report.sh && bash -n scripts/ci-e2e-container-hardening-report.sh && bash -n scripts/ci-backend-tests.sh && bash -n scripts/pilot-release-candidate-report.sh && bash -n scripts/pilot-operations-runbook.sh && bash -n scripts/production-pilot-final-gate.sh && bash -n scripts/load-test-hot-endpoints.sh && bash -n scripts/rollback-drill-verify.sh && bash -n scripts/openedx-publish-verify.sh && bash -n scripts/production-pilot-final-gate.sh; then
  record_status PASS SHELL_SYNTAX "release helper scripts pass bash -n"
else
  record_status FAIL SHELL_SYNTAX "one or more release helper scripts fail bash -n"
fi


# 8b) Enterprise navigation/DataTable UX foundation contract.
UX_FOUNDATION_FILES=(
  "frontend/components/navigation/Breadcrumbs.tsx"
  "frontend/components/table/EnterpriseDataTable.tsx"
  "frontend/components/table/TableStates.tsx"
  "frontend/hooks/useUrlTableState.ts"
  "frontend/styles/enterprise-ui.css"
)
ux_missing=0
for f in "${UX_FOUNDATION_FILES[@]}"; do
  if [[ ! -f "$f" ]]; then
    record_status FAIL UX_FOUNDATION_MODULE_MISSING "$f is missing"
    ux_missing=$((ux_missing+1))
  fi
done
if [[ "$ux_missing" == "0" ]]; then
  record_status PASS UX_FOUNDATION_MODULES "Enterprise navigation/DataTable modules are present"
fi
if grep -q "label: 'Ngân hàng đề'" frontend/components/layout/AppShell.tsx   && grep -q '<EnterpriseDataTable' frontend/app/bank/_components/pages/DepartmentsPage.tsx   && grep -q 'useUrlTableState' frontend/app/bank/_components/pages/DepartmentsPage.tsx; then
  record_status PASS BANK_HIERARCHY_UX_CONTRACT "Five-level Bank hierarchy and first EnterpriseDataTable migration are present"
else
  record_status FAIL BANK_HIERARCHY_UX_CONTRACT "Bank hierarchy/DataTable foundation contract is incomplete"
fi

# 8c) Bank workflow UX completion contract.
BANK_WORKFLOW_FILES=(
  "backend/app/services/question_bank/import_export.py"
  "frontend/hooks/useBankQuestionTableState.ts"
  "frontend/app/bank/_components/BankQuestionEnterpriseTable.tsx"
  "frontend/app/bank/_components/BankQuestionImportModal.tsx"
)
bank_ux_missing=0
for f in "${BANK_WORKFLOW_FILES[@]}"; do
  if [[ ! -f "$f" ]]; then
    record_status FAIL BANK_WORKFLOW_MODULE_MISSING "$f is missing"
    bank_ux_missing=$((bank_ux_missing+1))
  fi
done
if [[ "$bank_ux_missing" == "0" ]] \
  && grep -q "questions/import-preview" backend/app/api/routes/question_bank_v2.py \
  && grep -q "questions/import-errors/{preview_token}.xlsx" backend/app/api/routes/question_bank_v2.py \
  && grep -q "releases/{release_id}/preview" backend/app/api/routes/question_bank_v2.py \
  && grep -q "Chọn toàn bộ" frontend/app/bank/_components/pages/ChapterWorkspacePage.tsx; then
  record_status PASS BANK_WORKFLOW_UX_CONTRACT "Bank question paging/import/export/batch/preview contracts are present"
else
  record_status FAIL BANK_WORKFLOW_UX_CONTRACT "Bank workflow UX completion contract is incomplete"
fi

# 9) Dependency/build readiness evidence. This pack should tell reviewers whether
# the current runtime was capable of running backend pytest and frontend typecheck.
python - <<'PYDEP' > "$OUT_DIR/runtime-dependency-status.json" 2>&1
import importlib.util, json, shutil
required = ['fastapi', 'sqlalchemy', 'psycopg', 'pytest']
print(json.dumps({
    'python_packages': {name: bool(importlib.util.find_spec(name)) for name in required},
    'npm_available': bool(shutil.which('npm')),
    'docker_available': bool(shutil.which('docker')),
    'frontend_node_modules_present': __import__('pathlib').Path('frontend/node_modules').exists(),
    'frontend_package_lock_present': __import__('pathlib').Path('frontend/package-lock.json').exists(),
}, ensure_ascii=False, indent=2))
PYDEP
if [[ -d frontend/node_modules ]]; then
  record_status PASS FRONTEND_DEPS_PRESENT "frontend/node_modules exists; typecheck/build can run in this runtime"
else
  record_status PASS FRONTEND_TYPECHECK_INSTRUCTIONS "frontend/node_modules missing in artifact runtime; generated UAT typecheck/build instructions"
  cat > "$OUT_DIR/frontend-typecheck-required.txt" <<'TXT'
Run before UAT sign-off:

cd /opt/ai-server
OUT_DIR=/tmp/ai-frontend-build-$(date +%Y%m%d-%H%M%S) \
EXPECTED_VERSION=25.9.16.7.2.64.16.5.7.1.1 \
RUN_NPM_CI=1 \
RUN_FRONTEND_BUILD=1 \
./scripts/frontend-build-verify.sh
TXT
fi

# Production security P0/P1 closure gate.
if ./scripts/production-security-closure-report.sh "$OUT_DIR/production-security-closure" > "$OUT_DIR/production-security-closure.log" 2>&1; then
  record_status PASS PRODUCTION_SECURITY_CLOSURE "Production security P0/P1 source contract passed" "production-security-closure/production-security-closure.json"
else
  record_status FAIL PRODUCTION_SECURITY_CLOSURE "Production security P0/P1 source contract failed" "production-security-closure.log"
fi


# Performance and worker reliability gate.
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

# 10) Optional build gate. Default is off because artifact sandboxes may not include
# node_modules, Docker, .env.production, or PostgreSQL driver. UAT should run it.
if [[ "$INCLUDE_BUILD_GATE" == "1" ]]; then
  if OUT_DIR="$OUT_DIR/uat-build-gate" EXPECTED_VERSION="$EXPECTED_VERSION" STRICT="$STRICT_BUILD_GATE" ./scripts/uat-build-gate.sh > "$OUT_DIR/uat-build-gate.log" 2>&1; then
    record_status PASS UAT_BUILD_GATE "uat-build-gate.sh completed without FAIL status" "uat-build-gate/build-gate-summary.json"
  else
    record_status FAIL UAT_BUILD_GATE "uat-build-gate.sh reported FAIL status" "uat-build-gate.log"
  fi
else
  record_status PASS UAT_BUILD_GATE_INSTRUCTIONS "INCLUDE_BUILD_GATE=0; build gate script is available for UAT execution" ""
fi

# 10b) UAT HTTP/env compatibility hotfix gate.
if ./scripts/uat-http-env-compatibility-report.sh > "$OUT_DIR/uat-http-env-compatibility.log" 2>&1; then
  record_status PASS UAT_HTTP_ENV_COMPATIBILITY "UAT HTTP/env compatibility gate passed"
else
  record_status FAIL UAT_HTTP_ENV_COMPATIBILITY "UAT HTTP/env compatibility gate failed; see uat-http-env-compatibility.log"
fi

# 10c) UAT build/backend health hotfix gate.
if ./scripts/uat-build-backend-health-hotfix-report.sh > "$OUT_DIR/uat-build-backend-health-hotfix.log" 2>&1; then
  record_status PASS UAT_BUILD_BACKEND_HEALTH "UAT frontend build/backend health hotfix gate passed"
else
  record_status FAIL UAT_BUILD_BACKEND_HEALTH "UAT frontend build/backend health hotfix gate failed; see uat-build-backend-health-hotfix.log"
fi

# 11) Summarize APIs and tests for reviewer navigation.
find backend/app/api/routes -maxdepth 1 -type f -name '*.py' | sort > "$OUT_DIR/backend-routes.txt"
find backend/app/tests -maxdepth 1 -type f -name 'test_v25_9_16_7_2_*.py' | sort > "$OUT_DIR/versioned-tests.txt"
find frontend/app frontend/components frontend/lib -type f \( -name '*.tsx' -o -name '*.ts' -o -name '*.css' \) 2>/dev/null | sort > "$OUT_DIR/frontend-source-files.txt"

python - <<'PY' "$OUT_DIR/checks.tsv" "$OUT_DIR/review-summary.json"
import csv, json, sys
checks_path, out_path = sys.argv[1:]
rows = []
with open(checks_path, encoding='utf-8') as fh:
    for level, code, message in csv.reader(fh, delimiter='\t'):
        rows.append({'level': level, 'code': code, 'message': message})
summary = {
    'status': 'FAIL' if any(r['level'] == 'FAIL' for r in rows) else ('WARN' if any(r['level'] == 'WARN' for r in rows) else 'PASS'),
    'failures': sum(r['level'] == 'FAIL' for r in rows),
    'warnings': sum(r['level'] == 'WARN' for r in rows),
    'passes': sum(r['level'] == 'PASS' for r in rows),
    'checks': rows,
}
with open(out_path, 'w', encoding='utf-8') as fh:
    json.dump(summary, fh, ensure_ascii=False, indent=2)
print(json.dumps(summary, ensure_ascii=False, indent=2))
PY

cat > "$OUT_DIR/CLAUDE_REVIEW_BRIEF.md" <<'MD'
# Claude Code Review Brief

Review target: AI Server / Open edX CMS v25.9.16.7.2.64.16.5.7.1.1 — UAT HTTP Environment Compatibility Hotfix.

Static review services to inspect: SecurityReadinessService, SecurityAttackSimulationService, PerformanceReadinessService, QueryHotspotService, ReleaseCandidateService, PilotOperationsService, QuestionBankReleasePublishWorkflowService, QuestionBankQuizCreationWorkflowService, QuestionBankGenerationReviewWorkflowService, AcademicSyncEnrollmentWorkflowService.

This version continues workflow-by-workflow maintainability work after the Teacher Report split. Reviewers should inspect `backend/app/services/academic/ap_sync.py, academic/assignment_external.py`, `backend/app/services/question_bank_service.py`, and `MaintainabilityContractService`, while confirming release/publish, quiz creation, .64 production-pilot-final gate, and all security/performance/RBAC/query gates remain intact.

## Review focus

0. Security readiness: auth mode, demo headers, cookie flags, CORS whitelist, metrics token, connector HMAC, AP/OpenAI secrets, storage/upload/SSRF guards, and destructive cleanup disabled in production.
1. Build gate readiness: version sync, backend syntax, targeted tests when dependencies exist, frontend typecheck/build instructions, and UAT sign-off commands.
2. Security and RBAC: backend scope enforcement, no campus data leakage, safe UAT cleanup guards.
3. Analytics production path: ingest -> orchestrator -> class recalculate -> snapshot -> SLA/evidence panels.
4. Identity: AP RollNumber must be the CMS/Open edX student username; AP username/email must stay aliases only.
5. Bank UX/workflow: compact table UX, visible actions, Quiz/Final test production gate, no text-based status inference.
6. Operational safety: no request-time raw tracking.log scans, no full recalculate every minute, no destructive scripts by default.

## Reviewer guardrails

- Latest Alembic migration should remain `0053_v25_9_16_7_2_64_16_5_4_diff_idempotency.py` unless a later intentional schema change exists.
- UI must not use hard wording such as “gian lận/cheating/vi phạm chắc chắn”.
- Heavy analytics work must be queued as jobs, not executed in HTTP requests.
- Production destructive cleanup must remain disabled unless explicit UAT env and confirm phrase are supplied.
- Frontend status colors should use backend status fields, not keyword matching in Vietnamese messages.

## Generated artifacts

- `review-summary.json`: pass/warn/fail summary of static gates.
- `file-manifest.json`: SHA256 manifest of the artifact.
- `banned-wording-source.txt`: any disallowed wording hits.
- `dangerous-commands.txt`: destructive command candidates, if any.
- `routes-raw-trackinglog.txt`: raw tracking log references in API routes, if any.
- `backend-routes.txt`, `versioned-tests.txt`, `frontend-source-files.txt`: navigation aids.
- `runtime-dependency-status.json`: whether this runtime had pytest/psycopg/npm/docker and frontend dependencies.
- `frontend-typecheck-required.txt`: command to run the .53 frontend build verifier.
- `uat-build-gate/` when `INCLUDE_BUILD_GATE=1`: UAT build/typecheck evidence.
MD

log "Summary: $OUT_DIR/review-summary.json"
if [[ "$failures" -gt 0 ]]; then
  log "Completed with $failures failure(s), $warnings warning(s)."
  exit 1
fi
log "Completed with 0 failures, $warnings warning(s)."

# Preserved gate: GET /api/health/pilot-operations
# Preserved gate: GET /api/health/release-candidate
