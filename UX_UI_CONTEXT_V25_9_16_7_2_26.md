# UX/UI Context v25.9.16.7.2.26 — Production Audit Hardening

## Luồng vận hành chính

- `/student-management`: Môn → Lớp → Chi tiết lớp.
- `/teacher-management`: Giảng viên → Lớp → Hành vi học.
- `/analytics/learning`: Môn → Lớp → Xem kết quả.

## Nguyên tắc phân quyền

Backend là nguồn quyết định quyền cuối cùng. UI chỉ hỗ trợ hiển thị, không được xem là cơ chế bảo mật.

- SYSTEM_ADMIN: toàn hệ thống.
- CAMPUS_MANAGER: chỉ cơ sở được phân.
- Chủ môn/trưởng bộ môn: chỉ môn được phân.
- Giảng viên: chỉ lớp AP phân công.

## Từ ngữ chuẩn

- `Auto map tất cả` → `Tự động ghép Course CMS`.
- `Enrollment` / `Enroll` → `Ghi danh CMS`.
- `Job` → `Tác vụ nền` trên UI người dùng.
- `Học thật` → `Có dấu hiệu học thật`.
- `Treo máy` → `Có khả năng treo máy`.
- Không dùng `gian lận`, `cheating`, `vi phạm chắc chắn` trong UI phân tích hành vi học.

## Hành vi màn `/analytics/learning`

- Không tải toàn bộ môn một lần.
- Danh sách môn phân trang `50 / trang`.
- Tìm kiếm môn debounce 400ms.
- Chỉ tải danh sách lớp sau khi bấm `Xem lớp`.
- Chỉ tải kết quả sinh viên sau khi bấm `Xem kết quả`.
- Bấm pill kết quả mới mở drawer lý do.

## Tác vụ nền

- `Tự động ghép Course CMS` tạo parent job bền vững.
- Worker chỉ enqueue lớp trong `approved_class_ids` đã duyệt lúc bấm nút.
- F5 không mất tiến trình.
- Người dùng khác có quyền xem `/jobs` thấy tác vụ đang chạy.
