#!/usr/bin/env bash
set -Eeuo pipefail

API_BASE_URL="${API_BASE_URL:-https://api-ai.cms-test.poly.edu.vn/api}"
TOKEN="${TOKEN:-}"
EXPECTED_VERSION="${EXPECTED_VERSION:-25.9.16.7.2.64.16.5.6}"
CLASS_ID="${CLASS_ID:-}"
COURSE_ID="${COURSE_ID:-}"
BRANCH="${BRANCH:-poly}"
CAMPUS="${CAMPUS:-}"
SAMPLE_LIMIT="${SAMPLE_LIMIT:-5}"
INCLUDE_STATIC_SCANS="${INCLUDE_STATIC_SCANS:-true}"
OUT_DIR="${OUT_DIR:-/tmp/ai-production-pilot-final-$(date +%Y%m%d-%H%M%S)}"
mkdir -p "$OUT_DIR"

if [[ -z "$TOKEN" ]]; then
  echo "TOKEN is required" >&2
  exit 2
fi

query="sample_limit=$SAMPLE_LIMIT&include_static_scans=$INCLUDE_STATIC_SCANS"
if [[ -n "$CLASS_ID" ]]; then query="$query&class_id=$CLASS_ID"; fi
if [[ -n "$COURSE_ID" ]]; then query="$query&course_id=$COURSE_ID"; fi
if [[ -n "$BRANCH" ]]; then query="$query&branch=$BRANCH"; fi
if [[ -n "$CAMPUS" ]]; then query="$query&campus=$CAMPUS"; fi

fetch_json() {
  local path="$1" out="$2"
  curl -fsS "$API_BASE_URL/$path" \
    -H "Authorization: Bearer $TOKEN" \
    -H 'Accept: application/json' \
    -o "$OUT_DIR/$out"
}

fetch_json "health/production-pilot-final?$query" production-pilot-final.json
fetch_json "health/pilot-operations?$query" pilot-operations.json || true
fetch_json "health/release-candidate?$query" release-candidate.json || true
fetch_json "health/security-readiness" security-readiness.json || true
fetch_json "health/performance-readiness" performance-readiness.json || true
fetch_json "health/maintainability-contract" maintainability-contract.json || true
fetch_json "health/query-hotspots?max_items=120" query-hotspots.json || true

python - <<'PY' "$OUT_DIR/production-pilot-final.json" "$OUT_DIR/PRODUCTION_PILOT_FINAL_SUMMARY.md" "$EXPECTED_VERSION"
import json, sys
src, dst, expected = sys.argv[1:]
data = json.load(open(src, encoding='utf-8'))
with open(dst, 'w', encoding='utf-8') as fh:
    fh.write('# Production Pilot Final Gate Summary\n\n')
    fh.write(f"Status: **{data.get('status')}** · Decision: **{data.get('decision')}**\n\n")
    fh.write(f"Version: `{data.get('version')}` · Expected: `{expected}`\n\n")
    fh.write(f"Ready pilot: **{data.get('ready_for_pilot')}** · Ready broad production: **{data.get('ready_for_broad_production')}**\n\n")
    fh.write(f"Blockers: **{data.get('blocker_count', 0)}** · Warnings: **{data.get('warning_count', 0)}**\n\n")
    fh.write(f"Summary: {data.get('summary_label') or ''}\n\n")
    fh.write('## Gates\n\n')
    fh.write('| Gate | Status | Source | Blockers | Warnings | Endpoint |\n')
    fh.write('|---|---|---|---:|---:|---|\n')
    for gate in data.get('gates') or []:
        fh.write(f"| {gate.get('title')} | {gate.get('status')} | {gate.get('source_status') or ''} | {gate.get('blocker_count', 0)} | {gate.get('warning_count', 0)} | `{gate.get('report_endpoint')}` |\n")
    fh.write('\n## Final Checks\n\n')
    fh.write('| Severity | Code | OK | Message | Action |\n')
    fh.write('|---|---|---|---|---|\n')
    for item in data.get('final_checks') or []:
        fh.write(f"| {item.get('severity')} | `{item.get('code')}` | {item.get('ok')} | {item.get('message') or ''} | {item.get('action') or ''} |\n")
    fh.write('\n## Load Test Plan\n\n')
    fh.write('| Endpoint | Target p95 ms | Purpose |\n')
    fh.write('|---|---:|---|\n')
    for item in data.get('load_test_plan') or []:
        fh.write(f"| `{item.get('endpoint')}` | {item.get('target_p95_ms')} | {item.get('purpose') or ''} |\n")
    fh.write('\n## Evidence Required\n\n')
    for item in data.get('evidence_required') or []:
        fh.write(f'- {item}\n')
    fh.write('\n## Sign-off\n\n')
    signoff = data.get('signoff') or {}
    fh.write(f"Can sign off pilot: **{signoff.get('can_signoff_pilot')}**  \n")
    fh.write(f"Can sign off broad production: **{signoff.get('can_signoff_broad_production')}**  \n")
    fh.write(f"Required roles: {', '.join(signoff.get('required_roles') or [])}\n\n")
    fh.write('## Next Actions\n\n')
    for action in data.get('next_actions') or []:
        fh.write(f'- {action}\n')
    fh.write('\n## Read-only Guarantees\n\n')
    for item in data.get('read_only_guarantees') or []:
        fh.write(f'- {item}\n')
print(dst)
PY

echo "Production pilot final gate artifacts written to $OUT_DIR"
