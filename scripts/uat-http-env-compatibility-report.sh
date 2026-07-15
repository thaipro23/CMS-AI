#!/usr/bin/env bash
set -Eeuo pipefail
ROOT_DIR="${ROOT_DIR:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
cd "$ROOT_DIR"
pass=0
fail=0
check() {
  local label="$1"; shift
  if "$@"; then
    printf '[PASS] %s\n' "$label"
    pass=$((pass+1))
  else
    printf '[FAIL] %s\n' "$label"
    fail=$((fail+1))
  fi
}
has_line() { grep -qE "$2" "$1"; }
check 'Production env restores operational FRONTEND_URL' has_line .env.production.example '^FRONTEND_URL='
check 'Production env restores operational BACKEND_URL' has_line .env.production.example '^BACKEND_URL='
check 'Production env restores OPENEDX_MFE_BASE_URL alias' has_line .env.production.example '^OPENEDX_MFE_BASE_URL='
check 'Production env restores AP get-course cache aliases' bash -lc "grep -q '^ACADEMIC_AP_GET_COURSE_FILE_CACHE_ENABLED=' .env.production.example && grep -q '^ACADEMIC_AP_GET_COURSE_FILE_CACHE_DIR=' .env.production.example && grep -q '^ACADEMIC_AP_GET_COURSE_FILE_CACHE_TTL_SECONDS=' .env.production.example && grep -q '^ACADEMIC_AP_GET_COURSE_FILE_CACHE_REFRESH=' .env.production.example"
check 'Production env restores AP term-block TTL' has_line .env.production.example '^ACADEMIC_AP_TERM_BLOCK_REFRESH_TTL_SECONDS='
check 'Production env restores auto-map and full-learning sync' bash -lc "grep -q '^ACADEMIC_AUTO_MAP_COURSE_BEFORE_CMS_SYNC=' .env.production.example && grep -q '^ACADEMIC_FULL_SYNC_LEARNING_AFTER_ENROLLMENT=' .env.production.example"
check 'Production env restores Student Insight enrollment alias' has_line .env.production.example '^OPENEDX_STUDENT_INSIGHT_DEFAULT_ENROLLMENT_MODE='
check 'HTTP UAT template uses APP_ENV=uat' has_line .env.uat-http.example '^APP_ENV=uat$'
check 'HTTP UAT template explicitly opts into insecure cookie' bash -lc "grep -q '^AUTH_COOKIE_SECURE=false$' .env.uat-http.example && grep -q '^ALLOW_INSECURE_UAT_HTTP=true$' .env.uat-http.example"
check 'Production template keeps secure cookie mandatory' bash -lc "grep -q '^APP_ENV=production$' .env.production.example && grep -q '^AUTH_COOKIE_SECURE=true$' .env.production.example && grep -q '^ALLOW_INSECURE_UAT_HTTP=false$' .env.production.example"
check 'Config validates hardened UAT instead of skipping all checks' bash -lc "grep -q 'is_hardened_deployment' backend/app/core/config.py && grep -q 'ALLOW_INSECURE_UAT_HTTP=true' backend/app/core/config.py"
check 'Publisher accepts legacy MFE alias' grep -q "getattr(settings, 'openedx_mfe_base_url', None)" backend/app/modules/publisher/service.py
printf '\nUAT HTTP/env compatibility: %s passed, %s failed\n' "$pass" "$fail"
[[ "$fail" -eq 0 ]]
