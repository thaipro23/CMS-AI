#!/usr/bin/env bash
set -Eeuo pipefail

ROOT_DIR="${ROOT_DIR:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
FRONTEND_DIR="${FRONTEND_DIR:-$ROOT_DIR/frontend}"
OUT_DIR="${OUT_DIR:-$ROOT_DIR/.runtime/frontend-build-verify-$(date +%Y%m%d-%H%M%S)}"
EXPECTED_VERSION="${EXPECTED_VERSION:-25.9.16.7.2.64.16.5.7.1}"
RUN_NPM_CI="${RUN_NPM_CI:-1}"
RUN_FRONTEND_BUILD="${RUN_FRONTEND_BUILD:-1}"
mkdir -p "$OUT_DIR"
cd "$ROOT_DIR"

log() { printf '[frontend-build-verify] %s\n' "$*"; }
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

log "Writing frontend build evidence to $OUT_DIR"

if [[ ! -d "$FRONTEND_DIR" ]]; then
  record_status FAIL FRONTEND_DIR_MISSING "$FRONTEND_DIR is missing"
else
  record_status PASS FRONTEND_DIR_PRESENT "$FRONTEND_DIR exists"
fi

if python - <<'PY' "$FRONTEND_DIR" "$EXPECTED_VERSION" > "$OUT_DIR/frontend-version-metadata.json" 2>&1
import json, sys
from pathlib import Path
frontend = Path(sys.argv[1])
expected = sys.argv[2]
package = json.loads((frontend / 'package.json').read_text(encoding='utf-8'))
lock = json.loads((frontend / 'package-lock.json').read_text(encoding='utf-8'))
dockerfile = (frontend / 'Dockerfile').read_text(encoding='utf-8')
next_config = (frontend / 'next.config.js').read_text(encoding='utf-8')
result = {
    'expected_version': expected,
    'package_json_version': package.get('version'),
    'package_lock_root_version': lock.get('version'),
    'package_lock_package_version': lock.get('packages', {}).get('', {}).get('version'),
    'dockerfile_contains_expected_version': expected in dockerfile,
    'next_output_standalone': "output: 'standalone'" in next_config or 'output: "standalone"' in next_config,
    'scripts': package.get('scripts', {}),
}
result['ok'] = (
    result['package_json_version'] == expected
    and result['package_lock_root_version'] == expected
    and result['package_lock_package_version'] == expected
    and result['dockerfile_contains_expected_version']
    and result['next_output_standalone']
    and 'typecheck' in result['scripts']
    and 'build' in result['scripts']
)
print(json.dumps(result, ensure_ascii=False, indent=2))
raise SystemExit(0 if result['ok'] else 1)
PY
then
  record_status PASS FRONTEND_VERSION_METADATA "package/package-lock/Dockerfile/Next standalone metadata is consistent" "frontend-version-metadata.json"
else
  record_status FAIL FRONTEND_VERSION_METADATA "frontend package-lock/Dockerfile/Next metadata is inconsistent" "frontend-version-metadata.json"
fi

if ! command -v npm >/dev/null 2>&1; then
  record_status FAIL NPM_MISSING "npm is required for frontend UAT build verification"
else
  npm --version > "$OUT_DIR/npm-version.txt" 2>&1 || true
  node --version > "$OUT_DIR/node-version.txt" 2>&1 || true
  record_status PASS NPM_AVAILABLE "npm/node are available" "npm-version.txt"
fi

if command -v npm >/dev/null 2>&1; then
  if [[ ! -d "$FRONTEND_DIR/node_modules" ]]; then
    if [[ "$RUN_NPM_CI" == "1" ]]; then
      run_and_record NPM_CI "frontend npm ci --include=dev" npm-ci.log bash -lc "cd '$FRONTEND_DIR' && npm ci --include=dev --no-audit --no-fund"
    else
      record_status FAIL FRONTEND_DEPS_MISSING "frontend/node_modules missing and RUN_NPM_CI=0" "frontend-version-metadata.json"
    fi
  else
    record_status PASS FRONTEND_DEPS_PRESENT "frontend/node_modules exists"
  fi

  if [[ -d "$FRONTEND_DIR/node_modules" ]]; then
    run_and_record FRONTEND_TYPECHECK "frontend npm run typecheck" frontend-typecheck.log bash -lc "cd '$FRONTEND_DIR' && npm run typecheck"
    if [[ "$RUN_FRONTEND_BUILD" == "1" ]]; then
      run_and_record FRONTEND_BUILD "frontend npm run build" frontend-build.log bash -lc "cd '$FRONTEND_DIR' && npm run build"
      if [[ -f "$FRONTEND_DIR/.next/standalone/server.js" ]]; then
        record_status PASS NEXT_STANDALONE_SERVER "Next standalone server.js exists" ".next/standalone/server.js"
      else
        record_status FAIL NEXT_STANDALONE_SERVER "Next standalone server.js missing after build"
      fi
    else
      record_status WARN FRONTEND_BUILD_SKIPPED "RUN_FRONTEND_BUILD=0; npm run build skipped"
    fi
  fi
fi

python - <<'PY' "$OUT_DIR/checks.tsv" "$OUT_DIR/frontend-build-summary.json" "$OUT_DIR/FRONTEND_BUILD_SUMMARY.md"
import csv, json, sys
checks_path, json_path, md_path = sys.argv[1:]
rows = []
with open(checks_path, encoding='utf-8') as fh:
    for row in csv.reader(fh, delimiter='\t'):
        while len(row) < 4:
            row.append('')
        rows.append({'level': row[0], 'code': row[1], 'message': row[2], 'evidence': row[3]})
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
    fh.write('# Frontend Build Verification Summary\n\n')
    fh.write(f"Status: **{status}**\n\n")
    fh.write('| Level | Code | Message | Evidence |\n|---|---|---|---|\n')
    for r in rows:
        fh.write(f"| {r['level']} | `{r['code']}` | {r['message']} | {r['evidence']} |\n")
print(json.dumps(summary, ensure_ascii=False, indent=2))
PY

status="$(python - <<'PY' "$OUT_DIR/frontend-build-summary.json"
import json, sys
print(json.load(open(sys.argv[1], encoding='utf-8'))['status'])
PY
)"
log "Summary: $OUT_DIR/frontend-build-summary.json"
if [[ "$status" == "FAIL" ]]; then
  exit 1
fi
