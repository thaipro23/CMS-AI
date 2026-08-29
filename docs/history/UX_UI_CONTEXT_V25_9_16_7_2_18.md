# UX/UI Context v25.9.16.7.2.18

## Phân tích hành vi học cho giáo viên

Mục tiêu UX: giáo viên không cần đọc nhiều khối vận hành, không xem log, không xem quá nhiều lý do ngay từ đầu. Luồng chính chỉ trả lời: lớp nào, sinh viên nào, kết quả là gì.

## Luồng màn hình

```text
Hệ → Học kỳ → Cơ sở → Môn → Danh sách lớp cần quản lý → Chi tiết lớp
```

- Danh sách lớp là màn trung gian bắt buộc để giáo viên không phải chọn lớp từ dropdown dài.
- Bảng lớp chỉ hiển thị kết quả tổng quan.
- Chi tiết lớp chỉ hiển thị bảng sinh viên và kết quả.
- Lý do chỉ mở trong drawer khi bấm vào pill kết quả.

## Wording chính

- `Danh sách lớp cần quản lý`
- `Kết quả lớp`
- `Cần xem`
- `Chưa đủ dữ liệu`
- `Xem kết quả`
- `Lý do ra kết quả`

Không dùng các nhãn kết luận cứng như `gian lận`, `cheating`, `không học thật`.

## Fix quan trọng

Không gọi academic API với `page_size=500`; backend học vụ chỉ cho `page_size <= 200`. FE có guard chung `clampAcademicPageSize()` và riêng `/analytics/learning` tải môn nhiều trang bằng `pageSize=200`.

## Data source

- Danh sách lớp dùng endpoint aggregate `/api/analytics/subjects/{subject_id}/classes/learning-behavior/overview`.
- Endpoint này đọc snapshot/aggregate, không đọc raw tracking log.
- Mỗi class overview trả thêm `openedx_course_id` để FE không cần gọi thêm class list page size lớn chỉ để tìm course mapping.
