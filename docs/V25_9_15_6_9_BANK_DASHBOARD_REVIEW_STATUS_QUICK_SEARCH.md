# v25.9.15.6.9 - Bank Dashboard + Review Status + Quick Search

## Mục tiêu

Bản này biến UI ngân hàng đề thành giao diện dẫn đường cho giáo viên. Người dùng vào `/bank` phải biết ngay chỗ nào còn việc, chỗ nào đã duyệt xong, bài nào sẵn sàng chốt bộ đề và có thể tìm nhanh đến đúng bộ môn/môn/version/bài.

## Backend API mới

```http
GET /api/question-bank-v2/dashboard/overview
GET /api/question-bank-v2/dashboard/search?q=...
GET /api/question-bank-v2/departments/summary
GET /api/question-bank-v2/departments/{department_id}/subjects/summary
GET /api/question-bank-v2/subjects/{subject_id}/versions/summary
GET /api/question-bank-v2/subject-versions/{subject_offering_id}/chapters/summary
```

Các API này gom số liệu ở backend, frontend không tự join quá nhiều.

## UI mới

- `/bank` là Dashboard tổng quan, không còn redirect thẳng sang `/bank/departments`.
- Card Bộ môn hiển thị số môn đã duyệt xong/chưa duyệt xong, câu chờ xử lý, bài sẵn sàng chốt.
- Card Môn hiển thị số version đã duyệt/chưa duyệt, tổng câu, câu chờ xử lý.
- Card Version hiển thị tổng bài, tổng câu, đã duyệt, chưa duyệt/lỗi, release đã publish.
- Card Chapter hiển thị tài liệu, tổng câu, đã duyệt, chưa duyệt/lỗi, trạng thái release.
- Workspace Chapter có khối “Bạn cần làm gì tiếp?”.
- Tất cả trang Bank có tìm nhanh toàn hệ thống.

## Quy tắc duyệt xong

Một bài được coi là duyệt xong khi:

```text
Không còn pending_review
Không còn needs_review
Không còn draft_error
Có ít nhất 1 câu approved hoặc published
```

Version/môn/bộ môn được coi là duyệt xong khi các cấp con tương ứng đều duyệt xong.

## Lý do hủy câu

Nút Bỏ/Bỏ câu lỗi mở popup bắt nhập lý do. Lý do được lưu trong review log/audit để truy vết trách nhiệm và dùng cho fine-tune AI sau này.

## Không thêm migration

Bản này không thêm migration mới.
