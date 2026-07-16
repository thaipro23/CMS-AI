# Bank hierarchy table vertical alignment — Batch 5

## Phạm vi

Chỉ sửa CSS trình bày cho các bảng phân cấp Bank:

- `/bank/departments`
- `/bank/departments/{departmentId}/subjects`
- `/bank/subjects/{subjectId}/versions`
- `/bank/subject-versions/{versionId}/chapters`

## Thay đổi

- Căn giữa theo chiều dọc toàn bộ tiêu đề cột trong `thead`.
- Chuẩn hóa chiều cao hàng tiêu đề thành 42px trên desktop và 40px trên mobile.
- Cân bằng `padding-top` và `padding-bottom`, tránh chữ dạt lên mép trên.
- Căn giữa `enterprise-sort-button` cho cả cột có và không có sắp xếp.
- Giữ cell dữ liệu và nhóm nút thao tác nằm giữa theo chiều dọc.
- Không thay đổi component, route, API, RBAC hoặc dữ liệu.

## File sửa

- `frontend/styles/bank-redesign-batch-one.css`

Không chạy test, lint, build hoặc browser smoke test theo yêu cầu.
