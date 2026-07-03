# UX/UI Context v25.9.16.7.2.15

## Chủ đích UX

Các màn quản lý đào tạo phải đọc như dashboard enterprise: tiêu đề ngắn, KPI rõ nghĩa, không cần block hướng dẫn dài.

## `/student-management`

KPI dùng nhãn trực tiếp:

- Tổng số môn
- Tổng số lớp
- Tổng số sinh viên theo bộ lọc
- Course CMS đã map
- Cần kiểm tra

Không hiển thị note `Cách đọc số liệu` vì các nhãn đã đủ rõ.

## `/teacher-management`

Tiêu đề chính: `Quản lý giảng viên`.

KPI dùng nhãn trực tiếp:

- Tổng giảng viên
- Tổng số lớp
- Tổng số sinh viên

Không hiển thị:

- Tải lại báo cáo
- Tính lại báo cáo
- Báo cáo: Đang đọc cache...
- Cách đọc số liệu...

Giữ các action xuất Excel vì đây là tác vụ người dùng cần.

## Backend/UI consistency

Frontend đã bỏ thao tác cache báo cáo, nên endpoint list teacher report phải đọc động bằng `use_cache=False` để không còn tình trạng số liệu phụ thuộc cache cũ.
