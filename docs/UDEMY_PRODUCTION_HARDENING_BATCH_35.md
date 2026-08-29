# Batch 35 — Udemy Production Hardening

## Phạm vi

Batch 35 tiếp tục trực tiếp từ Batch 34 canonical và chỉ harden luồng Udemy hiện có.

**Không triển khai chuyển đổi, import hoặc migration dữ liệu từ Laravel ACMS cũ.** Không đọc các nguồn `subject.is_udemy`, `subject.items`, `deadline_week*`, `percent_week*` hoặc `grade_report_udemy`.

## Thay đổi chính

### 1. Upload/import workbook an toàn hơn

- Giới hạn số file, dung lượng từng file, tổng dung lượng và số dòng bằng cấu hình.
- Kiểm tra phần mở rộng và Content-Type của `.xlsx`.
- Kiểm tra chữ ký ZIP/OpenXML, thành phần bắt buộc, đường dẫn nội bộ, file mã hóa, số entry, tổng dung lượng giải nén và tỷ lệ nén bất thường.
- Rate limit Redis cho upload và retry. Production/UAT hardened fail closed nếu Redis không khả dụng.
- Giữ nguyên idempotency `subject_delivery_id + SHA-256`; không tạo sinh viên từ workbook.

### 2. Worker resilience

- Import và export chạy trên queue `exports` của `worker-heavy`.
- `acks_late`, `reject_on_worker_lost` và retry exponential cho lỗi hạ tầng tạm thời.
- Job persistent trong PostgreSQL; F5/đóng tab không làm dừng tác vụ.
- Healthcheck Celery ping đúng node `worker@<hostname>`, `worker-heavy@<hostname>` và `worker-analytics@<hostname>`.

### 3. Export nền

API mới:

```http
POST /api/academic/subject-deliveries/{delivery_id}/udemy-progress/export-jobs
GET  /api/academic/udemy/progress/export-jobs/{job_id}/download
```

- Frontend tạo job nền, tự tiếp tục theo dõi job active sau F5 và tải file khi hoàn tất.
- Job trùng cùng người dùng + cùng delivery/filter/scope được reuse khi đang queued/running.
- Worker re-resolve RBAC tại thời điểm chạy; quyền bị thu hồi sẽ không được dùng scope cũ.
- Tài khoản giới hạn lớp chỉ tải job do chính mình tạo và vẫn phải còn quyền với toàn bộ class trong report.
- Endpoint export đồng bộ cũ chỉ cho phép tối đa `ACADEMIC_UDEMY_SYNC_EXPORT_MAX_ROWS`; báo cáo lớn trả mã `UDEMY_EXPORT_REQUIRES_BACKGROUND_JOB`.

### 4. Retention

- Import/error artifact mặc định lưu 72 giờ.
- Export artifact mặc định lưu 48 giờ.
- Celery Beat chạy cleanup định kỳ, mặc định mỗi 6 giờ.
- Cleanup không xóa thư mục nguồn của import đang queued/running.
- Bản ghi job/audit vẫn giữ trong PostgreSQL; chỉ file local hết hạn bị xóa.

### 5. Hiệu năng database

Migration `0057_v25_9_16_7_2_64_35` chỉ thêm index:

```text
(subject_delivery_id, class_id)
(subject_delivery_id, match_status, progress_percent)
(subject_delivery_id, last_imported_at)
```

Migration này không chuyển đổi hoặc chỉnh sửa dữ liệu ACMS cũ.

## Cấu hình mới

```env
ACADEMIC_UDEMY_IMPORT_MAX_FILES=50
ACADEMIC_UDEMY_IMPORT_MAX_FILE_BYTES=20971520
ACADEMIC_UDEMY_IMPORT_MAX_TOTAL_BYTES=209715200
ACADEMIC_UDEMY_IMPORT_MAX_ROWS=300000
ACADEMIC_UDEMY_XLSX_MAX_ENTRIES=10000
ACADEMIC_UDEMY_XLSX_MAX_UNCOMPRESSED_BYTES=419430400
ACADEMIC_UDEMY_XLSX_MAX_COMPRESSION_RATIO=200
ACADEMIC_UDEMY_UPLOAD_RATE_LIMIT_PER_MINUTE=6
ACADEMIC_UDEMY_FILE_RETENTION_HOURS=72
ACADEMIC_UDEMY_EXPORT_FILE_RETENTION_HOURS=48
ACADEMIC_UDEMY_SYNC_EXPORT_MAX_ROWS=5000
ACADEMIC_UDEMY_WORKER_MAX_RETRIES=3
ACADEMIC_UDEMY_CLEANUP_INTERVAL_SECONDS=21600
```

## UAT bắt buộc

1. Chạy migration lên head 0057 và xác nhận ba index tồn tại.
2. Import file hợp lệ; xác nhận duplicate không nhân đôi snapshot.
3. Thử file sai Content-Type, file giả `.xlsx`, file quá giới hạn và workbook có cấu trúc ZIP nguy hiểm.
4. Tạo export có filter/class/scope; F5 trong khi chạy; xác nhận job tiếp tục và tải đúng workbook.
5. Đăng nhập teacher/campus owner; xác nhận không đọc hoặc tải report ngoài scope.
6. Dừng tạm Redis/PostgreSQL hoặc worker trong môi trường kiểm thử có kiểm soát; xác nhận retry và trạng thái job không mất.
7. Chạy Beat cleanup với artifact test đã hết hạn; xác nhận không xóa nguồn của job active.
8. Mở class CMS và chạy luồng CMS/Open edX cũ; xác nhận không regression.
9. Mở class Udemy; xác nhận không phát sinh mapping/enrollment/analytics Open edX.
10. Kiểm tra responsive tại 1440, 1366, 1024, 768 và 390 px.

## Không nằm trong Batch 35

- Chuyển dữ liệu Laravel ACMS cũ.
- Reset database hoặc xóa volume.
- Thay đổi connector Open edX, Unit Reset hoặc Learning MFE.
- Tuyên bố production accepted trước khi hoàn tất Docker build, migration thật, Celery/Redis thật và browser UAT.
