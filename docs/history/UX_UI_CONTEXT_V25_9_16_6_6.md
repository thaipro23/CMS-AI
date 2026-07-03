# UX/UI Context v25.9.16.6.6

## Mục tiêu UI
Thêm dashboard `/analytics/learning` để quản lý xem tổng quan tín hiệu học online trên nhiều lớp/course. UI không kết luận vi phạm, chỉ hiển thị dấu hiệu nghi vấn để giáo viên/quản lý kiểm tra thêm.

## Menu mới
- Nhóm: Vận hành
- Tên: Học online
- Route: `/analytics/learning`
- Permission: `view_dashboard`

## Ngôn ngữ bắt buộc
Các nhãn hiển thị:
- Có dấu hiệu học thật
- Có khả năng treo máy
- Dấu hiệu bất thường cần kiểm tra
- Chưa đủ dữ liệu
- Chưa thấy bất thường rõ

Không hiển thị nội dung kết luận chắc chắn. Mọi dashboard/export phải có disclaimer.

## Dashboard gồm
- Card tổng quan số lượng sinh viên theo nhận định.
- Bảng lớp cần chú ý.
- Bảng sinh viên có dấu hiệu bất thường cần kiểm tra.
- Bảng sinh viên có khả năng treo máy.
- Bảng deadline cần chú ý.
- Bộ lọc: hệ, cơ sở, class_id, course_id, nhận định, từ ngày, đến ngày.
- Nút Xuất CSV.

## Nguyên tắc hiệu năng
- Dashboard đọc snapshot `AnalyticsLearningBehaviorSnapshot`.
- Không query raw tracking log ở dashboard.
- Không recalculate khi mở dashboard.
- Không gọi API nặng nếu người dùng chỉ lọc dashboard.

## Bước tiếp theo đề xuất
v25.9.16.6.7 — Production Analytics Ops: scheduler ingest/recalculate, job queue hóa recalculate lớn, RBAC scope hardening theo campus/teacher, và smoke test thật cho dashboard.
