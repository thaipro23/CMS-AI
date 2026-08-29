# UX/UI Context v25.9.16.7.2.7

## Nguyên tắc

- Enterprise UI gọn, không underline bừa bãi.
- Link vẫn có `focus-visible` để dùng bàn phím/accessibility.
- Sidebar desktop cố định bên trái; main content không bị che.
- Bảng rộng cuộn ngang trong container riêng; STT sticky bên trái.
- Nút nói rõ hành động: không dùng “Làm mới” chung chung ở các điểm đã review.

## Đã sửa

- `/jobs`: nút chính đổi thành `Tải lại danh sách việc`.
- `/audit`: nút đổi thành `Tải lại nhật ký`.
- Header CMS: `Làm mới` đổi thành `Kết nối lại CMS`.
- CSS bỏ `!important` trong `globals.css`, thêm focus state cho link.
- STT sticky áp dụng cho `table-wrap`, `responsive-table-wrap`, `academic-table-wrap`, `training-table-wrap`, `bank-table-wrap`, `class-student-table-scroll`.
