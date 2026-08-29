# CONTEXT DỰ ÁN AI SERVER / OPEN edX CMS — BASELINE v25.9.16.7.2.50

## Baseline mới nhất

```text
v25.9.16.7.2.50 — UAT Evidence Pack + Acceptance Report Export
zip: ai-server-openedx-v25.9.16.7.2.50-uat-evidence-pack-report-export.zip
root: ai_server_openedx_v25_9_16_7_2_50
```

Bản `.49` tiếp tục từ `.48` và **không có migration mới**. Latest migration vẫn là:

```text
0052_v25_9_16_7_2_27_learning_behavior_logic_calibration.py
```

## Mục tiêu bản .49

Sau `.46` đã có SLA dashboard, `.47` đã QA Bank Quiz/Final test, `.48` đã harden Campus RBAC backend, bản `.49` đưa bước **pilot acceptance/UAT acceptance** lên UI và thêm script smoke test để admin không phải tự đọc Docker log hoặc ghép nhiều curl thủ công.

## Thay đổi chính

### 1. UI `/analytics/learning`

Thêm panel:

```text
Kiểm thử pilot UAT
```

Panel gọi endpoint sẵn có:

```text
GET /api/analytics/ops/pilot-acceptance
```

Panel hiển thị:

- `pilot_status`
- `ready_for_pilot`
- `ready_for_broad_production`
- số checklist đạt/tổng
- số blocker
- số cảnh báo
- lớp mẫu
- sinh viên mẫu
- checklist kỹ thuật
- lớp pilot cần chú ý
- việc tiếp theo

Panel là **read-only**:

- không enqueue job
- không recalculate trong request
- không đọc raw `tracking.log`
- không mutate dữ liệu
- không dùng wording kết luận vi phạm cá nhân

### 2. Script UAT smoke runner

Thêm:

```text
scripts/analytics-uat-acceptance.sh
```

Script kiểm tra một lượt:

```text
/api/health/build
/api/health/readiness
/api/rbac/scope-audit
/api/analytics/ops/sla
/api/analytics/ops/pilot-acceptance
/api/analytics/classes/{class_id}/doctor  # nếu truyền CLASS_ID
```

Ví dụ chạy UAT:

```bash
cd /opt/ai-server
API_BASE_URL=https://api-ai.cms-test.poly.edu.vn/api \
TOKEN='<TOKEN>' \
BRANCH=poly \
CAMPUS=ph \
CLASS_ID='<CLASS_ID>' \
./scripts/analytics-uat-acceptance.sh
```

## Kế thừa từ các bản trước

- `.48` Campus RBAC Audit Hardening
- `.47` Bank Quiz Final Test Production QA
- `.46` Analytics SLA Dashboard + Job Observability
- `.45` UAT RollNumber Identity Cleanup
- `.44` RollNumber Identity Reconciliation QA
- `.43` Production Readiness Gate Repair
- `.42` Bank Table Production UX + Bulk Workflow QA
- `.41` Bank Entity Actions Visible Fix
- `.40` CMS Student Username RollNumber Only
- `.37` Analytics Class Result Doctor + Production Readiness Repair
- `.36` Responsive Sidebar Shell Fix
- `.35` Analytics Post-Ingest Recalculate Orchestrator

## Deploy

```bash
cd /opt/ai-server
unzip -o ai-server-openedx-v25.9.16.7.2.50-uat-evidence-pack-report-export.zip -d /tmp/ai-server-v25.9.16.7.2.50
rsync -a --delete /tmp/ai-server-v25.9.16.7.2.50/ai_server_openedx_v25_9_16_7_2_50/ /opt/ai-server/
docker compose -f docker-compose.prod.yml --env-file .env.production build backend frontend worker beat
docker compose -f docker-compose.prod.yml --env-file .env.production up -d --force-recreate backend frontend worker beat
```

Set version:

```env
APP_VERSION=25.9.16.7.2.50
NEXT_PUBLIC_APP_VERSION=25.9.16.7.2.50
```

## Test đã chạy trong artifact build

```text
67 passed  # targeted static regression .34 → .49
17 passed  # focused .46/.47/.48/.49 subset
py_compile passed for changed backend route/config files
bash -n passed for scripts/analytics-uat-acceptance.sh
```

Lưu ý: full backend collection trong môi trường artifact vẫn có thể bị chặn bởi thiếu `psycopg`; frontend typecheck không chạy vì không có `frontend/node_modules`.
