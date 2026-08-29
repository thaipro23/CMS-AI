# UX/UI context v25.9.16.7.2.31

## Responsive Device-Adaptive UX

Mục tiêu là một giao diện vận hành dùng được trên nhiều thiết bị, không phải chỉ vừa màn desktop lớn.

### Quy tắc mới

1. Không để toàn trang bị scroll ngang.
2. Bảng nhiều cột được phép scroll ngang, nhưng chỉ trong khung bảng.
3. Filter/KPI/card tự co bằng `auto-fit/minmax`.
4. Nút thao tác trên touch device tối thiểu 44px chiều cao.
5. Sidebar desktop là rail trái; tablet/mobile là thanh điều hướng ngang gọn.
6. Modal/drawer dùng `100dvh` và safe-area để không bị cắt trên mobile.
7. Hover transform bị tắt trên touch device.
8. Typography dùng `clamp()` để tránh title quá lớn trên màn nhỏ.

### Breakpoint chính

- `1280px`: giảm sidebar, giảm table min-width.
- `1024px`: chuyển layout sang 1 cột, sidebar thành nav ngang.
- `760px`: mobile/tablet dọc, nút touch 44px, filter/card 1 cột.
- `480px`: mobile nhỏ, pagination/action stack 1 cột.

### Màn cần QA

- `/student-management`
- `/student-management/subjects/{subject_id}/classes`
- `/student-management/classes/{class_id}`
- `/teacher-management`
- `/analytics/learning`
- `/bank/quiz`
- `/jobs`
- `/audit`

### Không thay đổi

- Không đổi API.
- Không đổi dữ liệu.
- Không migration.
- Không fake dữ liệu.
