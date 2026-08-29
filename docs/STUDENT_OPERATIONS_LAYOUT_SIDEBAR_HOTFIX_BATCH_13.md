# Batch 13 — Student Operations Layout, Sticky Table Scroll & Global Sidebar Consistency

## Phạm vi

- `/student-management/subjects/{subjectId}/classes`
- `/student-management/classes/{classId}`
- Route chi tiết lớp dùng chung từ Teacher Management
- AppShell/sidebar toàn hệ thống
- `EnterpriseDataTable` dùng chung

## Thay đổi

### Danh sách lớp theo môn

- Bỏ cột `Sinh viên` khỏi bảng.
- Cột `Học tập` trở thành cột hiển thị mặc định, rộng tối thiểu 230px.
- Cột `Học tập` tổng hợp ghi danh, đã học, tiến độ trung bình và CMS match.
- Hai nút `Chi tiết` và `Phân tích` có cùng chiều rộng/chiều cao.
- Tạo khoảng cách 14px giữa KPI strip và bảng.

### Chi tiết lớp

- Ba action `Đồng bộ full CMS`, `Cập nhật điểm`, `Cấu hình tuần học` được chuẩn hóa thành action strip nổi bật, có icon và hierarchy rõ.
- Header `Học online` và `Danh sách sinh viên` dùng grid icon/copy rõ ràng; icon không dùng absolute positioning.
- Bảng sinh viên có thanh cuộn ngang đồng bộ, sticky ở đáy workspace trong thời gian bảng còn nằm trong viewport.
- Thanh cuộn sticky chỉ điều khiển bảng `Danh sách sinh viên`, không làm toàn trang cuộn ngang.
- Tablet/mobile tự chuyển action thành 2 cột hoặc 1 cột.

### Sidebar toàn hệ thống

Nguyên nhân có hai kiểu nút thu gọn sidebar: CSS đầy đủ của `.enterprise-sidebar-collapse-button` trước đây bị scope vào `.bank-hierarchy-shell`; route ngoài Bank chỉ nhận kích thước nhưng không nhận background, border, color và layout. Browser vì vậy hiển thị button mặc định màu trắng/viền đen.

Batch này chuyển toàn bộ visual contract của nút thu gọn sang `.enterprise-app-shell.enterprise-unified-shell`, nên mọi route dùng đúng một kiểu sidebar.

## File thay đổi

- `frontend/app/layout.tsx`
- `frontend/app/student-management/subjects/[subjectId]/classes/page.tsx`
- `frontend/app/student-management/classes/[classId]/page.tsx`
- `frontend/components/table/EnterpriseDataTable.tsx`
- `frontend/styles/student-operations-visual-hotfix.css`

## Verification

Không chạy TypeScript check, lint, build, unit test hoặc browser smoke test theo yêu cầu người dùng.
