# CONTEXT DỰ ÁN AI SERVER / OPEN edX CMS — BASELINE v25.9.16.7.2.50

## Baseline mới nhất

```text
v25.9.16.7.2.50 — Bank Quiz Final Test Production QA
zip: ai-server-openedx-v25.9.16.7.2.50-bank-quiz-final-test-production-qa.zip
root trong zip: ai_server_openedx_v25_9_16_7_2_47
```

Bản `.44` tiếp tục từ `.43` và **không có Alembic migration mới**. Latest migration vẫn là:

```text
0052_v25_9_16_7_2_27_learning_behavior_logic_calibration.py
```

## Mục tiêu bản .44

Sau `.40`, sinh viên được tạo/check tài khoản CMS/Open edX bằng `RollNumber/student_code` thay vì AP username/email. Ví dụ:

```text
AcademicStudent.username     = duongcvph59017@fpt.edu.vn
AcademicStudent.student_code = PH59017
CMS/Open edX username chuẩn  = ph59017
```

Rủi ro production: trước đây hệ thống có thể đã từng tạo user CMS bằng AP username/email cũ. Nếu chạy enrollment/sync diện rộng ngay có thể tạo trùng người học hoặc lấy nhầm tiến độ. Bản `.44` thêm audit/dry-run để phát hiện các trường hợp legacy/duplicate/missing trước khi vận hành rộng.

## Thay đổi chính

### 1. Backend identity reconciliation endpoint

Thêm endpoint read-only:

```text
GET /api/academic/classes/{class_id}/identity-reconciliation
```

Query params:

```text
status_filter=all | OK | LEGACY_AP_USERNAME | MISSING_MAPPING | READY_FOR_ROLLNUMBER | MISSING_ROLLNUMBER | DUPLICATE_ROLLNUMBER | DUPLICATE_CMS_MAPPING | CMS_USERNAME_MISMATCH | CANONICAL_INACTIVE
page=1
page_size=200
```

Endpoint dùng `_require_academic_sync_permission`, enforce scope class qua `AcademicService.assert_can_access_class(...)`.

### 2. Payload trả về

```json
{
  "ok": true,
  "class_id": "...",
  "class_code": "COM1071.01",
  "status": "ready | needs_sync | blocked",
  "message": "...",
  "policy": "rollnumber_canonical_username",
  "dry_run": true,
  "mutation_performed": false,
  "counts": {
    "total": 15,
    "ok": 10,
    "blocker": 1,
    "warning": 4,
    "legacy_ap_username": 1,
    "missing_mapping": 3,
    "ready_for_rollnumber": 1
  },
  "items": [
    {
      "student_code": "PH59017",
      "ap_username": "duongcvph59017@fpt.edu.vn",
      "canonical_username": "ph59017",
      "openedx_username": "duongcvph59017@fpt.edu.vn",
      "status": "LEGACY_AP_USERNAME",
      "severity": "blocker",
      "recommended_action": "review_legacy_user_before_rollnumber_sync"
    }
  ],
  "next_actions": []
}
```

### 3. Status codes

```text
OK
READY_FOR_ROLLNUMBER
MISSING_MAPPING
LEGACY_AP_USERNAME
MISSING_ROLLNUMBER
DUPLICATE_ROLLNUMBER
DUPLICATE_CMS_MAPPING
CMS_USERNAME_MISMATCH
CANONICAL_INACTIVE
```

Ý nghĩa quan trọng:

- `OK`: mapping đang dùng đúng RollNumber canonical và có thể enroll.
- `READY_FOR_ROLLNUMBER`: có RollNumber, chưa có mapping/mapping chưa check; có thể chạy Đồng bộ full CMS nếu không có blocker khác.
- `MISSING_MAPPING`: chưa có mapping CMS.
- `LEGACY_AP_USERNAME`: mapping hiện tại đang dùng AP username/email cũ; cần review trước khi tạo user RollNumber để tránh trùng.
- `MISSING_ROLLNUMBER`: thiếu `student_code`, không thể tạo username CMS chuẩn FEID.
- `DUPLICATE_ROLLNUMBER`: trùng RollNumber trong roster/class, phải làm sạch AP.
- `DUPLICATE_CMS_MAPPING`: nhiều mapping trỏ cùng canonical username.
- `CMS_USERNAME_MISMATCH`: mapping CMS không khớp RollNumber cũng không khớp AP username.
- `CANONICAL_INACTIVE`: username đúng RollNumber nhưng user CMS inactive.

### 4. UI chi tiết lớp

Trang:

```text
/student-management/classes/{class_id}
```

Thêm panel:

```text
Kiểm tra identity CMS/RollNumber
```

Panel hiển thị:

```text
Tổng dòng
Sẵn sàng
Blocker
Cảnh báo
Legacy AP username
Thiếu mapping
Việc cần làm tiếp theo
5 dòng mẫu để kiểm tra nhanh
```

Có bộ lọc:

```text
Tất cả
Sẵn sàng
Legacy AP username
Chưa có mapping
Sẵn sàng tạo RollNumber
Thiếu RollNumber
Trùng RollNumber
Sai username CMS
```

### 5. Production-safety

Bản `.44` **không mutate dữ liệu**:

```text
dry_run = true
mutation_performed = false
```

Không tự sửa mapping, không xóa user cũ, không đổi user Open edX. Đây là bước audit để admin biết có an toàn chạy Đồng bộ full CMS/Ghi danh CMS diện rộng hay chưa.

## Giữ nguyên từ các bản trước

```text
.43 Production Readiness Gate Repair
.42 Bank Table Production UX + Bulk Workflow QA
.41 Bank Entity Actions Visible Fix
.40 CMS Student Username RollNumber Only
.37 Analytics Class Result Doctor
.36 Responsive Sidebar Shell Fix
.35 Analytics Post-Ingest Recalculate Orchestrator
```

## Deploy

```bash
cd /opt/ai-server

unzip -o ai-server-openedx-v25.9.16.7.2.50-bank-quiz-final-test-production-qa.zip -d /tmp/ai-server-v25.9.16.7.2.50

rsync -a --delete /tmp/ai-server-v25.9.16.7.2.50/ai_server_openedx_v25_9_16_7_2_47/ /opt/ai-server/

docker compose -f docker-compose.prod.yml --env-file .env.production build backend frontend worker beat

docker compose -f docker-compose.prod.yml --env-file .env.production up -d --force-recreate backend frontend worker beat
```

Set version:

```env
APP_VERSION=25.9.16.7.2.50
NEXT_PUBLIC_APP_VERSION=25.9.16.7.2.50
```

## Verify sau deploy

```bash
curl -sS 'https://api-ai.cms-test.poly.edu.vn/api/academic/classes/<CLASS_ID>/identity-reconciliation?page_size=200' \
  -H 'Authorization: Bearer <TOKEN>' | jq
```

Kỳ vọng với ví dụ FEID/AP:

```text
RollNumber PH59017 -> canonical_username ph59017
AP username duongcvph59017@fpt.edu.vn chỉ là alias
Nếu openedx_username hiện tại còn duongcvph59017@fpt.edu.vn -> LEGACY_AP_USERNAME/blocker
Nếu openedx_username là ph59017 -> OK
```

## Test đã chạy trong artifact build

```text
51 passed
py_compile passed cho backend/app/services/academic_service.py, backend/app/api/routes/academic.py, backend/app/schemas/academic.py
```

Full backend collection vẫn có thể bị chặn trong môi trường thiếu `psycopg`. Frontend typecheck không chạy trong artifact runtime vì không có `frontend/node_modules`.
