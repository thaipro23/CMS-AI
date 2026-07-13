#!/usr/bin/env bash
set -euo pipefail

API_BASE_URL="${API_BASE_URL:-${BACKEND_URL:-http://localhost:8000/api}}"
TOKEN="${TOKEN:-}"
CLASS_ID="${CLASS_ID:-}"
COURSE_ID="${COURSE_ID:-}"
CAMPUS="${CAMPUS:-}"
BRANCH="${BRANCH:-poly}"
SAMPLE_LIMIT="${SAMPLE_LIMIT:-5}"
OUT_DIR="${OUT_DIR:-./uat-evidence-$(date +%Y%m%d-%H%M%S)}"

if [[ -z "$TOKEN" ]]; then
  echo "ERROR: set TOKEN=<Bearer token without the Bearer prefix>" >&2
  exit 2
fi

AUTH_HEADER="Authorization: Bearer ${TOKEN}"
mkdir -p "$OUT_DIR"
# Expected evidence files: build.json readiness.json rbac-scope-audit.json
# analytics-sla.json pilot-acceptance.json evidence-pack.json class-doctor.json
# plus EVIDENCE_SUMMARY.md.

urlencode() {
  python -c 'import sys, urllib.parse; print(urllib.parse.quote(sys.argv[1]))' "$1"
}

call_to_file() {
  local name="$1"
  local url="$2"
  local file="$OUT_DIR/${name}.json"
  echo "== ${name}: ${url}" >&2
  curl -fsS "$url" -H "$AUTH_HEADER" -o "$file"
  python -m json.tool "$file" > "$file.tmp" && mv "$file.tmp" "$file"
}

query="sample_limit=${SAMPLE_LIMIT}"
if [[ -n "$CLASS_ID" ]]; then query="${query}&class_id=$(urlencode "$CLASS_ID")"; fi
if [[ -n "$COURSE_ID" ]]; then query="${query}&course_id=$(urlencode "$COURSE_ID")"; fi
if [[ -n "$CAMPUS" ]]; then query="${query}&campus=$(urlencode "$CAMPUS")"; fi
if [[ -n "$BRANCH" ]]; then query="${query}&branch=$(urlencode "$BRANCH")"; fi

call_to_file "build" "${API_BASE_URL}/health/build"
call_to_file "readiness" "${API_BASE_URL}/health/readiness"
call_to_file "rbac-scope-audit" "${API_BASE_URL}/rbac/scope-audit"
call_to_file "analytics-sla" "${API_BASE_URL}/analytics/ops/sla?limit=20"
call_to_file "pilot-acceptance" "${API_BASE_URL}/analytics/ops/pilot-acceptance?${query}"
call_to_file "evidence-pack" "${API_BASE_URL}/analytics/ops/evidence-pack?${query}"

if [[ -n "$CLASS_ID" ]]; then
  call_to_file "class-doctor" "${API_BASE_URL}/analytics/classes/$(urlencode "$CLASS_ID")/doctor"
fi

python - "$OUT_DIR" <<'PY'
from __future__ import annotations
import json
import sys
from pathlib import Path

out = Path(sys.argv[1])

def load(name: str) -> dict:
    path = out / f"{name}.json"
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text())
    except Exception as exc:
        return {"error": str(exc)}

pack = load("evidence-pack")
readiness = load("readiness")
sla = load("analytics-sla")
pilot = load("pilot-acceptance")
doctor = load("class-doctor")
summary = pack.get("summary") or {}
lines = [
    "# Analytics UAT Evidence Pack",
    "",
    f"- Version: `{pack.get('version') or load('build').get('version') or 'unknown'}`",
    f"- Generated at: `{pack.get('generated_at') or 'unknown'}`",
    f"- Evidence status: **{pack.get('evidence_status') or 'UNKNOWN'}**",
    f"- Ready for pilot: **{summary.get('ready_for_pilot')}**",
    f"- Ready for broad production: **{summary.get('ready_for_broad_production')}**",
    f"- SLA status: **{summary.get('sla_status') or sla.get('sla_status') or 'UNKNOWN'}**",
    f"- Pilot status: **{summary.get('pilot_status') or pilot.get('pilot_status') or 'UNKNOWN'}**",
    f"- Blockers: **{summary.get('blocker_count', pack.get('blocker_count', 0))}**",
    f"- Warnings: **{summary.get('warning_count', pack.get('warning_count', 0))}**",
    "",
    "## Filters",
]
for key, value in (pack.get("filters") or {}).items():
    lines.append(f"- {key}: `{value}`")

lines.extend(["", "## Primary readiness"])
primary = readiness.get("primary_blocker") or {}
if primary:
    lines.append(f"- Primary blocker: `{primary.get('code')}` — {primary.get('message')}")
    if primary.get("action"):
        lines.append(f"- Action: {primary.get('action')}")
else:
    lines.append("- Primary blocker: none")

lines.extend(["", "## Next actions"])
for action in (pack.get("next_actions") or [])[:10]:
    lines.append(f"- {action}")
if not (pack.get("next_actions") or []):
    lines.append("- Không có action bắt buộc từ evidence pack.")

lines.extend(["", "## Class doctor"])
if doctor:
    lines.append(f"- Status: `{doctor.get('status')}`")
    lines.append(f"- Data gap: `{doctor.get('data_gap')}`")
    lines.append(f"- Message: {doctor.get('message')}")
    lines.append(f"- Recommended action: {doctor.get('recommended_action')}")
else:
    lines.append("- Không truyền CLASS_ID nên không chạy class doctor.")

lines.extend(["", "## Files"])
for path in sorted(out.glob("*.json")):
    lines.append(f"- `{path.name}`")

lines.extend(["", "> Evidence pack chỉ là bằng chứng nghiệm thu vận hành. Các nhãn hành vi cá nhân là tín hiệu mềm, cần giáo viên/quản lý xác minh.", ""])
(out / "EVIDENCE_SUMMARY.md").write_text("\n".join(lines))
print(out / "EVIDENCE_SUMMARY.md")
PY

if command -v jq >/dev/null 2>&1; then
  echo
  echo "== Evidence summary =="
  jq '{version, evidence_status, summary, next_actions: (.next_actions[0:5])}' "$OUT_DIR/evidence-pack.json"
fi

echo
echo "UAT evidence pack written to: $OUT_DIR"
echo "Open: $OUT_DIR/EVIDENCE_SUMMARY.md"
