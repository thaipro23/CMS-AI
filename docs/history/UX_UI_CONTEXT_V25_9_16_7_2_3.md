# UX/UI Context v25.9.16.7.2.3

## Mục tiêu UX

Production test gọn hơn, dễ nhìn bảng hơn, giảm thao tác mò thanh cuộn.

## Thay đổi chính

- Thêm cột `STT` cho các bảng vận hành chính:
  - Học online dashboard
  - Pilot acceptance
  - Lớp cần chú ý
  - Danh sách sinh viên trong chi tiết lớp
  - Workflow Assignment
  - Quản lý giảng viên
  - Lớp của giảng viên
  - Sinh viên & lớp: môn/lớp
  - Jobs
  - Audit
  - Cơ sở
  - Học kỳ/block
  - AP sync
  - Bank history/search/quiz tables chính
- Bảng sinh viên có STT sticky trước cột Sinh viên.
- Khi trỏ chuột nằm giữa bảng sinh viên, wheel/trackpad sẽ cuộn ngang chính vùng bảng sinh viên, không cần kéo thanh ngang dưới bảng.
- `/analytics/learning` bỏ JSX section thừa, giảm nguy cơ layout lỗi runtime.

## Nguyên tắc giữ nguyên

- Không dùng từ “gian lận/cheating/vi phạm chắc chắn”.
- Nhãn học online vẫn là tín hiệu mềm:
  - Có dấu hiệu học thật
  - Có khả năng treo máy
  - Dấu hiệu bất thường cần kiểm tra
  - Chưa đủ dữ liệu
  - Chưa thấy bất thường rõ
- Không hiển thị raw tracking log trên dashboard.
- Dashboard chỉ đọc snapshot/aggregate.
