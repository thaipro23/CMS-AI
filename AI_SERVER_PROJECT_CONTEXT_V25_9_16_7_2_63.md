# CONTEXT DỰ ÁN AI SERVER / OPEN edX CMS — BASELINE v25.9.16.7.2.64.13

## Baseline mới nhất

```text
v25.9.16.7.2.64.13 — Maintainability + UI Contract Refactor
zip: ai-server-openedx-v25.9.16.7.2.64.13-maintainability-ui-contract-refactor.zip
root: ai_server_openedx_v25_9_16_7_2_64_13
```

Bản `.63` tiếp tục từ `.62 Query Hotspot + Load Hardening` và không có Alembic migration mới. Latest migration vẫn là:

```text
0052_v25_9_16_7_2_27_learning_behavior_logic_calibration.py
```

## Mục tiêu `.63`

Không thêm nghiệp vụ mới. Bản này giảm rủi ro maintainability bằng cách chuẩn hóa contract schema cho readiness/gate endpoints, tạo split module frontend cho readiness API/types/components, và thêm maintainability contract gate để làm rõ các God files còn cần tách tiếp.

## Thay đổi backend chính

### 1. Pydantic readiness/gate response contracts

Thêm:

```text
backend/app/schemas/readiness.py
```

Các contract chính:

```text
OperationReportBase
ProductionReadinessReport
SecurityReadinessReport
PerformanceReadinessReport
QueryHotspotReport
ReleaseCandidateReport
PilotOperationsReport
MaintainabilityContractReport
```

Các endpoint trong `backend/app/api/routes/health.py` đã có `response_model`:

```text
GET /api/health/readiness
GET /api/health/security-readiness
GET /api/health/performance-readiness
GET /api/health/query-hotspots
GET /api/health/release-candidate
GET /api/health/pilot-operations
GET /api/health/maintainability-contract
```

Schema dùng `extra='allow'` để backward-compatible với payload report cũ nhưng vẫn khóa các field chung cho FE/API contract.

### 2. Maintainability contract gate

Thêm:

```text
backend/app/services/maintainability_contract.py
GET /api/health/maintainability-contract
```

Gate này read-only, static source scan:

```text
Không query database
Không import heavy runtime modules
Không enqueue job
Không mutate dữ liệu
Không thay đổi schema database
```

Nó report:

```text
status: READY | READY_WITH_WARNINGS | BLOCKED
file_metrics
contract_modules
checks
sections
summary
next_actions
read_only_guarantees
```

Nó không che giấu large-file debt; các file lớn như `academic_service.py`, `question_bank_service.py`, `analytics_core_service.py`, `frontend/lib/api.ts`, `frontend/types/index.ts`, `globals.css` vẫn được báo warning để refactor tiếp.

## Thay đổi frontend chính

Thêm split modules:

```text
frontend/types/readiness.ts
frontend/lib/api/readiness.ts
frontend/components/readiness/OperationalGatePanel.tsx
```

Mục tiêu: các readiness/ops UI/API sau này không tiếp tục làm phình:

```text
frontend/types/index.ts
frontend/lib/api.ts
frontend/app/analytics/learning/page.tsx
frontend/app/globals.css
```

Đã export `API`, `apiFetch`, `parseResponse` từ `frontend/lib/api.ts` để split API facade có thể dùng lại legacy client mà không duplicate logic.

## Scripts mới/cập nhật

Thêm:

```text
scripts/maintainability-contract-report.sh
```

Script xuất:

```text
maintainability-contract.json
MAINTAINABILITY_CONTRACT_SUMMARY.md
```

Đã tích hợp vào:

```text
scripts/uat-runtime-verify.sh
scripts/uat-build-gate.sh
scripts/claude-code-review-pack.sh
```

## Deploy

```bash
cd /opt/ai-server
unzip -o ai-server-openedx-v25.9.16.7.2.64.13-maintainability-ui-contract-refactor.zip -d /tmp/ai-server-v25.9.16.7.2.64.13
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
curl -sS 'https://api-ai.cms-test.poly.edu.vn/api/health/maintainability-contract' \
  -H 'Authorization: Bearer <TOKEN>' | jq
```

Xuất report:

```bash
cd /opt/ai-server
API_BASE_URL=https://api-ai.cms-test.poly.edu.vn/api \
TOKEN='<TOKEN>' \
OUT_DIR=/tmp/ai-maintainability-contract-$(date +%Y%m%d-%H%M%S) \
./scripts/maintainability-contract-report.sh
```

## Test/check đã chạy

```text
v63-specific tests: 6 passed
selected v57/v58/v59/v60/v61/v62/v63 regression: 38 passed
backend/app + Open edX connector + unit-reset compileall: passed
bash syntax: passed
claude-code-review-pack: PASS, failures=0, warnings=0
uat-build-gate sandbox: WARN only because backend deps/psycopg, frontend node_modules, Docker/.env.production are unavailable/skipped in sandbox
```

## Honest limitation

`.63` chưa tách hết God files vì khối lượng lớn và rủi ro regression cao. Bản này tạo contract/schema/split-module/gate để các bản sau tách có kiểm soát. Large files vẫn được report thành warning chứ không bị che giấu.

## Roadmap tiếp theo

```text
v25.9.16.7.2.64.13 — Production Pilot Final QA + Rollback Drill
```

Hoặc có thể làm `.63.x` để tách tiếp một nhóm lớn cụ thể, ví dụ `academic_service.py` hoặc `question_bank_service.py`, trước khi chốt `.64`.
