# Release v25.9.16.7.2.64.16.5.7.2.16 — AP Sync Selected Subject Scope

## Mục tiêu

`/ap-sync` không còn lấy toàn bộ danh mục `/get-course` rồi gọi `/get-data-cms` cho mọi môn. Phạm vi đồng bộ được lấy từ `/subject-management` của đúng học kỳ và hệ.

Một môn chỉ được đưa vào AP sync khi các Block đang hoạt động của môn trong học kỳ được chọn nhất quán là `cms` hoặc nhất quán là `udemy`. Môn `Chưa chọn`, môn dữ liệu cũ `mixed`, hoặc môn chỉ được chọn một phần Block bị loại khỏi phạm vi cho tới khi quản trị viên xử lý lại tại Quản lý môn học.

## Contract backend

- `AcademicAPSyncWorkflowService._selected_subject_scope()` đọc trực tiếp `AcademicSubjectDelivery` + `AcademicSubject` + `AcademicTerm`.
- `enqueue_sync_from_ap_job()` chụp danh sách `subject_codes` cụ thể trước khi tính request fingerprint.
- Client gửi mã môn cụ thể vẫn bị backend kiểm tra; mã chưa chọn CMS/Udemy trả HTTP 422.
- Không có môn hợp lệ trả HTTP 422 thay vì fallback sang toàn bộ AP catalog.
- Worker mới yêu cầu job có `subject_codes` bất biến. Job legacy không fingerprint được resolve lại theo Subject Management; tuyệt đối không expand request rỗng thành toàn bộ `/get-course`.
- Không đổi database schema; Alembic head giữ `0059_v25_9_16_7_2_64_37`.

## Contract frontend

Trang `/ap-sync` hiển thị:

- tổng môn thực sự được đồng bộ;
- số môn CMS;
- số môn Udemy;
- số môn của hệ đang chọn;
- cảnh báo khi chưa chọn nền tảng cho môn nào.

Nút đồng bộ bị disable nếu hệ không có cơ sở hoặc không có môn CMS/Udemy. Dialog xác nhận hiển thị số môn sẽ chạy.

## Version

Current application version: `25.9.16.7.2.64.16.5.7.2.16`.
