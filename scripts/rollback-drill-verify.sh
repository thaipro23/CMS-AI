#!/usr/bin/env bash
set -Eeuo pipefail

CURRENT_ZIP="${CURRENT_ZIP:-}"
PREVIOUS_ZIP="${PREVIOUS_ZIP:-}"
CURRENT_ROOT="${CURRENT_ROOT:-ai_server_openedx_v25_9_16_7_2_64_14}"
PREVIOUS_ROOT="${PREVIOUS_ROOT:-}"
ENV_BACKUP="${ENV_BACKUP:-}"
DEPLOY_ROOT="${DEPLOY_ROOT:-/opt/ai-server}"
OUT_DIR="${OUT_DIR:-/tmp/ai-rollback-drill-$(date +%Y%m%d-%H%M%S)}"
mkdir -p "$OUT_DIR"

: > "$OUT_DIR/checks.tsv"
record() { printf '%s\t%s\t%s\n' "$1" "$2" "$3" >> "$OUT_DIR/checks.tsv"; }

if [[ -n "$CURRENT_ZIP" && -f "$CURRENT_ZIP" ]] && unzip -l "$CURRENT_ZIP" | grep -q "$CURRENT_ROOT/"; then
  record PASS CURRENT_ZIP "Current zip contains $CURRENT_ROOT"
else
  record FAIL CURRENT_ZIP "Set CURRENT_ZIP and CURRENT_ROOT to an existing release artifact"
fi

if [[ -n "$PREVIOUS_ZIP" && -f "$PREVIOUS_ZIP" ]]; then
  if [[ -n "$PREVIOUS_ROOT" ]]; then
    if unzip -l "$PREVIOUS_ZIP" | grep -q "$PREVIOUS_ROOT/"; then record PASS PREVIOUS_ZIP "Previous zip contains $PREVIOUS_ROOT"; else record FAIL PREVIOUS_ZIP "Previous zip missing $PREVIOUS_ROOT"; fi
  else
    record WARN PREVIOUS_ROOT "PREVIOUS_ROOT not set; previous zip exists but root was not verified"
  fi
else
  record WARN PREVIOUS_ZIP "PREVIOUS_ZIP not set/found; rollback artifact must be available before pilot"
fi

if [[ -n "$ENV_BACKUP" && -f "$ENV_BACKUP" ]]; then
  record PASS ENV_BACKUP ".env.production backup exists"
else
  record WARN ENV_BACKUP "ENV_BACKUP not set/found; backup .env.production before pilot"
fi

cat > "$OUT_DIR/ROLLBACK_COMMANDS_PREVIEW.md" <<MD
# Rollback Commands Preview

This script is dry-run only; it does not execute rollback.

\`\`\`bash
cd $DEPLOY_ROOT

# 1) Restore previous artifact
unzip -o <PREVIOUS_ZIP> -d /tmp/ai-server-rollback
rsync -a --delete /tmp/ai-server-rollback/<PREVIOUS_ROOT>/ $DEPLOY_ROOT/

# 2) Restore env if needed
cp <ENV_BACKUP> $DEPLOY_ROOT/.env.production

# 3) Rebuild/recreate services
docker compose -f docker-compose.prod.yml --env-file .env.production build backend frontend worker beat
docker compose -f docker-compose.prod.yml --env-file .env.production up -d --force-recreate backend frontend worker beat

# 4) Verify
curl -sS https://api-ai.cms-test.poly.edu.vn/api/health/build | jq
curl -sS https://api-ai.cms-test.poly.edu.vn/api/health/production-pilot-final -H 'Authorization: Bearer <TOKEN>' | jq
\`\`\`
MD

python - <<'PY' "$OUT_DIR/checks.tsv" "$OUT_DIR/rollback-drill-summary.json" "$OUT_DIR/ROLLBACK_DRILL_SUMMARY.md"
import csv, json, sys
checks_path, json_path, md_path = sys.argv[1:]
rows=[]
with open(checks_path, encoding='utf-8') as fh:
    for level, code, message in csv.reader(fh, delimiter='\t'):
        rows.append({'level': level, 'code': code, 'message': message})
status = 'FAIL' if any(r['level']=='FAIL' for r in rows) else ('WARN' if any(r['level']=='WARN' for r in rows) else 'PASS')
json.dump({'status': status, 'checks': rows}, open(json_path, 'w', encoding='utf-8'), ensure_ascii=False, indent=2)
with open(md_path, 'w', encoding='utf-8') as fh:
    fh.write('# Rollback Drill Summary\n\n')
    fh.write(f"Status: **{status}**\n\n")
    fh.write('| Level | Code | Message |\n|---|---|---|\n')
    for row in rows:
        fh.write(f"| {row['level']} | `{row['code']}` | {row['message']} |\n")
print(md_path)
PY

echo "Rollback drill artifacts written to $OUT_DIR"
