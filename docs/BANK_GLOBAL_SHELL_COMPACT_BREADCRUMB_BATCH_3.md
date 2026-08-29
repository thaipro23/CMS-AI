# Bank UI Batch 3 — Global compact shell, full breadcrumbs, compact table controls

## Phạm vi

Điều chỉnh trực tiếp từ Batch 2, chỉ tập trung giao diện và CSS:

- Thu gọn tỷ lệ hiển thị desktop về khoảng 75–80% so với bản trước.
- Áp dụng cùng sidebar và topbar cho toàn bộ hệ thống, không chỉ các route Bank hierarchy.
- Hiển thị đầy đủ breadcrumb phân cấp của Ngân hàng đề.
- Loại bỏ khoảng trống thừa giữa toolbar và tiêu đề bảng.
- Giữ nguyên route, API, dữ liệu, RBAC và workflow nghiệp vụ.

## Breadcrumb canonical

- Bộ môn: `Ngân hàng đề > Bộ môn`
- Môn học: `Ngân hàng đề > Bộ môn > Môn học`
- Phiên bản môn: `Ngân hàng đề > Bộ môn > Môn học > Phiên bản môn`
- Bài học: `Ngân hàng đề > Bộ môn > Môn học > Phiên bản môn > Bài học`
- Chi tiết bài: `Ngân hàng đề > Bộ môn > Môn học > Phiên bản môn > Bài học > Bài N`

Các tầng cha có liên kết quay lại route tương ứng. Breadcrumb dài cuộn ngang riêng trong topbar thay vì bị cắt còn hai tầng.

## Global AppShell

- Sidebar desktop: 236px; collapsed: 66px.
- Topbar: 64px.
- Giảm kích thước logo, menu item, icon, user area và CMS status.
- Giữ sidebar/topbar cố định; main content là vùng cuộn.
- Nút thu gọn sidebar xuất hiện thống nhất trên toàn hệ thống.
- Mobile vẫn dùng drawer.

## Bank hierarchy density

- Giảm icon và tiêu đề trang.
- Giảm padding của content, toolbar, table row và pagination.
- Table header 42px; data row khoảng 64px.
- Action button còn 34px chiều cao.
- Density/column toolbar còn khoảng 50px và căn phải.
- Xóa phần tử spacer rỗng trong `controls-only`, khắc phục khoảng trắng trước tiêu đề bảng.

## File thay đổi

- `frontend/components/layout/AppShell.tsx`
- `frontend/styles/bank-redesign-batch-one.css`
- `frontend/app/bank/_components/pages/DepartmentSubjectsPage.tsx`
- `frontend/app/bank/_components/pages/SubjectVersionsPage.tsx`
- `frontend/app/bank/_components/pages/SubjectVersionChaptersPage.tsx`
- `frontend/app/bank/_components/pages/ChapterWorkspacePage.tsx`

## Verification

Không chạy TypeScript check, lint, test, build hoặc browser smoke test theo yêu cầu của người dùng.
