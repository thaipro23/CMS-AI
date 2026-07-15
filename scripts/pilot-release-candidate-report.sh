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
OUT_DIR="${OUT_DIR:-/tmp/ai-pilot-release-candidate-$(date +%Y%m%d-%H%M%S)}"
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

curl -fsS "$API_BASE_URL/health/release-candidate?$query" \
  -H "Authorization: Bearer $TOKEN" \
  -H 'Accept: application/json' \
  -o "$OUT_DIR/release-candidate.json"

# Keep the underlying gate artifacts beside the RC summary for reviewers.
for item in \
  "health/readiness:readiness.json" \
  "health/security-readiness:security-readiness.json" \
  "health/performance-readiness:performance-readiness.json" \
  "analytics/ops/evidence-pack?$query:evidence-pack.json"; do
  path="${item%%:*}"
  file="${item##*:}"
  curl -fsS "$API_BASE_URL/$path" \
    -H "Authorization: Bearer $TOKEN" \
    -H 'Accept: application/json' \
    -o "$OUT_DIR/$file" || true
done

python - <<'PY' "$OUT_DIR/release-candidate.json" "$OUT_DIR/PILOT_RELEASE_CANDIDATE_SUMMARY.md" "$EXPECTED_VERSION"
import json, sys
src, dst, expected = sys.argv[1:]
data = json.load(open(src, encoding='utf-8'))
with open(dst, 'w', encoding='utf-8') as fh:
    fh.write('# Pilot Release Candidate Summary\n\n')
    fh.write(f"Status: **{data.get('status')}** · Go/No-Go: **{data.get('go_no_go')}**\n\n")
    fh.write(f"Version: `{data.get('version')}` · Expected: `{expected}`\n\n")
    fh.write(f"Ready for pilot: **{data.get('ready_for_pilot')}** · Ready broad production: **{data.get('ready_for_broad_production')}**\n\n")
    fh.write(f"Blockers: **{data.get('blocker_count', 0)}** · Warnings: **{data.get('warning_count', 0)}**\n\n")
    fh.write(f"Summary: {data.get('summary_label') or ''}\n\n")
    fh.write('## Gates\n\n')
    fh.write('| Gate | Status | Blockers | Warnings | Endpoint | Message |\n')
    fh.write('|---|---|---:|---:|---|---|\n')
    for gate in data.get('gates') or []:
        fh.write(f"| {gate.get('title')} | {gate.get('status')} | {gate.get('blocker_count', 0)} | {gate.get('warning_count', 0)} | `{gate.get('report_endpoint')}` | {gate.get('message') or ''} |\n")
    fh.write('\n## Blockers\n\n')
    blockers = data.get('blockers') or []
    if not blockers:
        fh.write('Không có blocker.\n')
    else:
        fh.write('| Source | Code | Message | Action |\n|---|---|---|---|\n')
        for item in blockers:
            fh.write(f"| {item.get('source')} | `{item.get('code')}` | {item.get('message') or ''} | {item.get('action') or ''} |\n")
    fh.write('\n## Warnings\n\n')
    warnings = data.get('warnings') or []
    if not warnings:
        fh.write('Không có cảnh báo.\n')
    else:
        fh.write('| Source | Code | Message | Action |\n|---|---|---|---|\n')
        for item in warnings[:20]:
            fh.write(f"| {item.get('source')} | `{item.get('code')}` | {item.get('message') or ''} | {item.get('action') or ''} |\n")
    fh.write('\n## Next actions\n\n')
    for action in data.get('next_actions') or []:
        fh.write(f'- {action}\n')
    fh.write('\n## Read-only guarantees\n\n')
    for item in data.get('read_only_guarantees') or []:
        fh.write(f'- {item}\n')
print(dst)
PY

echo "Pilot release candidate evidence written to $OUT_DIR"
