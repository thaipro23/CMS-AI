#!/usr/bin/env bash
set -euo pipefail

API_BASE_URL="${API_BASE_URL:-https://api-ai.cms-test.poly.edu.vn/api}"
TOKEN="${TOKEN:-}"
OUT_DIR="${OUT_DIR:-/tmp/ai-analytics-course-class-mapping-$(date +%Y%m%d-%H%M%S)}"
BRANCH="${BRANCH:-poly}"
CAMPUS="${CAMPUS:-}"
TERM_ID="${TERM_ID:-}"
SUBJECT_ID="${SUBJECT_ID:-}"
CLASS_ID="${CLASS_ID:-}"
COURSE_ID="${COURSE_ID:-}"
LIMIT="${LIMIT:-100}"

mkdir -p "$OUT_DIR"
if [[ -z "$TOKEN" ]]; then
  echo "TOKEN is required" >&2
  exit 2
fi

query="limit=${LIMIT}"
[[ -n "$BRANCH" ]] && query+="&branch=${BRANCH}"
[[ -n "$CAMPUS" ]] && query+="&campus=${CAMPUS}"
[[ -n "$TERM_ID" ]] && query+="&term_id=${TERM_ID}"
[[ -n "$SUBJECT_ID" ]] && query+="&subject_id=${SUBJECT_ID}"
[[ -n "$CLASS_ID" ]] && query+="&class_id=${CLASS_ID}"
[[ -n "$COURSE_ID" ]] && query+="&course_id=${COURSE_ID}"

curl_json() {
  local url="$1"
  local output="$2"
  curl -fsS "$url" -H "Authorization: Bearer ${TOKEN}" -H 'Accept: application/json' -o "$output"
}

report_json="$OUT_DIR/analytics-course-class-mapping.json"
curl_json "${API_BASE_URL%/}/analytics/ops/course-class-mapping?${query}" "$report_json"

python3 - "$report_json" "$OUT_DIR/COURSE_CLASS_MAPPING_SUMMARY.md" <<'PY'
import json, sys
src, dst = sys.argv[1], sys.argv[2]
data = json.load(open(src, encoding='utf-8'))
lines = []
lines.append('# Analytics Course/Class Mapping Reliability')
lines.append('')
lines.append(f"- Status: `{data.get('status')}`")
lines.append(f"- Summary: {data.get('summary_label') or ''}")
lines.append(f"- Blockers: {data.get('blocker_count', 0)}")
lines.append(f"- Warnings: {data.get('warning_count', 0)}")
lines.append(f"- Scope classes: {data.get('total_scope_classes', 0)}")
lines.append(f"- Returned classes: {data.get('returned_classes', 0)}")
lines.append(f"- Courses with events but no class mapping: {data.get('courses_with_events_without_class_mapping_count', 0)}")
lines.append('')
lines.append('## Counts')
for k, v in sorted((data.get('counts') or {}).items()):
    lines.append(f"- {k}: {v}")
lines.append('')
if data.get('next_actions'):
    lines.append('## Next actions')
    for action in data.get('next_actions') or []:
        lines.append(f"- {action}")
    lines.append('')
items = data.get('items') or []
if items:
    lines.append('## Sample classes')
    for item in items[:20]:
        lines.append(f"- `{item.get('class_code') or item.get('class_id')}` · {item.get('reliability_status')} · course={item.get('resolved_course_id') or 'N/A'} · snapshots={item.get('snapshot_count', 0)}/{item.get('roster_count', 0)} · action={item.get('recommended_action') or ''}")
    lines.append('')
orphans = data.get('courses_with_events_without_class_mapping') or []
if orphans:
    lines.append('## Courses with events but no class mapping')
    for item in orphans[:20]:
        lines.append(f"- `{item.get('course_id')}` · events={item.get('event_count', 0)} · users={item.get('user_count', 0)} · latest={item.get('latest_event_at') or 'N/A'}")
    lines.append('')
lines.append('## Read-only guarantees')
for item in data.get('read_only_guarantees') or []:
    lines.append(f"- {item}")
open(dst, 'w', encoding='utf-8').write('\n'.join(lines) + '\n')
PY

echo "Wrote: $report_json"
echo "Wrote: $OUT_DIR/COURSE_CLASS_MAPPING_SUMMARY.md"
