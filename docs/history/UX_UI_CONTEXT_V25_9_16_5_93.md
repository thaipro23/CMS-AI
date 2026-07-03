# UX/UI Context — v25.9.16.5.93

## Điều đã chốt

- Người dùng không muốn text kỹ thuật dài trong màn chi tiết lớp.
- `Tiến độ học` chỉ cần:
  - `Hoàn thành khóa học:`
  - `Điểm tổng:`
  - trạng thái như `Điểm thấp`
- Mỗi mục 1 dòng, không thêm dấu chấm ở trạng thái.
- Chỉ `Danh sách sinh viên` được cuộn ngang; các thẻ summary/action phía trên giữ nguyên.
- Không hiện hướng dẫn kéo ngang/Shift-wheel.
- Không hiện mặc định các dòng `Nguồn`, `Fallback`, `Chẩn đoán điểm CMS`.

## v93 đã rà và tối ưu

- Tách luồng load dữ liệu:
  - overview lớp chỉ load khi vào lớp hoặc sau sync;
  - danh sách sinh viên load theo search/filter/page.
- Không còn reload mapping/learning summary khi chỉ chuyển trang hoặc tìm kiếm sinh viên.
- Assignment rows chỉ gọi API khi mở modal.
- Quiz source/debug chỉ hiện khi thêm `?debug=1`.
- Bỏ strip `Các đầu điểm CMS` phía trên bảng sinh viên.
- Thông báo hoàn tất đồng bộ rút gọn.

## Rule dữ liệu giữ nguyên

- `Cập nhật điểm` không tạo user, không enroll.
- `Đồng bộ full CMS` vẫn là full flow.
- Completion fallback = số StudentModule `sequential` có `position` / tổng reachable sequential.
- `itembank`, `problem`, `video` không được tự tính là Course completion.
