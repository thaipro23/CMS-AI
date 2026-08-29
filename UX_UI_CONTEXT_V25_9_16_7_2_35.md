# UX/UI Context v25.9.16.7.2.35

Bản `.35` không đổi layout lớn. UX thay đổi là hành vi hệ thống: người dùng không cần nhớ bấm “Tính lại học online” sau mỗi batch ingest.

## Nguyên tắc vận hành

- Tracking log vào → hệ thống tự đưa các lớp bị ảnh hưởng vào `/jobs`.
- Người dùng theo dõi tiến độ ở `/jobs` với nhãn `Tính lại học online`.
- Không kết luận gian lận/vi phạm. UI vẫn dùng nhãn mềm:
  - Có dấu hiệu học thật
  - Có khả năng treo máy
  - Dấu hiệu bất thường cần kiểm tra
  - Chưa đủ dữ liệu
  - Chưa thấy bất thường rõ

## Kỳ vọng người dùng

- Không cần tự thao tác sau mỗi lần ingest.
- Không thấy `0 sinh viên` sai nếu AP roster đã có sinh viên.
- Nếu thiếu snapshot, bảng vẫn hiển thị sinh viên là `Chưa đủ dữ liệu`.
- Nếu cần ép tính lại ngay, nút thủ công ở chi tiết lớp vẫn còn là đường fallback.
