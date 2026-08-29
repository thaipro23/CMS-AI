# UX/UI Context — v25.9.16.7.2.19

## Learning behavior production flow

Mục tiêu UX: giáo viên không cần đọc nhiều cảnh báo kỹ thuật. Giáo viên cần đi từ lớp mình phụ trách đến kết quả học online của sinh viên.

## Luồng chính

1. Giáo viên vào `/teacher-management`.
2. Bấm `Xem lớp` ở giảng viên.
3. Ở danh sách lớp, bấm `Hành vi học`.
4. Hệ thống mở `/analytics/learning` với đúng kỳ/cơ sở/môn/lớp.
5. Màn chính chỉ hiện kết quả.
6. Giáo viên bấm pill kết quả của sinh viên để xem lý do.

## Nguyên tắc copywriting

- Dùng `Có dấu hiệu học thật`, `Có khả năng treo máy`, `Dấu hiệu bất thường cần kiểm tra`, `Chưa đủ dữ liệu`, `Chưa thấy bất thường rõ`.
- Không dùng wording khẳng định như `gian lận`, `cheating`, `vi phạm chắc chắn`, `treo máy chắc chắn`.
- Lý do chỉ xuất hiện trong drawer chi tiết để tránh làm rối màn chính.

## Production guardrails

- Academic page size giữ `<= 200`.
- Class overview dùng `limit=200` và phân trang.
- Direct class open dùng `class_id` ở overview endpoint để không phải tải toàn bộ lớp của môn.
