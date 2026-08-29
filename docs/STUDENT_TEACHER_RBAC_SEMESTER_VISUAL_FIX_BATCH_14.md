# Batch 14 — Student/Teacher, RBAC và định dạng ngày học kỳ

## Phạm vi

- `/student-management/classes/{classId}`
- `/teacher-management`
- `/teacher-management/teachers/{teacherId}/classes`
- `/student-management/subjects/{subjectId}/classes`
- `/users` — popup Gán quyền
- `/semesters` — popup Thêm/Sửa học kỳ

## Thay đổi

### Chi tiết lớp

- Tách trạng thái `Chưa đồng bộ CMS` và gợi ý `Cần đồng bộ full CMS` thành hai dòng có khoảng cách rõ ràng.
- Bỏ badge `Assignment: đọc từ hệ thống ngoài` khỏi thanh action.
- Loại bỏ icon giả do `.section-head::before`, giữ đúng một `VisualIcon` cho `Học online` và `Danh sách sinh viên`.
- Tăng chiều rộng cột Tiến độ học lên 240px để nội dung không dính/chồng.

### Quản lý giảng viên và danh sách lớp

- Teacher workspace và teacher classes workspace chuyển sang grid có gap 14px.
- KPI, notice và bảng không còn dính thành một khối.
- Nút `Chi tiết` và `Phân tích` có cùng chiều rộng, chiều cao và khoảng cách.
- Cột thao tác danh sách lớp giảng viên tăng lên 132px.

### Gán quyền

- Không cho gán mới role `TEACHER_ASSIGNED / Giáo viên được phân công AP` trên giao diện.
- `Người duyệt câu hỏi` chỉ còn phạm vi `Môn học` và `Version/kỳ môn`.
- Loại phạm vi `Bài / chapter` được bỏ khỏi popup Gán quyền.
- Quyền cũ trong dữ liệu vẫn được hiển thị để không mất khả năng audit/thu hồi.

### Học kỳ

- Toàn bộ ô ngày trong popup học kỳ dùng đúng chuỗi `dd/mm/yyyy` thay vì phụ thuộc locale của native `input[type=date]`.
- Giá trị form được chuẩn hóa theo định dạng Việt Nam và vẫn chuyển về ISO khi gửi backend.
- Thông báo validation đổi thành yêu cầu nhập đúng `dd/mm/yyyy`.

## File sửa

- `frontend/app/student-management/classes/[classId]/page.tsx`
- `frontend/app/teacher-management/teachers/[teacherId]/classes/page.tsx`
- `frontend/app/users/page.tsx`
- `frontend/app/semesters/page.tsx`
- `frontend/styles/student-operations-visual-hotfix.css`

Không chạy TypeScript check, lint, build hoặc browser smoke test theo yêu cầu.
