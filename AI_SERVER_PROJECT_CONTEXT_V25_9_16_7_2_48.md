# CONTEXT DỰ ÁN AI SERVER / OPEN edX CMS — BASELINE v25.9.16.7.2.50

## Baseline mới nhất

```text
v25.9.16.7.2.50 — Campus RBAC Audit Hardening
zip: ai-server-openedx-v25.9.16.7.2.50-campus-rbac-audit-hardening.zip
root: ai_server_openedx_v25_9_16_7_2_48
```

Bản `.48` tiếp tục từ `.47` và tập trung đóng rủi ro phân quyền campus/scope ở backend cho UAT/production. Không có migration mới.

Latest migration vẫn là:

```text
0052_v25_9_16_7_2_27_learning_behavior_logic_calibration.py
```

## Vấn đề bản này xử lý

Frontend ẩn menu/nút không đủ an toàn. Các job/report/export chạy nền có thể bị xem lại hoặc tải file nếu endpoint list/detail/download không kiểm tra scope thật. Với campus-scoped operators, all-campus job/export cũng có thể materialize dữ liệu ngoài scope nếu không bắt chọn campus cụ thể.

## Thay đổi chính

### 1. Business RBAC campus/scope helpers

Trong `backend/app/services/business_rbac.py` thêm:

```text
normalize_campus_code(...)
campus_scope_for_user(...)
can_access_campus(...)
require_campus_access(...)
ensure_requested_campus_filter_allowed(...)
can_access_academic_scope(...)
require_academic_scope(...)
```

Mục tiêu:

- Normalize campus code trước khi so sánh.
- SYSTEM_ADMIN vẫn unrestricted.
- CAMPUS_MANAGER scope `CAMPUS:ph` chỉ thao tác trong `ph`.
- CAMPUS_MANAGER scope `CAMPUS:*` hoặc `SYSTEM` thấy toàn bộ.
- Job campus trống là broad job; user campus-scoped không được xem job broad của người khác.
- Job do chính actor tạo trong scope hợp lệ vẫn xem được để không mất workflow UAT.

### 2. Teacher report job/export hardening

Trong `backend/app/api/routes/academic.py`:

- `POST /api/academic/training/teachers/report-cache/jobs`
- `POST /api/academic/training/teachers/export/jobs`
- `GET /api/academic/training/teachers/report-jobs`
- `GET /api/academic/training/teachers/report-jobs/{job_id}`
- `GET /api/academic/training/teachers/report-jobs/{job_id}/download`

Đã harden:

- CAMPUS_MANAGER scope hẹp phải chọn `campus` cụ thể khi tạo report/export job.
- Job list lọc fail-closed bằng `can_access_academic_scope(...)`.
- Job detail/download gọi `require_academic_scope(...)`.
- `request_json` của job lưu:
  - `requester_context`
  - `approved_campus_codes`
  - `campus_scope_unrestricted`
  - `scope_enforced_by_backend`

### 3. Bulk Auto map tất cả job hardening

Trong:

```text
POST /api/academic/subjects/course-mapping/auto-all-sync/jobs
GET  /api/academic/bulk-operation-jobs
GET  /api/academic/bulk-operation-jobs/{job_id}
```

Đã harden:

- CAMPUS_MANAGER scope hẹp phải chọn campus cụ thể trước khi chạy job.
- Active job reuse chỉ dùng nếu job đó cũng visible với actor hiện tại.
- List/detail job lọc theo scope.
- `request_json` lưu approved campus/class/subject scope.

### 4. Class sync job request scope audit

Các class sync jobs lưu thêm:

```text
approved_class_id
approved_campus_codes
approved_branch
scope_enforced_by_backend
```

Áp dụng cho:

```text
cms_sync_check
cms_enrollment_sync
learning_sync
full_cms_sync
```

### 5. Scope audit endpoint

Thêm endpoint:

```text
GET /api/rbac/scope-audit
```

Trả về:

```text
user_id/email/username
legacy_role
is_system_admin
permissions
campus_scope
academic_scope
bank_scope
assignments
backend_enforced=true
```

Dùng để debug nhanh một token/operator đang thấy gì trước khi mở `/student-management`, `/teacher-management`, `/analytics/learning`, `/jobs`, `/audit`.

## Giữ nguyên từ các bản trước

- `.47` Bank Quiz Final Test Production QA.
- `.46` Analytics SLA Dashboard + Job Observability.
- `.45` UAT RollNumber Identity Cleanup.
- `.44` RollNumber Identity Reconciliation QA.
- `.43` Production Readiness Gate Repair.
- `.42` Bank Table Production UX + Bulk Workflow QA.
- `.40` CMS Student Username RollNumber Only.
- `.37` Analytics Class Result Doctor.
- `.36` Responsive Sidebar Shell Fix.
- `.35` Analytics Post-Ingest Recalculate Orchestrator.

## Test đã chạy trong artifact

```text
95 passed
py_compile passed cho business_rbac.py, academic.py, rbac.py, config.py
```

Full test collection vẫn có thể bị chặn ở môi trường không có `psycopg`, giống các bản trước. Frontend typecheck chưa chạy vì artifact/runtime không có `frontend/node_modules`.

## Deploy

```bash
cd /opt/ai-server
unzip -o ai-server-openedx-v25.9.16.7.2.50-campus-rbac-audit-hardening.zip -d /tmp/ai-server-v25.9.16.7.2.50
rsync -a --delete /tmp/ai-server-v25.9.16.7.2.50/ai_server_openedx_v25_9_16_7_2_48/ /opt/ai-server/
docker compose -f docker-compose.prod.yml --env-file .env.production build backend frontend worker beat
docker compose -f docker-compose.prod.yml --env-file .env.production up -d --force-recreate backend frontend worker beat
```

Set version:

```env
APP_VERSION=25.9.16.7.2.50
NEXT_PUBLIC_APP_VERSION=25.9.16.7.2.50
```

## Verify nhanh

```bash
curl -sS 'https://api-ai.cms-test.poly.edu.vn/api/rbac/scope-audit' \
  -H 'Authorization: Bearer <TOKEN>' | jq

curl -sS 'https://api-ai.cms-test.poly.edu.vn/api/academic/training/teachers/report-jobs?status=all' \
  -H 'Authorization: Bearer <TOKEN>' | jq

curl -sS 'https://api-ai.cms-test.poly.edu.vn/api/academic/bulk-operation-jobs?status=all' \
  -H 'Authorization: Bearer <TOKEN>' | jq
```

Expected:

- SYSTEM_ADMIN unrestricted.
- CAMPUS_MANAGER `ph` chỉ thấy scope `ph`.
- CAMPUS_MANAGER scope hẹp không tạo được all-campus teacher report/export hoặc all-campus Auto map tất cả.
- Job/report ngoài scope trả 403 khi xem detail/download.
