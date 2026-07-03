# UX/UI Context v25.9.16.7.2.22

## Nguyên tắc

Các màn quản lý học vụ phải giữ nguyên phạm vi người dùng đã chọn khi drill-down và quay lại. Không tự suy luận campus từ lớp chi tiết nếu màn danh sách ban đầu đang ở `Tất cả cơ sở`.

## Đã sửa

- `/student-management` đọc query params ban đầu: `term_id`, `branch`, `campus`, `search`.
- `/student-management/subjects/{subject_id}/classes` hiển thị rõ phạm vi: Hệ, Học kỳ, Cơ sở.
- Link từ danh sách lớp sang chi tiết lớp gửi thêm `list_campus=all` khi người dùng đang xem tất cả cơ sở.
- `/student-management/classes/{class_id}` dùng `list_campus` để quay lại danh sách lớp, không tự ép campus của lớp hiện tại.
- Nút `Hành vi học` vẫn dùng campus thật của lớp để mở analytics đúng lớp.
- `/teacher-management` đọc query params ban đầu và không tự chọn campus đầu tiên.
- `/teacher-management` KPI tính theo toàn bộ bộ lọc, không theo trang hiện tại.

## Expected behavior

Nếu vào danh sách lớp COM1071 với tất cả cơ sở và thấy 29 lớp, sau khi vào chi tiết một lớp cơ sở PS rồi quay lại vẫn phải giữ 29 lớp. Chỉ khi người dùng chủ động lọc campus PS mới còn 8 lớp.
