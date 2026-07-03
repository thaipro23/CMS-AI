# UX/UI Context v25.9.16.7.2.4

## Thay đổi UX/UI

- Danh sách sinh viên giữ STT.
- Bảng Danh sách sinh viên tự cuộn ngang trong vùng bảng, không làm tràn ngang toàn trang.
- Thanh cuộn ngang nằm trong bảng; không cần kéo toàn page.
- Plain vertical wheel dùng để cuộn trang bình thường.
- Horizontal trackpad hoặc Shift+wheel dùng để cuộn ngang bảng.
- Bỏ gạch chân/underline ở link, breadcrumb và các bảng vận hành chính.
- Giảm độ nặng của các cảnh báo Học online, rút gọn text cảnh báo dài.

## Thay đổi logic vận hành

- Backfill học online không bị chặn chỉ vì thiếu session structure.
- Nếu lớp đã có Course CMS và sinh viên, backfill có thể tạo snapshot `Chưa đủ dữ liệu`.
- Dashboard không còn bị cảm giác lỗi trắng/0 toàn bộ khi tracking log đã ingest nhưng chưa rebuild Bài/Session.
- Course CMS resolve fallback sang mapping môn/kỳ/campus/branch nếu lớp không có override riêng.

## Chính sách an toàn

- Học online vẫn chỉ là tín hiệu hỗ trợ xác minh.
- UI không kết luận vi phạm.
- Các nhãn mềm giữ nguyên.
