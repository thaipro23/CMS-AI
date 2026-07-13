#!/usr/bin/env bash
set -Eeuo pipefail

API_BASE_URL="${API_BASE_URL:-https://api-ai.cms-test.poly.edu.vn/api}"
TOKEN="${TOKEN:-}"
EXPECTED_VERSION="${EXPECTED_VERSION:-25.9.16.7.2.64.12}"
CLASS_ID="${CLASS_ID:-}"
COURSE_ID="${COURSE_ID:-}"
BRANCH="${BRANCH:-poly}"
CAMPUS="${CAMPUS:-}"
SAMPLE_LIMIT="${SAMPLE_LIMIT:-5}"
OUT_DIR="${OUT_DIR:-/tmp/ai-pilot-operations-runbook-$(date +%Y%m%d-%H%M%S)}"
mkdir -p "$OUT_DIR"

if [[ -z "$TOKEN" ]]; then
  echo "TOKEN is required" >&2
  exit 2
fi

query="sample_limit=$SAMPLE_LIMIT"
if [[ -n "$CLASS_ID" ]]; then query="$query&class_id=$CLASS_ID"; fi
if [[ -n "$COURSE_ID" ]]; then query="$query&course_id=$COURSE_ID"; fi
if [[ -n "$BRANCH" ]]; then query="$query&branch=$BRANCH"; fi
if [[ -n "$CAMPUS" ]]; then query="$query&campus=$CAMPUS"; fi

curl -fsS "$API_BASE_URL/health/pilot-operations?$query" \
  -H "Authorization: Bearer $TOKEN" \
  -H 'Accept: application/json' \
  -o "$OUT_DIR/pilot-operations.json"

curl -fsS "$API_BASE_URL/health/release-candidate?$query" \
  -H "Authorization: Bearer $TOKEN" \
  -H 'Accept: application/json' \
  -o "$OUT_DIR/release-candidate.json" || true

python - <<'PY' "$OUT_DIR/pilot-operations.json" "$OUT_DIR/PILOT_OPERATIONS_RUNBOOK.md" "$EXPECTED_VERSION"
import json, sys
src, dst, expected = sys.argv[1:]
data = json.load(open(src, encoding='utf-8'))
with open(dst, 'w', encoding='utf-8') as fh:
    fh.write('# Pilot Operations Runbook\n\n')
    fh.write(f"Status: **{data.get('status')}** · Decision: **{data.get('decision')}**\n\n")
    fh.write(f"Version: `{data.get('version')}` · Expected: `{expected}`\n\n")
    fh.write(f"Ready pilot: **{data.get('ready_for_pilot')}** · Ready broad production: **{data.get('ready_for_broad_production')}**\n\n")
    fh.write(f"Blockers: **{data.get('blocker_count', 0)}** · Warnings: **{data.get('warning_count', 0)}**\n\n")
    fh.write(f"Summary: {data.get('summary_label') or ''}\n\n")
    fh.write('## Release Candidate Summary\n\n')
    rc = data.get('release_candidate_summary') or {}
    fh.write('| Status | Go/No-Go | Ready Pilot | Ready Broad |\n')
    fh.write('|---|---|---|---|\n')
    fh.write(f"| {rc.get('status')} | {rc.get('go_no_go')} | {rc.get('ready_for_pilot')} | {rc.get('ready_for_broad_production')} |\n\n")
    fh.write('## Pilot Phases\n\n')
    for phase in data.get('phases') or []:
        fh.write(f"### {phase.get('title') or phase.get('key')} — {phase.get('status')}\n")
        for check in phase.get('checks') or []:
            fh.write(f'- {check}\n')
        fh.write('\n')
    fh.write('## Monitoring Cadence\n\n')
    fh.write('| Window | Frequency | Check |\n|---|---|---|\n')
    for item in data.get('monitoring_cadence') or []:
        fh.write(f"| {item.get('window')} | {item.get('frequency')} | {item.get('check')} |\n")
    fh.write('\n## Rollback Triggers\n\n')
    fh.write('| Severity | Code | Condition | Action |\n|---|---|---|---|\n')
    for item in data.get('rollback_triggers') or []:
        fh.write(f"| {item.get('severity')} | `{item.get('code')}` | {item.get('condition') or ''} | {item.get('action') or ''} |\n")
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

echo "Pilot operations runbook written to $OUT_DIR"
