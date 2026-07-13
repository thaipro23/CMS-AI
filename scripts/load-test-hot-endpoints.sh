#!/usr/bin/env bash
# v25.9.16.7.2.64.12 — Production Pilot Final QA + Rollback Drill
set -Eeuo pipefail

API_BASE_URL="${API_BASE_URL:-https://api-ai.cms-test.poly.edu.vn/api}"
TOKEN="${TOKEN:-}"
REQUESTS="${REQUESTS:-5}"
CONCURRENCY_NOTE="${CONCURRENCY_NOTE:-sequential-smoke}"
OUT_DIR="${OUT_DIR:-/tmp/ai-load-test-hot-endpoints-$(date +%Y%m%d-%H%M%S)}"
ENDPOINTS_FILE="${ENDPOINTS_FILE:-}"
mkdir -p "$OUT_DIR"

if [[ -z "$TOKEN" ]]; then
  echo "TOKEN is required" >&2
  exit 2
fi

if [[ -n "$ENDPOINTS_FILE" && -f "$ENDPOINTS_FILE" ]]; then
  mapfile -t ENDPOINTS < <(grep -v '^#' "$ENDPOINTS_FILE" | sed '/^$/d')
else
  ENDPOINTS=(
    '/health/build'
    '/jobs?page=1&page_size=20'
    '/audit?page=1&page_size=20'
    '/health/query-hotspots?max_items=80'
    '/health/maintainability-contract'
    '/health/pilot-operations?sample_limit=5'
    '/health/production-pilot-final?sample_limit=5&include_static_scans=true'
  )
fi

: > "$OUT_DIR/latency.tsv"
for endpoint in "${ENDPOINTS[@]}"; do
  for i in $(seq 1 "$REQUESTS"); do
    tmp="$OUT_DIR/response-${i}.json"
    result=$(curl -sS -o "$tmp" -w '%{http_code}\t%{time_total}' \
      "$API_BASE_URL$endpoint" \
      -H "Authorization: Bearer $TOKEN" \
      -H 'Accept: application/json' || printf '000\t0')
    http_code="${result%%$'\t'*}"
    seconds="${result##*$'\t'}"
    printf '%s\t%s\t%s\t%s\n' "$endpoint" "$i" "$http_code" "$seconds" >> "$OUT_DIR/latency.tsv"
  done
done

python - <<'PY' "$OUT_DIR/latency.tsv" "$OUT_DIR/load-test-summary.json" "$OUT_DIR/LOAD_TEST_HOT_ENDPOINTS_SUMMARY.md" "$REQUESTS" "$CONCURRENCY_NOTE"
import csv, json, math, sys
latency_path, json_path, md_path, requests, note = sys.argv[1:]
rows=[]
with open(latency_path, encoding='utf-8') as fh:
    for endpoint, index, http_code, seconds in csv.reader(fh, delimiter='\t'):
        rows.append({'endpoint': endpoint, 'index': int(index), 'http_code': http_code, 'ms': round(float(seconds)*1000, 2)})
by={}
for row in rows:
    by.setdefault(row['endpoint'], []).append(row)
summary=[]
for endpoint, items in by.items():
    values=sorted(item['ms'] for item in items)
    p95=values[min(len(values)-1, math.ceil(len(values)*0.95)-1)] if values else 0
    ok_codes=sum(200 <= int(item['http_code'] or 0) < 400 for item in items)
    summary.append({'endpoint': endpoint, 'requests': len(items), 'ok': ok_codes, 'p95_ms': p95, 'max_ms': max(values or [0])})
status='FAIL' if any(item['ok'] < item['requests'] for item in summary) else 'PASS'
out={'status': status, 'mode': note, 'requests_per_endpoint': int(requests), 'summary': summary, 'rows': rows}
json.dump(out, open(json_path, 'w', encoding='utf-8'), ensure_ascii=False, indent=2)
with open(md_path, 'w', encoding='utf-8') as fh:
    fh.write('# Load Test Hot Endpoints Summary\n\n')
    fh.write(f"Status: **{status}** · Mode: `{note}` · Requests/endpoint: **{requests}**\n\n")
    fh.write('| Endpoint | OK | Requests | p95 ms | max ms |\n|---|---:|---:|---:|---:|\n')
    for item in summary:
        fh.write(f"| `{item['endpoint']}` | {item['ok']} | {item['requests']} | {item['p95_ms']} | {item['max_ms']} |\n")
print(md_path)
PY

echo "Load test artifacts written to $OUT_DIR"
