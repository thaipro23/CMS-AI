# AI Server / Open edX CMS — Context v25.9.16.7.2.64.13

Baseline mới nhất:

```text
v25.9.16.7.2.64.13 — Security Attack Simulation + 20 Common Attack Hardening
zip: ai-server-openedx-v25.9.16.7.2.64.13-security-attack-simulation-hardening.zip
root: ai_server_openedx_v25_9_16_7_2_64_13
```

Bản `.64.11` tiếp tục từ `.64.10` và không có migration mới. Latest Alembic vẫn là:

```text
0052_v25_9_16_7_2_27_learning_behavior_logic_calibration.py
```

## Mục tiêu

Mô phỏng an toàn 20 nhóm tấn công web/API phổ biến trên artifact, thêm hardening thực tế và đưa security attack simulation vào readiness/ops flow.

## Thay đổi chính

### Backend hardening

Thêm middleware security headers:

```text
backend/app/core/security_headers.py
backend/app/main.py
```

Headers áp dụng:

```text
X-Content-Type-Options: nosniff
X-Frame-Options: DENY
Referrer-Policy: no-referrer
Permissions-Policy: accelerometer=(), camera=(), geolocation=(), ...
Cross-Origin-Resource-Policy: same-site
Cache-Control: no-store
X-Permitted-Cross-Domain-Policies: none
Content-Security-Policy: default-src 'none'; frame-ancestors 'none'; base-uri 'none'; form-action 'none'
Strict-Transport-Security nếu production + secure cookie
```

### HMAC nonce / replay protection

AI connector client now sends:

```text
X-AI-Connector-Nonce
```

File:

```text
backend/app/modules/openedx_connector/real.py
```

Unit reset plugin accepts nonce signatures and stores nonce/signature in Django cache:

```text
openedx-unit-reset-plugin/openedx_unit_reset/views.py
```

Open edX connector plugin already has nonce replay protection:

```text
openedx-connector-plugin/openedx_ai_connector/auth.py
```

### Upload filename hardening

Bank material upload pending filename now uses:

```text
safe_upload_filename(...)
```

Files:

```text
backend/app/services/question_bank/helpers.py
backend/app/api/routes/question_bank_v2.py
```

### Security attack simulation gate

Endpoint mới:

```text
GET /api/health/security-attack-simulation
```

Service:

```text
backend/app/services/security_attack_simulation.py
```

Report is read-only and checks 20 common attack classes:

```text
1. Demo header role spoofing
2. JWT admin privilege spoofing
3. Wrong/expired token replay
4. Cookie-authenticated CSRF without Origin
5. Malicious cross-site Origin
6. Wildcard CORS with credentials
7. Clickjacking/frame injection
8. MIME sniffing/content-type confusion
9. Sensitive Referer leakage
10. TLS downgrade/cookie theft over HTTP
11. Unauthenticated metrics scraping
12. SSRF through asset/transcript download URL
13. Connector HMAC replay
14. Unit-reset HMAC replay
15. Path traversal in uploaded filenames
16. Oversized upload/decompression bomb
17. Unsupported executable upload
18. Unauthorized Assignment score mutation
19. Debug traceback/secret leakage in API errors
20. Student Ops / Quiz Bank privilege confusion
```

Safe policy:

```text
read_only_static_attack_simulation_no_exploit_execution
```

Guarantees:

```text
Không gửi exploit request vào live server
Không brute-force token/password
Không scan mạng nội bộ
Không gọi Open edX/AP/OpenAI
Không enqueue job hoặc mutate database
```

### Frontend ops readiness

`/ops/readiness` now includes:

```text
Security attack simulation
```

Files:

```text
frontend/app/ops/readiness/page.tsx
frontend/lib/api/readiness.ts
frontend/types/readiness.ts
```

### Scripts

New script:

```text
scripts/security-attack-simulation-report.sh
```

Outputs:

```text
security-attack-simulation.json
SECURITY_ATTACK_SIMULATION_SUMMARY.md
```

Integrated into:

```text
scripts/uat-runtime-verify.sh
scripts/uat-build-gate.sh
scripts/claude-code-review-pack.sh
```

## Test/check results

```text
v64.x + v64.11 regression: 68 passed
backend/app + Open edX connector + unit-reset compileall: passed
bash syntax: passed
claude-code-review-pack: PASS, failures=0, warnings=0
uat-build-gate sandbox: WARN only because missing deps/node_modules/Docker/env or skipped frontend/review
```

## Deploy

```bash
cd /opt/ai-server

unzip -o ai-server-openedx-v25.9.16.7.2.64.13-security-attack-simulation-hardening.zip -d /tmp/ai-server-v25.9.16.7.2.64.13

rsync -a --delete /tmp/ai-server-v25.9.16.7.2.64.13/ai_server_openedx_v25_9_16_7_2_64_13/ /opt/ai-server/

docker compose -f docker-compose.prod.yml --env-file .env.production build backend frontend worker beat

docker compose -f docker-compose.prod.yml --env-file .env.production up -d --force-recreate backend frontend worker beat
```

Version env:

```env
APP_VERSION=25.9.16.7.2.64.13
NEXT_PUBLIC_APP_VERSION=25.9.16.7.2.64.13
```

Verify:

```bash
curl -sS 'https://api-ai.cms-test.poly.edu.vn/api/health/security-attack-simulation' \
  -H 'Authorization: Bearer <TOKEN>' | jq
```

Export report:

```bash
cd /opt/ai-server

API_BASE_URL=https://api-ai.cms-test.poly.edu.vn/api \
TOKEN='<TOKEN>' \
OUT_DIR=/tmp/ai-security-attack-simulation-$(date +%Y%m%d-%H%M%S) \
./scripts/security-attack-simulation-report.sh
```

## Lưu ý trung thực

`.64.11` không tấn công live server, không brute-force và không scan mạng. Đây là static attack simulation + code hardening an toàn trong artifact. Sau deploy UAT cần chạy dynamic smoke test có kiểm soát qua reverse proxy/TLS thật: CSRF no Origin, malicious Origin, SSRF private IP, upload oversized file, HMAC replay, security headers, role matrix.
