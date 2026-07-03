# UX/UI Context v25.9.16.6.7

## Bản này làm gì

v25.9.16.6.7 tập trung production ops cho Học online:

- Nút tính lại Học online trong chi tiết lớp chuyển sang job nền.
- Người dùng không phải chờ request dài.
- `/jobs` có nhóm `Học online` để xem ingest/tính lại học online.
- Dashboard `/analytics/learning` tiếp tục đọc snapshot, không đọc raw log.
- Export vẫn có disclaimer và chỉ dùng nhãn mềm.

## Text an toàn bắt buộc

Các nhãn duy nhất được hiển thị:

- Có dấu hiệu học thật
- Có khả năng treo máy
- Dấu hiệu bất thường cần kiểm tra
- Chưa đủ dữ liệu
- Chưa thấy bất thường rõ

Không hiển thị:

- gian lận
- cheating
- không học thật
- treo máy chắc chắn
- vi phạm chắc chắn

## Jobs UI

`/jobs` có thêm nhóm:

```text
Học online
```

Hiển thị:

- Ingest học online
- Tính lại học online
- trạng thái
- tiến độ
- log mount hay chưa
- số event/lỗi parse ở mức ngắn gọn

## Chi tiết lớp

Khi bấm `Tính lại học online`:

- hệ thống đưa vào hàng đợi
- hiện message ngắn `Đã đưa tính lại học online vào hàng đợi`
- không block UI
- xem tiến trình ở `/jobs`

## Phân quyền

Analytics API áp dụng lại scope từ AcademicService/BusinessRBAC:

- SYSTEM_ADMIN xem tất cả
- CAMPUS_MANAGER xem campus được phân quyền
- Teacher xem lớp được AP phân công hoặc môn được phân quyền
- Không truyền `class_id` cho video students sẽ không trả danh sách sinh viên nếu user không có scope toàn hệ thống

## Production note

Bản này chưa thêm UI lớn mới. Đây là bước vận hành production: job nền, scope, health, smoke test.
