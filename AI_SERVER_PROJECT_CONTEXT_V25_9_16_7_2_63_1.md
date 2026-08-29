# CONTEXT DỰ ÁN AI SERVER / OPEN edX CMS — BASELINE v25.9.16.7.2.64.13

## Baseline mới nhất

```text
v25.9.16.7.2.64.13 — Maintainability + UI Contract Refactor / Completion: Ops Readiness Split
zip: ai-server-openedx-v25.9.16.7.2.64.13-maintainability-completion-ops-readiness-split.zip
root: ai_server_openedx_v25_9_16_7_2_64_13
```

Bản này tiếp tục từ `.63` và không có Alembic migration mới. Latest migration vẫn là:

```text
0052_v25_9_16_7_2_27_learning_behavior_logic_calibration.py
```

## Mục tiêu `.63.1`

User yêu cầu tiếp tục làm `.63` cho đến hết. `.63.1` hoàn thiện hướng maintainability bằng cách tách thật operational readiness UI khỏi màn nghiệp vụ `/analytics/learning` sang một route riêng, đồng thời dùng các split module đã tạo ở `.63`.

## Thay đổi chính

### 1. Route UI mới

```text
/ops/readiness
```

File:

```text
frontend/app/ops/readiness/page.tsx
```

Trang này gom các gate vận hành:

```text
Security readiness
Performance readiness
Release Candidate
Pilot Operations
Maintainability contract
Query hotspots
```

Tính chất:

```text
Read-only
Không enqueue job
Không mutate dữ liệu
Không đọc raw tracking.log
Không phá flow analytics cũ
```

### 2. Dùng split frontend modules thay vì tiếp tục làm phình monolith

Các file chính:

```text
frontend/lib/api/readiness.ts
frontend/types/readiness.ts
frontend/components/readiness/OperationalGatePanel.tsx
```

Bổ sung trong `.63.1`:

```text
getQueryHotspots(...)
QueryHotspotReport
```

### 3. Navigation

Thêm item trong AppShell:

```text
Readiness → /ops/readiness
permission: view_jobs
```

File:

```text
frontend/components/layout/AppShell.tsx
```

### 4. Maintainability gate theo dõi route split mới

Cập nhật:

```text
backend/app/services/maintainability_contract.py
```

Maintainability contract hiện track thêm:

```text
frontend/app/ops/readiness/page.tsx
```

## Test/check đã chạy

```text
v63.1-specific tests: 6 passed
selected v57/v58/v59/v60/v61/v62/v63/v63.1 regression: 44 passed
backend/app + Open edX connector + unit-reset compileall: passed
bash syntax: passed
claude-code-review-pack: PASS, 0 failures, 0 warnings
uat-build-gate sandbox: WARN only because backend deps/psycopg, frontend node_modules, Docker/.env.production are unavailable or frontend build/review was skipped
```

## Deploy

```bash
cd /opt/ai-server

unzip -o ai-server-openedx-v25.9.16.7.2.64.13-maintainability-completion-ops-readiness-split.zip -d /tmp/ai-server-v25.9.16.7.2.64.13

rsync -a --delete /tmp/ai-server-v25.9.16.7.2.64.13/ai_server_openedx_v25_9_16_7_2_64_13/ /opt/ai-server/

docker compose -f docker-compose.prod.yml --env-file .env.production build backend frontend worker beat

docker compose -f docker-compose.prod.yml --env-file .env.production up -d --force-recreate backend frontend worker beat
```

Set version:

```env
APP_VERSION=25.9.16.7.2.64.13
NEXT_PUBLIC_APP_VERSION=25.9.16.7.2.64.13
```

## Verify

Backend:

```bash
curl -sS 'https://api-ai.cms-test.poly.edu.vn/api/health/maintainability-contract' \
  -H 'Authorization: Bearer <TOKEN>' | jq

curl -sS 'https://api-ai.cms-test.poly.edu.vn/api/health/query-hotspots?max_items=120' \
  -H 'Authorization: Bearer <TOKEN>' | jq
```

Frontend:

```text
/ops/readiness
```

## Lưu ý trung thực

`.63.1` vẫn không tách ồ ạt `academic_service.py`, `question_bank_service.py`, `analytics_core_service.py`, `globals.css`, vì làm vậy dễ phá nghiệp vụ nếu không có test integration/load đầy đủ. Bản này hoàn thiện phần nền maintainability và đưa ops dashboard ra route riêng. Nếu muốn tiếp tục trước `.64`, nên làm `.63.2` để tách một khu vực lớn duy nhất, ví dụ `analytics/learning/page.tsx` hoặc `question_bank_service.py`.

## Roadmap còn lại

```text
v25.9.16.7.2.64.13 — Production Pilot Final QA + Rollback Drill
```
