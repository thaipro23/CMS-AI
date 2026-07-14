#!/usr/bin/env bash
# v25.9.16.7.2.64.16.5.3 — Production Pilot Final QA + Rollback Drill
set -Eeuo pipefail

API_BASE_URL="${API_BASE_URL:-https://api-ai.cms-test.poly.edu.vn/api}"
TOKEN="${TOKEN:-}"
RELEASE_ID="${RELEASE_ID:-}"
COURSE_ID="${COURSE_ID:-}"
OUT_DIR="${OUT_DIR:-/tmp/ai-openedx-publish-verify-$(date +%Y%m%d-%H%M%S)}"
mkdir -p "$OUT_DIR"

if [[ -z "$TOKEN" ]]; then
  echo "TOKEN is required" >&2
  exit 2
fi

: > "$OUT_DIR/checks.tsv"
record() { printf '%s\t%s\t%s\t%s\n' "$1" "$2" "$3" "${4:-}" >> "$OUT_DIR/checks.tsv"; }

if [[ -n "$RELEASE_ID" ]]; then
  if curl -fsS "$API_BASE_URL/question-bank-v2/releases/$RELEASE_ID/publish-audit" \
    -H "Authorization: Bearer $TOKEN" -H 'Accept: application/json' \
    -o "$OUT_DIR/release-publish-audit.json"; then
    record PASS RELEASE_PUBLISH_AUDIT "release publish audit fetched" release-publish-audit.json
  else
    record FAIL RELEASE_PUBLISH_AUDIT "release publish audit failed" release-publish-audit.json
  fi
else
  record WARN RELEASE_ID_MISSING "RELEASE_ID not set; skip release publish audit" ""
fi

if [[ -n "$COURSE_ID" ]]; then
  record WARN COURSE_VERIFY_MANUAL "COURSE_ID set; verify quiz/final test in Open edX UI and course outline manually" ""
else
  record WARN COURSE_ID_MISSING "COURSE_ID not set; skip course quiz/final test manual checklist" ""
fi

python - <<'PY' "$OUT_DIR/checks.tsv" "$OUT_DIR/openedx-publish-verify-summary.json" "$OUT_DIR/OPENEDX_PUBLISH_VERIFY_SUMMARY.md"
import csv, json, sys
checks_path, json_path, md_path = sys.argv[1:]
rows=[]
with open(checks_path, encoding='utf-8') as fh:
    for row in csv.reader(fh, delimiter='\t'):
        while len(row) < 4: row.append('')
        rows.append({'level': row[0], 'code': row[1], 'message': row[2], 'evidence': row[3]})
status='FAIL' if any(r['level']=='FAIL' for r in rows) else ('WARN' if any(r['level']=='WARN' for r in rows) else 'PASS')
json.dump({'status': status, 'checks': rows}, open(json_path, 'w', encoding='utf-8'), ensure_ascii=False, indent=2)
with open(md_path, 'w', encoding='utf-8') as fh:
    fh.write('# Open edX Publish Verify Summary\n\n')
    fh.write(f"Status: **{status}**\n\n")
    fh.write('| Level | Code | Message | Evidence |\n|---|---|---|---|\n')
    for row in rows:
        fh.write(f"| {row['level']} | `{row['code']}` | {row['message']} | {row['evidence']} |\n")
    fh.write('\n## Manual checks\n\n')
    fh.write('- Open the Open edX course outline and verify quiz/final test visibility.\n')
    fh.write('- Verify Library/Problem components exist for the published release.\n')
    fh.write('- Verify rollback plan for created quiz/final test instances if pilot scope changes.\n')
print(md_path)
PY

echo "Open edX publish verify artifacts written to $OUT_DIR"
