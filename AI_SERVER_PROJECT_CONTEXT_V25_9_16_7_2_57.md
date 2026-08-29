# CONTEXT DỰ ÁN AI SERVER / OPEN edX CMS — BASELINE v25.9.16.7.2.64.13

## Baseline mới nhất

```text
v25.9.16.7.2.64.13 — Performance Load Hardening
zip: ai-server-openedx-v25.9.16.7.2.64.13-performance-load-hardening.zip
root: ai_server_openedx_v25_9_16_7_2_64_13
```

Bản `.57` tiếp tục từ `.56` và **không có Alembic migration mới**. Latest migration vẫn là:

```text
0052_v25_9_16_7_2_27_learning_behavior_logic_calibration.py
```

## Mục tiêu `.57`

Bổ sung cổng kiểm tra hiệu năng/load trước khi mở rộng UAT/pilot nhiều lớp, nhiều môn, nhiều tracking event. Báo cáo tập trung vào rủi ro nghẽn DB/worker/response-size/index mà không chạy query nặng trong request.

## Thay đổi chính

### 1. Performance readiness endpoint

Thêm endpoint authenticated/read-only:

```text
GET /api/health/performance-readiness
```

Endpoint dùng:

```text
backend/app/services/performance_readiness.py
```

Báo cáo trả về:

```text
status: READY | READY_WITH_WARNINGS | BLOCKED
blocker_count
warning_count
checks
sections
table_estimates
queue_pressure
limits
next_actions
read_only_guarantees
```

### 2. Các nhóm kiểm tra

```text
configuration
- DB_POOL_SIZE
- DB_MAX_OVERFLOW
- DB_STATEMENT_TIMEOUT_MS
- ANALYTICS_DASHBOARD_MAX_PAGE_SIZE
- BANK_SEARCH_MAX_RESULTS
- OPENEDX_CONNECTOR_MAX_BATCH_SIZE
- ANALYTICS_POST_INGEST_MAX_JOBS_PER_RUN
- ANALYTICS_BACKFILL_MAX_ACTIVE_JOBS

index_contract
- academic classes/class students/jobs
- analytics tracking/progress/snapshot tables
- bank questions/release/quiz/job tables

queue_pressure
- class sync jobs
- bulk operation jobs
- teacher report jobs
- bank operation jobs
- generation jobs

table_growth
- pg_stat_user_tables estimates nếu runtime là PostgreSQL
```

### 3. UI `/analytics/learning`

Thêm panel:

```text
Hiệu năng vận hành
```

Panel hiển thị:

```text
- performance status
- blocker/cảnh báo
- DB pool/overflow
- statement timeout
- active jobs / failed jobs last hour
- analytics page-size
- connector batch size
- sections/checks
- next actions
- read-only guarantees
```

### 4. Script evidence

Thêm:

```text
scripts/performance-readiness-report.sh
```

Chạy UAT:

```bash
API_BASE_URL=https://api-ai.cms-test.poly.edu.vn/api \
TOKEN='<TOKEN>' \
OUT_DIR=/tmp/ai-performance-readiness-$(date +%Y%m%d-%H%M%S) \
./scripts/performance-readiness-report.sh
```

Output:

```text
performance-readiness.json
PERFORMANCE_READINESS_SUMMARY.md
```

### 5. Runtime verify

`scripts/uat-runtime-verify.sh` gọi thêm:

```text
/api/health/performance-readiness
```

để sau deploy biết readiness + SLA + pilot + evidence + performance trong một lượt verify.

## Safety

Bản `.57` là read-only:

```text
Không scan raw tracking.log trong request
Không chạy EXPLAIN ANALYZE hoặc query plan nặng
Không gọi Open edX connector trong performance report
Không enqueue job
Không recalculate trong request
Không mutate dữ liệu
Không migration mới
Không dùng wording kết luận vi phạm cá nhân
```

## Kiểm thử đã chạy

```text
v57-specific tests: 5 passed
Selected static regression: 25 passed
backend compileall: passed
bash syntax: passed
claude-code-review-pack: PASS, 0 failures, 0 warnings
uat-build-gate sandbox: WARN only do thiếu psycopg/frontend node_modules/Docker/.env.production
```

## Deploy

```bash
cd /opt/ai-server
unzip -o ai-server-openedx-v25.9.16.7.2.64.13-performance-load-hardening.zip -d /tmp/ai-server-v25.9.16.7.2.64.13
rsync -a --delete /tmp/ai-server-v25.9.16.7.2.64.13/ai_server_openedx_v25_9_16_7_2_64_13/ /opt/ai-server/

docker compose -f docker-compose.prod.yml --env-file .env.production build backend frontend worker beat
docker compose -f docker-compose.prod.yml --env-file .env.production up -d --force-recreate backend frontend worker beat
```

Set version:

```env
APP_VERSION=25.9.16.7.2.64.13
NEXT_PUBLIC_APP_VERSION=25.9.16.7.2.64.13
```

## Verify nhanh

```bash
curl -sS 'https://api-ai.cms-test.poly.edu.vn/api/health/performance-readiness' \
  -H 'Authorization: Bearer <TOKEN>' | jq
```

## Preserved từ các bản trước

- `.56` Bank Release Publish Reliability + Rollback QA
- `.55` Analytics Course/Class Mapping Reliability
- `.54` RollNumber Identity Migration Assistant
- `.53` UAT Runtime Verification + Frontend Build Fix
- `.52` Claude Review Findings + Build Gate
- `.51` Claude Code Review Readiness Pack
- `.50` UAT Evidence Pack
- `.49` Pilot Acceptance UI
- `.48` Campus RBAC Audit Hardening
- `.47` Bank Quiz Final Test Production QA
- `.46` Analytics SLA Dashboard
- `.45` UAT RollNumber cleanup
- `.44` identity reconciliation
- `.42` Bank table UX
- `.40` CMS student username = RollNumber
- `.37` analytics class result doctor
- `.36` sidebar fix
- `.35` post-ingest recalculate orchestrator
