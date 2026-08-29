# CONTEXT DỰ ÁN AI SERVER / OPEN edX CMS — BASELINE v25.9.16.7.2.64.13

## Baseline mới nhất

```text
v25.9.16.7.2.64.13 — Production Pilot Final QA + Rollback Drill
zip: ai-server-openedx-v25.9.16.7.2.64.13-production-pilot-final-qa-rollback-drill.zip
root: ai_server_openedx_v25_9_16_7_2_64_13
```

Bản `.64` tiếp tục từ `.63.1`, không có Alembic migration mới. Latest migration vẫn là:

```text
0052_v25_9_16_7_2_27_learning_behavior_logic_calibration.py
```

## Mục tiêu bản .64

`.64` là bản chốt theo roadmap 4 bản: Production Pilot Final QA + Rollback Drill. Mục tiêu không phải thêm nghiệp vụ mới, mà gom toàn bộ gate vận hành thành quy trình sign-off trước khi chạy pilot thật:

- final go/no-go gate;
- load-test hot endpoints;
- rollback drill dry-run;
- Open edX publish/quiz verification checklist;
- evidence pack trước pilot;
- sign-off rõ theo role vận hành.

## Thay đổi backend

### Endpoint mới

```text
GET /api/health/production-pilot-final
```

Query optional:

```text
class_id
course_id
campus
branch
sample_limit
include_static_scans
```

File chính:

```text
backend/app/services/production_pilot_final.py
backend/app/api/routes/health.py
backend/app/schemas/readiness.py
```

Response gồm:

```text
status: GO | GO_WITH_MONITORING | HOLD
decision: GO_PILOT | GO_CONTROLLED_PILOT | NO_GO
ready_for_pilot
ready_for_broad_production
gates
final_checks
evidence_required
load_test_plan
rollback_drill
signoff
next_actions
read_only_guarantees
```

### Safety

Endpoint final gate là read-only:

```text
Không đọc raw tracking.log trong request
Không gọi Open edX/AP/OpenAI trong request
Không enqueue job hoặc recalculate
Không publish/rollback Bank Release
Không chạy load test trong API request
Không mutate database
Không kết luận vi phạm cá nhân
```

## Thay đổi frontend

Màn mới từ `.63.1`:

```text
/ops/readiness
```

`.64` bổ sung panel:

```text
Production pilot final
```

File chính:

```text
frontend/app/ops/readiness/page.tsx
frontend/lib/api/readiness.ts
frontend/types/readiness.ts
```

## Scripts mới

```text
scripts/production-pilot-final-gate.sh
scripts/load-test-hot-endpoints.sh
scripts/rollback-drill-verify.sh
scripts/openedx-publish-verify.sh
```

### production-pilot-final-gate.sh

Gọi:

```text
/api/health/production-pilot-final
/api/health/pilot-operations
/api/health/release-candidate
/api/health/security-readiness
/api/health/performance-readiness
/api/health/maintainability-contract
/api/health/query-hotspots
```

Xuất:

```text
production-pilot-final.json
PRODUCTION_PILOT_FINAL_SUMMARY.md
```

### load-test-hot-endpoints.sh

Smoke/load test tuần tự các endpoint nóng bằng curl, đo `time_total`, tính p95/max.

Xuất:

```text
latency.tsv
load-test-summary.json
LOAD_TEST_HOT_ENDPOINTS_SUMMARY.md
```

### rollback-drill-verify.sh

Dry-run only, không rollback thật. Kiểm tra:

```text
CURRENT_ZIP
PREVIOUS_ZIP
PREVIOUS_ROOT
ENV_BACKUP
DEPLOY_ROOT
```

Xuất:

```text
rollback-drill-summary.json
ROLLBACK_DRILL_SUMMARY.md
ROLLBACK_COMMANDS_PREVIEW.md
```

### openedx-publish-verify.sh

Read-only verification/checklist cho release publish audit nếu có `RELEASE_ID`.

Xuất:

```text
release-publish-audit.json
OPENEDX_PUBLISH_VERIFY_SUMMARY.md
```

## Scripts đã cập nhật

```text
scripts/uat-runtime-verify.sh
scripts/uat-build-gate.sh
scripts/claude-code-review-pack.sh
```

Runtime verify probe thêm:

```text
/api/health/production-pilot-final
```

Build gate version-sync thêm 4 script mới.

## Deploy

```bash
cd /opt/ai-server
unzip -o ai-server-openedx-v25.9.16.7.2.64.13-production-pilot-final-qa-rollback-drill.zip -d /tmp/ai-server-v25.9.16.7.2.64.13
rsync -a --delete /tmp/ai-server-v25.9.16.7.2.64.13/ai_server_openedx_v25_9_16_7_2_64_13/ /opt/ai-server/
docker compose -f docker-compose.prod.yml --env-file .env.production build backend frontend worker beat
docker compose -f docker-compose.prod.yml --env-file .env.production up -d --force-recreate backend frontend worker beat
```

Env:

```env
APP_VERSION=25.9.16.7.2.64.13
NEXT_PUBLIC_APP_VERSION=25.9.16.7.2.64.13
```

## Verify nhanh

```bash
curl -sS 'https://api-ai.cms-test.poly.edu.vn/api/health/production-pilot-final?branch=poly&campus=ph&sample_limit=5' \
  -H 'Authorization: Bearer <TOKEN>' | jq
```

## Full final evidence trên UAT

```bash
cd /opt/ai-server

OUT_DIR=/tmp/ai-server-uat-build-gate-$(date +%Y%m%d-%H%M%S) \
STRICT=1 \
RUN_FRONTEND_BUILD=1 \
RUN_FRONTEND_INSTALL=1 \
RUN_REVIEW_PACK=1 \
./scripts/uat-build-gate.sh

API_BASE_URL=https://api-ai.cms-test.poly.edu.vn/api \
TOKEN='<TOKEN>' \
BRANCH=poly \
CAMPUS=ph \
CLASS_ID='<CLASS_ID>' \
OUT_DIR=/tmp/ai-production-pilot-final-$(date +%Y%m%d-%H%M%S) \
./scripts/production-pilot-final-gate.sh

API_BASE_URL=https://api-ai.cms-test.poly.edu.vn/api \
TOKEN='<TOKEN>' \
REQUESTS=10 \
OUT_DIR=/tmp/ai-load-hot-$(date +%Y%m%d-%H%M%S) \
./scripts/load-test-hot-endpoints.sh

CURRENT_ZIP=/opt/artifacts/ai-server-openedx-v25.9.16.7.2.64.13-production-pilot-final-qa-rollback-drill.zip \
PREVIOUS_ZIP=/opt/artifacts/<previous-release>.zip \
PREVIOUS_ROOT='<previous-root>' \
ENV_BACKUP=/opt/backups/.env.production.before-v64 \
OUT_DIR=/tmp/ai-rollback-drill-$(date +%Y%m%d-%H%M%S) \
./scripts/rollback-drill-verify.sh
```

## Tests/checks trong artifact

```text
v64-specific tests: 5 passed
selected v57/v58/v59/v60/v61/v62/v63/v63.1/v64 regression: 49 passed
backend/app + Open edX connector + unit-reset compileall: passed
bash syntax: passed
claude-code-review-pack: PASS, failures=0, warnings=0
uat-build-gate sandbox: WARN only due missing deps/node_modules/Docker/env or skipped frontend/review
```

## Roadmap sau .64

Roadmap 4 bản đã hoàn thành:

```text
.61 Auth/RBAC Security Boundary Hardening
.62 Query Hotspot + Load Hardening
.63 Maintainability + UI Contract Refactor
.64 Production Pilot Final QA + Rollback Drill
```

Tiếp theo không nên thêm feature lớn. Nên chạy pilot thật hẹp và dùng evidence từ `.64`. Nếu cần tiếp tục code, nên làm `.64.1` chỉ sửa lỗi phát hiện từ UAT final gate/load/rollback.
