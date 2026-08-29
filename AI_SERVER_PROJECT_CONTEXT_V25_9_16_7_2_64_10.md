# CONTEXT DỰ ÁN AI SERVER / OPEN edX CMS — BASELINE v25.9.16.7.2.64.13

Ngôn ngữ làm việc: tiếng Việt. Vai trò: senior full-stack engineer / backend architect / frontend engineer / UX reviewer thực dụng cho AI Server + Open edX CMS FPT Polytechnic.

## Baseline mới nhất

```text
v25.9.16.7.2.64.13 — Academic AP Sync + External Assignment Workflow Split
zip: ai-server-openedx-v25.9.16.7.2.64.13-academic-ap-sync-external-assignment-workflow-split.zip
root: ai_server_openedx_v25_9_16_7_2_64_13
```

Bản `.64.10` tiếp tục từ `.64.9`, không có migration mới. Latest migration vẫn là:

```text
0052_v25_9_16_7_2_27_learning_behavior_logic_calibration.py
```

## Mục tiêu `.64.10`

1. Tiếp tục tách workflow còn lại theo hướng an toàn.
2. Tách AP sync/import orchestration khỏi `backend/app/api/routes/academic.py`.
3. Bỏ luồng nhập/sửa điểm Assignment trên AI Server vì điểm Assignment do hệ thống khác xử lý.
4. Giữ backward compatibility cho read-only display nếu DB đã có assignment snapshot cũ/được import.

## Thay đổi chính

### 1. Academic AP Sync workflow split

Module mới:

```text
backend/app/services/academic/ap_sync.py
```

Service mới:

```text
AcademicAPSyncWorkflowService
```

Đã chuyển orchestration khỏi route học vụ:

```text
sync_campuses_from_ap
get_sync_options
sync_from_json
enqueue_sync_from_ap_job
list_sync_jobs
get_sync_job
sync_from_ap
```

Route vẫn giữ response shape cũ, chỉ delegate sang workflow mới:

```text
backend/app/api/routes/academic.py
```

Không đổi `AcademicImportService`, Celery task, AP payload, sync run semantics, audit action names hoặc route URLs.

### 2. Externalize Assignment score entry

Module mới:

```text
backend/app/services/academic/assignment_external.py
```

Service mới:

```text
AcademicAssignmentExternalWorkflowService
```

Quy tắc mới:

```text
AI Server không còn nhập/sửa điểm Assignment.
Điểm Assignment do hệ thống khác xử lý.
AI Server chỉ đọc/hiển thị snapshot đã được đồng bộ nếu có.
```

Endpoint read-only vẫn còn:

```text
GET /api/academic/classes/{class_id}/assignment-defense-scores
```

Endpoint write bị khóa an toàn:

```text
PUT /api/academic/classes/{class_id}/assignment-defense-scores
→ HTTP 410
→ code: ASSIGNMENT_SCORE_EXTERNALIZED
```

Không xóa dữ liệu assignment score cũ trong DB.

### 3. RBAC update

Đã bỏ permission:

```text
academic.manage_assignment_scores
manage_assignment_scores legacy bridge
```

`BusinessRBACService.can_manage_assignment_scores_for_campus(...)` luôn trả `False`.

### 4. Frontend update

File chính:

```text
frontend/app/student-management/classes/[classId]/page.tsx
frontend/context/AppContext.tsx
```

Thay đổi:

```text
Không còn nút Workflow Assignment.
Không còn gọi saveAcademicClassAssignmentDefenseScores.
Không còn permission map manage_assignment_scores.
Hiển thị nhãn: Assignment: đọc từ hệ thống ngoài.
```

## Workflow split đã hoàn thành trước đó

```text
.64.1 Maintainability Service/UI Split Completion
.64.2 Academic Access/Roster Workflow Split
.64.3 Question Bank Release/Publish Workflow Split
.64.4 Analytics SLA/Evidence/Result Workflow Split
.64.5 Academic Sync/Enrollment Mutation Workflow Split
.64.6 Question Bank Quiz Creation/Auto-map Workflow Split
.64.7 Academic Identity Import/Reconciliation Workflow Split
.64.8 Teacher Report Cache/Training Report Workflow Split
.64.9 Question Bank Generation/Review Workflow Split
.64.10 Academic AP Sync + External Assignment Workflow Split
```

## Test/check

```text
v64.10-specific tests: 6 passed
selected v64.x regression: 62 passed
backend/app + Open edX connector + unit-reset compileall: passed
bash syntax: passed
claude-code-review-pack: PASS, failures=0, warnings=0
uat-build-gate sandbox: WARN only due missing deps/node_modules/Docker/env or skipped frontend/review
```

## Deploy

```bash
cd /opt/ai-server
unzip -o ai-server-openedx-v25.9.16.7.2.64.13-academic-ap-sync-external-assignment-workflow-split.zip -d /tmp/ai-server-v25.9.16.7.2.64.13
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
curl -sS 'https://api-ai.cms-test.poly.edu.vn/api/health/maintainability-contract' \
  -H 'Authorization: Bearer <TOKEN>' | jq

curl -sS 'https://api-ai.cms-test.poly.edu.vn/api/health/production-pilot-final?branch=poly&campus=ph&sample_limit=5' \
  -H 'Authorization: Bearer <TOKEN>' | jq
```

## Ghi chú trung thực

`.64.10` tách AP sync/import route orchestration và externalize Assignment score entry. Nó chưa tách toàn bộ AP import internals bên trong `AcademicImportService`; phần đó nên làm tiếp nếu cần theo `.64.11` hoặc `.64.12`, với integration tests riêng cho AP payload thật.
