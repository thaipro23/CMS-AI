# Bank hierarchy visual alignment — Batch 2

Nguồn: tiếp tục trực tiếp từ `v25.9.16.7.2.64.16.5.7.2.3-bank-redesign-batch1`.

## Route áp dụng

- `/bank/departments`
- `/bank/departments/{departmentId}/subjects`
- `/bank/subjects/{subjectId}/versions`
- `/bank/subject-versions/{versionId}/chapters`

## Thay đổi giao diện

- Đồng bộ AppShell theo HTML demo đã chốt: sidebar 304px, topbar 86px, navigation mật độ và active state theo mẫu.
- Topbar hiển thị breadcrumb ngang `Ngân hàng đề › trang hiện tại`.
- Thêm page intro gồm icon, tiêu đề và mô tả ở đầu workspace.
- Bộ lọc, số kết quả và create action nằm ở hàng đầu của panel.
- Density và column visibility nằm ở hàng thứ hai.
- Chuẩn hóa bảng: header, chiều cao dòng, border, identity text, status badge, action và pagination theo mẫu.
- Nút Sửa/Xóa hiển thị trực tiếp kèm icon.
- Giữ nguyên API, route, RBAC, URL state, pagination, modal và toàn bộ workflow nghiệp vụ.
- Responsive giữ sidebar drawer và table scroll riêng.

## File thay đổi

- `frontend/app/bank/_components/BankHierarchyPageIntro.tsx` — mới
- `frontend/app/bank/_components/pages/DepartmentsPage.tsx`
- `frontend/app/bank/_components/pages/DepartmentSubjectsPage.tsx`
- `frontend/app/bank/_components/pages/SubjectVersionsPage.tsx`
- `frontend/app/bank/_components/pages/SubjectVersionChaptersPage.tsx`
- `frontend/app/bank/_components/shared.tsx`
- `frontend/components/icons/AppIcon.tsx`
- `frontend/components/layout/AppShell.tsx`
- `frontend/styles/bank-redesign-batch-one.css`

## Verification

Không chạy TypeScript check, lint, test, build hoặc browser smoke test theo yêu cầu của người dùng. Batch này chỉ triển khai giao diện/component presentation/CSS.
