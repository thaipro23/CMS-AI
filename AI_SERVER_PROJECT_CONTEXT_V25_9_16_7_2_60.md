# CONTEXT DỰ ÁN AI SERVER / OPEN edX CMS — BASELINE v25.9.16.7.2.64.13

Ngôn ngữ làm việc: tiếng Việt. Vai trò: senior full-stack engineer / backend architect / frontend engineer / UX reviewer thực dụng cho AI Server + Open edX CMS FPT Polytechnic.

## Baseline mới nhất

```text
v25.9.16.7.2.64.13 — Pilot Operations Runbook + Rollback Gate
zip: ai-server-openedx-v25.9.16.7.2.64.13-pilot-operations-runbook-rollback-gate.zip
root: ai_server_openedx_v25_9_16_7_2_64_13
```

Bản `.60` tiếp tục từ `.59` và không có migration mới. Latest migration vẫn là:

```text
0052_v25_9_16_7_2_27_learning_behavior_logic_calibration.py
```

## Mục tiêu `.60`

`.59` đã có Pilot Release Candidate gate để trả lời “có thể pilot không?”. `.60` biến kết quả đó thành runbook vận hành pilot có thể dùng thật: preflight, deploy window, warm-up, monitoring, rollback triggers, evidence required và sign-off.

## Thay đổi chính

### Backend

Thêm service:

```text
backend/app/services/pilot_operations.py
```

Thêm endpoint read-only:

```text
GET /api/health/pilot-operations
```

Endpoint này compose từ `ReleaseCandidateService` và trả về:

```text
status: PILOT_READY | PILOT_WITH_MONITORING | HOLD
decision: GO_PILOT | GO_CONTROLLED_PILOT | NO_GO
release_candidate_summary
phases
monitoring_cadence
rollback_triggers
evidence_required
signoff
blockers
warnings
next_actions
read_only_guarantees
```

### Frontend

`/analytics/learning` có panel mới:

```text
Pilot operations runbook
```

Panel hiển thị:

```text
- status / decision
- ready_for_pilot
- ready_for_broad_production
- RC status
- số phase
- số rollback trigger
- phase checklist
- rollback triggers
- next actions
- read-only guarantees
```

### Scripts

Thêm:

```text
scripts/pilot-operations-runbook.sh
```

Script xuất:

```text
pilot-operations.json
release-candidate.json
PILOT_OPERATIONS_RUNBOOK.md
```

Đã cập nhật:

```text
scripts/uat-runtime-verify.sh
scripts/uat-build-gate.sh
scripts/claude-code-review-pack.sh
```

để kiểm tra thêm pilot operations gate.

## Safety/read-only guarantees

Bản `.60` không làm việc nguy hiểm:

```text
Không đọc raw tracking.log trong request
Không gọi Open edX/AP/OpenAI trong request
Không enqueue job hoặc recalculate
Không publish/rollback Bank Release
Không mutate database
Không kết luận vi phạm cá nhân
```

## Deploy

```bash
cd /opt/ai-server
unzip -o ai-server-openedx-v25.9.16.7.2.64.13-pilot-operations-runbook-rollback-gate.zip -d /tmp/ai-server-v25.9.16.7.2.64.13
rsync -a --delete /tmp/ai-server-v25.9.16.7.2.64.13/ai_server_openedx_v25_9_16_7_2_64_13/ /opt/ai-server/
docker compose -f docker-compose.prod.yml --env-file .env.production build backend frontend worker beat
docker compose -f docker-compose.prod.yml --env-file .env.production up -d --force-recreate backend frontend worker beat
```

Env:

```env
APP_VERSION=25.9.16.7.2.64.13
NEXT_PUBLIC_APP_VERSION=25.9.16.7.2.64.13
```

## Verify

```bash
curl -sS 'https://api-ai.cms-test.poly.edu.vn/api/health/pilot-operations?branch=poly&campus=ph&sample_limit=5' \
  -H 'Authorization: Bearer <TOKEN>' | jq
```

Xuất runbook:

```bash
cd /opt/ai-server
API_BASE_URL=https://api-ai.cms-test.poly.edu.vn/api \
TOKEN='<TOKEN>' \
BRANCH=poly \
CAMPUS=ph \
CLASS_ID='<CLASS_ID>' \
OUT_DIR=/tmp/ai-pilot-operations-$(date +%Y%m%d-%H%M%S) \
./scripts/pilot-operations-runbook.sh
```

## Kết quả kiểm tra trong artifact

```text
v60 + selected v57/v58/v59 regression: 19 passed
backend compileall: passed
bash syntax: passed
claude-code-review-pack: PASS, failures=0, warnings=0
uat-build-gate sandbox: WARN do thiếu psycopg/frontend node_modules/Docker/.env.production trong sandbox
```

## Các baseline trước được giữ nguyên

```text
.59 Pilot Release Candidate
.58 Security Production Hardening
.57 Performance Load Hardening
.56 Bank Release Publish Reliability + Rollback QA
.55 Analytics Course/Class Mapping Reliability
.54 RollNumber Identity Migration Assistant
.53 UAT Runtime Verification + Frontend Build Fix
.52 Claude Review Findings + Build Gate
.51 Claude Review Readiness Pack
.50 UAT Evidence Pack
.49 Pilot Acceptance UI
.48 Campus RBAC Audit Hardening
.47 Bank Quiz Final Test QA
.46 Analytics SLA Dashboard
.45 UAT RollNumber cleanup
.44 identity reconciliation QA
.42 Bank table UX
.40 CMS student username RollNumber only
.37 Analytics class result doctor
.36 responsive sidebar shell fix
.35 post-ingest recalculate orchestrator
```
