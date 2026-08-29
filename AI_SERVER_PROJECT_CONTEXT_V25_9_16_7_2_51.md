# CONTEXT DỰ ÁN AI SERVER / OPEN edX CMS — BASELINE v25.9.16.7.2.51

## Baseline mới nhất

```text
v25.9.16.7.2.51 — Claude Code Review Readiness Pack
zip: ai-server-openedx-v25.9.16.7.2.51-claude-code-review-readiness-pack.zip
root: ai_server_openedx_v25_9_16_7_2_51
```

Bản `.51` tiếp tục từ `.50`, không thêm nghiệp vụ lớn. Mục tiêu là chuẩn bị artifact để Claude AI hoặc senior reviewer kiểm tra code có bằng chứng, manifest và guardrail rõ ràng.

## Không có migration mới

Latest migration vẫn là:

```text
0052_v25_9_16_7_2_27_learning_behavior_logic_calibration.py
```

## Thay đổi chính trong `.51`

1. Thêm script:

```text
scripts/claude-code-review-pack.sh
```

2. Script xuất gói review gồm:

```text
review-summary.json
CLAUDE_REVIEW_BRIEF.md
file-manifest.json
banned-wording-source.txt
dangerous-commands.txt
routes-raw-trackinglog.txt
backend-routes.txt
versioned-tests.txt
frontend-source-files.txt
```

3. Static gates trong review pack:

```text
- Version sync trong config/package/docker/env/AppShell/README/RUN_CURRENT.
- Alembic latest 0052 vẫn tồn tại.
- Không có migration 0053/0054 ngoài ý muốn.
- Không có wording cứng gian lận/cheating/vi phạm chắc chắn trong source.
- Không có command phá dữ liệu rõ ràng trong scripts/source.
- Không có raw tracking.log scanner trực tiếp trong API routes.
- python -m compileall backend/app pass.
- bash -n cho helper scripts pass.
```

4. Thêm docs:

```text
docs/CLAUDE_CODE_REVIEW_HANDOFF_V25_9_16_7_2_51.md
docs/RELEASE_v25.9.16.7.2.51_CLAUDE_CODE_REVIEW_READINESS_PACK.md
RUN_V25_9_16_7_2_51.md
```

5. Cập nhật static tests để assert `.51` là current version:

```text
backend/app/tests/test_v25_9_16_7_2_51_claude_code_review_pack.py
```

## Kết quả verify trong artifact build

```text
Targeted versioned/static regression: 86 passed
claude-code-review-pack: PASS, 0 failures, 0 warnings, 15 passes
py_compile backend/app: passed
bash -n review/evidence scripts: passed
```

Full backend collection vẫn có thể bị chặn trong môi trường thiếu `psycopg`, giống các bản trước.

## Các baseline quan trọng vẫn giữ nguyên

```text
.50 UAT Evidence Pack + Acceptance Report Export
.49 Analytics Pilot Acceptance UI + UAT Smoke Runner
.48 Campus RBAC Audit Hardening
.47 Bank Quiz Final Test Production QA
.46 Analytics SLA Dashboard + Job Observability
.45 UAT RollNumber Identity Cleanup
.44 RollNumber Identity Reconciliation QA
.43 Production Readiness Gate Repair
.42 Bank Table Production UX + Bulk Workflow QA
.40 CMS Student Username RollNumber Only
.37 Analytics Class Result Doctor
.36 Responsive Sidebar Shell Fix
.35 Analytics Post-Ingest Recalculate Orchestrator
```

## Cách chạy review pack cho Claude

```bash
cd /opt/ai-server
OUT_DIR=/tmp/ai-server-claude-review-$(date +%Y%m%d-%H%M%S) \
./scripts/claude-code-review-pack.sh
```

Mở trước:

```text
review-summary.json
CLAUDE_REVIEW_BRIEF.md
file-manifest.json
banned-wording-source.txt
dangerous-commands.txt
routes-raw-trackinglog.txt
```

## Deploy

```bash
cd /opt/ai-server
unzip -o ai-server-openedx-v25.9.16.7.2.51-claude-code-review-readiness-pack.zip -d /tmp/ai-server-v25.9.16.7.2.51
rsync -a --delete /tmp/ai-server-v25.9.16.7.2.51/ai_server_openedx_v25_9_16_7_2_51/ /opt/ai-server/
docker compose -f docker-compose.prod.yml --env-file .env.production build backend frontend worker beat
docker compose -f docker-compose.prod.yml --env-file .env.production up -d --force-recreate backend frontend worker beat
```

Env:

```env
APP_VERSION=25.9.16.7.2.51
NEXT_PUBLIC_APP_VERSION=25.9.16.7.2.51
```
