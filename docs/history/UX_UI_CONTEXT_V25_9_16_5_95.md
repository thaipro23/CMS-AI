# UX/UI + Technical Context — v25.9.16.5.95

## Trọng tâm

Dọn phần vận hành Jobs/Audit để tránh lẫn lộn:

- Jobs = theo dõi tiến trình xử lý.
- Audit = nhật ký thao tác/đối soát.

## Đã làm

### `/jobs`

Hiển thị gom các nhóm việc:

- Đồng bộ lớp/CMS:
  - Kiểm tra CMS
  - Enroll CMS
  - Cập nhật điểm
  - Đồng bộ full CMS
- Đồng bộ AP
- Báo cáo giáo viên:
  - Tính lại báo cáo GV
  - Xuất Excel GV
- Bank / Quiz:
  - Tách tài liệu
  - Tạo câu hỏi
  - Đưa bộ đề lên CMS
  - Tạo Quiz

UI gọn hơn:

- Bỏ mô tả kỹ thuật dài.
- Có filter nhóm việc.
- Mặc định xem `Đang chạy` để giảm dữ liệu tải.
- Có tìm nhanh theo mã việc, loại việc, lớp, người tạo.

### `/audit`

- Rút gọn mô tả hero.
- Không còn hiện raw action code mặc định.
- Không còn hiện target id dài mặc định.
- Muốn debug kỹ thuật dùng `/audit?debug=1`.

### Backend

Thêm API nhẹ:

- `GET /api/academic/sync/class-jobs`
- `GET /api/academic/training/teachers/report-jobs`

Rút gọn label worker:

- `Đang cập nhật điểm`
- `Đang đồng bộ CMS`
- `Hoàn tất cập nhật điểm`
- `Hoàn tất đồng bộ CMS`

## Không đổi

- Course completion vẫn là rule v90/v91:
  - completed = StudentModule `sequential` có `position`
  - total = reachable sequential/subsection
  - không tính `itembank/problem/video`
- Quiz eligibility vẫn là rule v94:
  - quiz phải 100%
  - không sau deadline từ `/semesters`
  - không dùng ngưỡng 50/80

## Version

- Frontend footer/package: `25.9.16.5.95`
- Connector version: `CONNECTOR_VERSION = 25.9.16.5.95`
- Training policy version: `v25.9.16.5.95`
