# CONTEXT DỰ ÁN AI SERVER / OPEN edX CMS — BASELINE v25.9.16.7.2.64.13

## Baseline mới nhất

```text
v25.9.16.7.2.64.13 — UAT Runtime Verification + Frontend Build Fix
zip: ai-server-openedx-v25.9.16.7.2.64.13-claude-review-findings-build-gate-hardening.zip
root: ai_server_openedx_v25_9_16_7_2_52
```

Bản `.52` tiếp tục từ `.51` và **không thêm nghiệp vụ mới**. Mục tiêu là làm chặt review/build gate để Claude AI hoặc senior reviewer kiểm tra code có bằng chứng rõ ràng.

## Không migration mới

Latest migration vẫn là:

```text
0052_v25_9_16_7_2_27_learning_behavior_logic_calibration.py
```

Không có `0053`/`0054`.

## Thay đổi chính của `.52`

### 1. UAT build gate mới

Thêm script:

```text
scripts/uat-build-gate.sh
```

Script này kiểm tra:

```text
- version sync trong config/package/docker/env/AppShell/README/RUN_CURRENT
- Alembic head guard, không có migration mới ngoài ý muốn
- backend python compileall
- dependency check cho pytest/psycopg
- targeted backend pytest khi đủ dependency
- frontend npm typecheck/build khi có frontend/node_modules
- Docker Compose config validation khi có Docker và .env.production
- optional Claude review pack khi RUN_REVIEW_PACK=1
```

Chạy UAT sign-off:

```bash
cd /opt/ai-server
OUT_DIR=/tmp/ai-server-uat-build-gate-$(date +%Y%m%d-%H%M%S) \
STRICT=1 \
RUN_FRONTEND_BUILD=1 \
RUN_REVIEW_PACK=1 \
./scripts/uat-build-gate.sh
```

Kết quả:

```text
build-gate-summary.json
BUILD_GATE_SUMMARY.md
py_compile.log
backend-targeted-tests.log
frontend-typecheck.log
frontend-build.log
claude-code-review-pack/review-summary.json
```

### 2. Nâng Claude review pack

`script/claude-code-review-pack.sh` được nâng để có thêm:

```text
runtime-dependency-status.json
frontend-typecheck-required.txt nếu artifact runtime không có frontend/node_modules
optional UAT build gate bằng INCLUDE_BUILD_GATE=1
shell syntax check cho scripts/uat-build-gate.sh
```

Chạy review pack:

```bash
cd /opt/ai-server
OUT_DIR=/tmp/ai-server-claude-review-$(date +%Y%m%d-%H%M%S) \
INCLUDE_BUILD_GATE=1 \
STRICT_BUILD_GATE=0 \
./scripts/claude-code-review-pack.sh
```

### 3. Docs mới

```text
RUN_V25_9_16_7_2_53.md
docs/CLAUDE_CODE_REVIEW_HANDOFF_V25_9_16_7_2_53.md
docs/RELEASE_v25.9.16.7.2.64.13_CLAUDE_REVIEW_FINDINGS_BUILD_GATE_HARDENING.md
```

## Quy tắc vẫn giữ nguyên

- Không fake dữ liệu.
- Không reset DB.
- Không xóa volume.
- Không sửa tay `alembic_version`.
- Không dùng wording cứng kiểu gian lận/cheating/vi phạm chắc chắn trên UI.
- Tác vụ analytics nặng phải chạy worker/job nền.
- RBAC phải enforce ở backend.
- Dashboard/readiness/evidence API là read-only.

## Các bản trước vẫn được giữ

```text
.51 Claude Code Review Readiness Pack
.50 UAT Evidence Pack
.49 Analytics Pilot Acceptance UI
.48 Campus RBAC Audit Hardening
.47 Bank Quiz Final Test Production QA
.46 Analytics SLA Dashboard
.45 UAT RollNumber Identity Cleanup
.44 RollNumber Identity Reconciliation QA
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
unzip -o ai-server-openedx-v25.9.16.7.2.64.13-claude-review-findings-build-gate-hardening.zip -d /tmp/ai-server-v25.9.16.7.2.64.13
rsync -a --delete /tmp/ai-server-v25.9.16.7.2.64.13/ai_server_openedx_v25_9_16_7_2_52/ /opt/ai-server/
docker compose -f docker-compose.prod.yml --env-file .env.production build backend frontend worker beat
docker compose -f docker-compose.prod.yml --env-file .env.production up -d --force-recreate backend frontend worker beat
```

Set version:

```env
APP_VERSION=25.9.16.7.2.64.13
NEXT_PUBLIC_APP_VERSION=25.9.16.7.2.64.13
```
