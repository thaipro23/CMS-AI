#!/usr/bin/env bash
set -Eeuo pipefail

ROOT_DIR="${ROOT_DIR:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
OUT_DIR="${OUT_DIR:-$ROOT_DIR/.runtime/uat-runtime-verify-$(date +%Y%m%d-%H%M%S)}"
EXPECTED_VERSION="${EXPECTED_VERSION:-25.9.16.7.2.64.12}"
API_BASE_URL="${API_BASE_URL:-https://api-ai.cms-test.poly.edu.vn/api}"
FRONTEND_URL="${FRONTEND_URL:-https://ai.cms-test.poly.edu.vn}"
TOKEN="${TOKEN:-}"
CLASS_ID="${CLASS_ID:-}"
CURL_TIMEOUT_SECONDS="${CURL_TIMEOUT_SECONDS:-20}"
mkdir -p "$OUT_DIR"
cd "$ROOT_DIR"

log() { printf '[uat-runtime-verify] %s\n' "$*"; }
: > "$OUT_DIR/checks.tsv"

record_status() {
  local level="$1" code="$2" message="$3" evidence="${4:-}"
  printf '%s\t%s\t%s\t%s\n' "$level" "$code" "$message" "$evidence" >> "$OUT_DIR/checks.tsv"
}

auth_args=()
if [[ -n "$TOKEN" ]]; then
  auth_args=(-H "Authorization: Bearer $TOKEN")
fi

curl_json() {
  local code="$1" path="$2" outfile="$3" auth_required="${4:-0}"
  local url="${API_BASE_URL%/}${path}"
  if [[ "$auth_required" == "1" && -z "$TOKEN" ]]; then
    record_status WARN "${code}_SKIPPED" "$path requires TOKEN" ""
    return 0
  fi
  log "GET $url"
  if curl -fsS --max-time "$CURL_TIMEOUT_SECONDS" "${auth_args[@]}" "$url" > "$OUT_DIR/$outfile" 2> "$OUT_DIR/${outfile}.curl.log"; then
    record_status PASS "$code" "GET $path succeeded" "$outfile"
  else
    record_status FAIL "$code" "GET $path failed" "${outfile}.curl.log"
  fi
}

log "Writing UAT runtime verification evidence to $OUT_DIR"

curl_json API_HEALTH_BUILD /health/build build.json 0
curl_json API_HEALTH /health health.json 0
curl_json API_READINESS /health/readiness readiness.json 1
curl_json PERFORMANCE_READINESS /health/performance-readiness performance-readiness.json 1
curl_json QUERY_HOTSPOTS /health/query-hotspots query-hotspots.json 1
curl_json MAINTAINABILITY_CONTRACT /health/maintainability-contract maintainability-contract.json 1
curl_json SECURITY_READINESS /health/security-readiness security-readiness.json 1
curl_json SECURITY_ATTACK_SIMULATION /health/security-attack-simulation security-attack-simulation.json 1
curl_json RELEASE_CANDIDATE /health/release-candidate release-candidate.json 1
curl_json PILOT_OPERATIONS /health/pilot-operations pilot-operations.json 1
curl_json PRODUCTION_PILOT_FINAL /health/production-pilot-final production-pilot-final.json 1
curl_json RBAC_SCOPE_AUDIT /rbac/scope-audit rbac-scope-audit.json 1
curl_json ANALYTICS_SLA /analytics/ops/sla analytics-sla.json 1
curl_json PILOT_ACCEPTANCE /analytics/ops/pilot-acceptance pilot-acceptance.json 1
curl_json EVIDENCE_PACK /analytics/ops/evidence-pack evidence-pack.json 1
if [[ -n "$CLASS_ID" ]]; then
  curl_json CLASS_DOCTOR "/analytics/classes/$CLASS_ID/doctor" class-doctor.json 1
else
  record_status WARN CLASS_DOCTOR_SKIPPED "CLASS_ID not supplied; class doctor runtime probe skipped" ""
fi

log "GET $FRONTEND_URL"
if curl -fsSL --max-time "$CURL_TIMEOUT_SECONDS" "$FRONTEND_URL" > "$OUT_DIR/frontend.html" 2> "$OUT_DIR/frontend.curl.log"; then
  record_status PASS FRONTEND_HTTP "Frontend URL responded" "frontend.html"
  if grep -q "$EXPECTED_VERSION" "$OUT_DIR/frontend.html"; then
    record_status PASS FRONTEND_VERSION_MARKER "Frontend HTML contains expected version $EXPECTED_VERSION" "frontend.html"
  else
    record_status WARN FRONTEND_VERSION_MARKER "Frontend HTML did not expose expected version marker; check AppShell after login" "frontend.html"
  fi
else
  record_status FAIL FRONTEND_HTTP "Frontend URL failed" "frontend.curl.log"
fi

python - <<'PY' "$OUT_DIR" "$EXPECTED_VERSION" > "$OUT_DIR/runtime-json-analysis.json" 2>&1
import json, sys
from pathlib import Path
out = Path(sys.argv[1])
expected = sys.argv[2]
analysis = {'expected_version': expected, 'files': {}, 'issues': []}
for name in ['build.json', 'readiness.json', 'performance-readiness.json', 'query-hotspots.json', 'security-readiness.json', 'security-attack-simulation.json', 'release-candidate.json', 'pilot-operations.json', 'production-pilot-final.json', 'analytics-sla.json', 'pilot-acceptance.json', 'evidence-pack.json']:
    path = out / name
    if not path.exists() or not path.read_text(encoding='utf-8', errors='ignore').strip():
        continue
    try:
        payload = json.loads(path.read_text(encoding='utf-8'))
    except Exception as exc:
        analysis['issues'].append({'file': name, 'issue': f'invalid_json:{exc}'})
        continue
    entry = {}
    for key in ['version', 'app_version', 'status', 'stage_status', 'sla_status', 'pilot_status', 'evidence_status', 'ready_for_pilot', 'ready_for_broad_production']:
        if key in payload:
            entry[key] = payload[key]
    # Nested common shapes.
    if isinstance(payload.get('build'), dict):
        entry['build_version'] = payload['build'].get('version') or payload['build'].get('app_version')
    analysis['files'][name] = entry
    versions = [v for k, v in entry.items() if 'version' in k and isinstance(v, str)]
    if versions and expected not in versions:
        analysis['issues'].append({'file': name, 'issue': 'version_mismatch', 'versions': versions})
print(json.dumps(analysis, ensure_ascii=False, indent=2))
PY
if grep -q 'version_mismatch\|invalid_json' "$OUT_DIR/runtime-json-analysis.json"; then
  record_status WARN RUNTIME_JSON_ANALYSIS "Runtime JSON analysis found version/JSON issue" "runtime-json-analysis.json"
else
  record_status PASS RUNTIME_JSON_ANALYSIS "Runtime JSON analysis completed" "runtime-json-analysis.json"
fi

python - <<'PY' "$OUT_DIR/checks.tsv" "$OUT_DIR/runtime-verify-summary.json" "$OUT_DIR/RUNTIME_VERIFY_SUMMARY.md"
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
    fh.write('# UAT Runtime Verification Summary\n\n')
    fh.write(f"Status: **{status}**\n\n")
    fh.write('| Level | Code | Message | Evidence |\n|---|---|---|---|\n')
    for r in rows:
        fh.write(f"| {r['level']} | `{r['code']}` | {r['message']} | {r['evidence']} |\n")
print(json.dumps(summary, ensure_ascii=False, indent=2))
PY

status="$(python - <<'PY' "$OUT_DIR/runtime-verify-summary.json"
import json, sys
print(json.load(open(sys.argv[1], encoding='utf-8'))['status'])
PY
)"
log "Summary: $OUT_DIR/runtime-verify-summary.json"
if [[ "$status" == "FAIL" ]]; then
  exit 1
fi
