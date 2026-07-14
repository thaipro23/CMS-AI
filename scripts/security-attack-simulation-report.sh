#!/usr/bin/env bash
set -Eeuo pipefail

API_BASE_URL="${API_BASE_URL:-https://api-ai.cms-test.poly.edu.vn/api}"
TOKEN="${TOKEN:-}"
EXPECTED_VERSION="${EXPECTED_VERSION:-25.9.16.7.2.64.16.5.1}"
OUT_DIR="${OUT_DIR:-/tmp/ai-security-attack-simulation-$(date +%Y%m%d-%H%M%S)}"
mkdir -p "$OUT_DIR"

if [[ -z "$TOKEN" ]]; then
  echo "TOKEN is required" >&2
  exit 2
fi

curl -fsS "$API_BASE_URL/health/security-attack-simulation" \
  -H "Authorization: Bearer $TOKEN" \
  -H 'Accept: application/json' \
  -o "$OUT_DIR/security-attack-simulation.json"

python - <<'PY' "$OUT_DIR/security-attack-simulation.json" "$OUT_DIR/SECURITY_ATTACK_SIMULATION_SUMMARY.md" "$EXPECTED_VERSION"
import json, sys
src, dst, expected = sys.argv[1:]
data = json.load(open(src, encoding='utf-8'))
attacks = data.get('attacks') or []
issues = [a for a in attacks if a.get('status') != 'PROTECTED']
with open(dst, 'w', encoding='utf-8') as fh:
    fh.write('# Security Attack Simulation Summary\n\n')
    fh.write(f"Status: **{data.get('status')}**\n\n")
    fh.write(f"Version: `{data.get('version')}` · Expected: `{expected}`\n\n")
    fh.write(f"Attacks simulated: **{data.get('attack_count', len(attacks))}** · Protected: **{data.get('protected_count', 0)}** · Needs review: **{data.get('needs_review_count', 0)}**\n\n")
    fh.write(f"Blockers: **{data.get('blocker_count', 0)}** · Warnings: **{data.get('warning_count', 0)}**\n\n")
    fh.write('## 20 attack controls\n\n')
    fh.write('| # | Category | Attack | Status | Control | Fix/UAT action |\n')
    fh.write('|---:|---|---|---|---|---|\n')
    for item in attacks:
        fh.write(f"| {item.get('id')} | {item.get('category')} | {item.get('attack')} | {item.get('status')} | {item.get('control')} | {item.get('fix')} |\n")
    fh.write('\n## Issues needing UAT review\n\n')
    if not issues:
        fh.write('Không có blocker/cảnh báo trong static simulation.\n')
    else:
        for item in issues:
            fh.write(f"- **{item.get('attack')}**: {item.get('fix')}\n")
    fh.write('\n## Read-only guarantees\n\n')
    for item in data.get('read_only_guarantees') or []:
        fh.write(f'- {item}\n')
print(dst)
PY

echo "Security attack simulation report written to $OUT_DIR"
