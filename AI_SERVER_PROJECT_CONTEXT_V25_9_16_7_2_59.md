# CONTEXT DỰ ÁN AI SERVER / OPEN edX CMS — BASELINE v25.9.16.7.2.64.13

## Baseline mới nhất

```text
v25.9.16.7.2.64.13 — Pilot Release Candidate
zip: ai-server-openedx-v25.9.16.7.2.64.13-pilot-release-candidate.zip
root: ai_server_openedx_v25_9_16_7_2_64_13
```

Bản `.59` tiếp tục từ `.58` và **không có Alembic migration mới**. Latest migration vẫn là:

```text
0052_v25_9_16_7_2_27_learning_behavior_logic_calibration.py
```

## Mục tiêu bản .59

Đóng gói bản RC cho UAT/pilot bằng một gate go/no-go tổng hợp, thay vì phải tự xem rời rạc nhiều panel/report.

Bản này **không thêm nghiệp vụ mới** và không thay đổi schema. Trọng tâm là release evidence, go/no-go, reviewer handoff và rollback readiness.

## Thay đổi chính

### 1. Release Candidate endpoint

Thêm endpoint authenticated/read-only:

```text
GET /api/health/release-candidate
```

Query optional:

```text
class_id
course_id
campus
branch
sample_limit
```

Endpoint trả:

```text
status: PASS | PASS_WITH_WARNINGS | FAIL
go_no_go: GO_PILOT | GO_PILOT_WITH_MONITORING | GO_BROAD_PRODUCTION | HOLD
ready_for_pilot
ready_for_broad_production
blocker_count
warning_count
gates
blockers
warnings
next_actions
reports
read_only_guarantees
```

### 2. ReleaseCandidateService

File mới:

```text
backend/app/services/release_candidate.py
```

Service gom các gate có sẵn:

```text
Production readiness
Security readiness
Performance readiness
UAT evidence pack
Pilot acceptance
```

### 3. UI /analytics/learning

Thêm panel:

```text
Pilot Release Candidate
```

Panel hiển thị:

```text
status
go_no_go
ready_for_pilot
ready_for_broad_production
blocker/warning count
gates
blockers
next actions
read-only guarantees
```

### 4. Script evidence RC

Thêm script:

```text
scripts/pilot-release-candidate-report.sh
```

Script xuất:

```text
release-candidate.json
readiness.json
security-readiness.json
performance-readiness.json
evidence-pack.json
PILOT_RELEASE_CANDIDATE_SUMMARY.md
```

### 5. Runtime/build/review integration

Cập nhật:

```text
scripts/uat-runtime-verify.sh
scripts/uat-build-gate.sh
scripts/claude-code-review-pack.sh
```

Runtime verify giờ probe thêm:

```text
/api/health/release-candidate
```

Claude review pack biết đến `ReleaseCandidateService` và RC script.

## Safety policy

Release Candidate gate là read-only:

```text
Không đọc raw tracking.log trong request
Không gọi Open edX/AP/OpenAI trong request
Không enqueue job hoặc recalculate
Không publish/rollback Bank Release
Không mutate database
Không kết luận vi phạm cá nhân
```

## Những bản trước được giữ nguyên

```text
.58 Security Production Hardening
.57 Performance Load Hardening
.56 Bank Release Publish Reliability + Rollback QA
.55 Analytics Course/Class Mapping Reliability
.54 RollNumber Identity Migration Assistant
.53 UAT Runtime Verification + Frontend Build Fix
.52 Claude Review Findings + Build Gate Hardening
.51 Claude Code Review Readiness Pack
.50 UAT Evidence Pack
.49 Pilot Acceptance UI
.48 Campus RBAC Audit Hardening
.47 Bank Quiz Final Test QA
.46 Analytics SLA Dashboard
.45 UAT RollNumber Cleanup
.44 Identity Reconciliation QA
.43 Production Readiness Gate Repair
.42 Bank Table Production UX
.40 CMS Student Username RollNumber Only
.37 Analytics Class Result Doctor
.36 Responsive Sidebar Shell Fix
.35 Analytics Post-Ingest Recalculate Orchestrator
```

## Deploy

```bash
cd /opt/ai-server
unzip -o ai-server-openedx-v25.9.16.7.2.64.13-pilot-release-candidate.zip -d /tmp/ai-server-v25.9.16.7.2.64.13
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
curl -sS 'https://api-ai.cms-test.poly.edu.vn/api/health/release-candidate?branch=poly&campus=ph&sample_limit=5' \
  -H 'Authorization: Bearer <TOKEN>' | jq
```

Xuất evidence:

```bash
API_BASE_URL=https://api-ai.cms-test.poly.edu.vn/api \
TOKEN='<TOKEN>' \
BRANCH=poly \
CAMPUS=ph \
CLASS_ID='<CLASS_ID>' \
OUT_DIR=/tmp/ai-pilot-rc-$(date +%Y%m%d-%H%M%S) \
./scripts/pilot-release-candidate-report.sh
```

## Kết quả kiểm thử trong artifact

```text
v59-specific tests: 5 passed
v57+v58+v59 selected regression: 14 passed
backend compileall: passed
bash syntax: passed
claude-code-review-pack: PASS, 0 failures, 0 warnings
uat-build-gate sandbox: WARN only because psycopg/frontend node_modules/Docker/.env.production are unavailable
```
