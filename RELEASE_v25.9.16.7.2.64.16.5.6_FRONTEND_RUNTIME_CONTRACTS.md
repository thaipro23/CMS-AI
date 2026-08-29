# v25.9.16.7.2.64.16.5.6 — Frontend Runtime Contracts + Modal/Error Boundary

## Mục tiêu

Bản này tiếp tục trực tiếp từ `.64.16.5.5`, tập trung đóng các khoảng trống runtime frontend được phát hiện trong review production:

- modal/drawer chưa có cùng accessibility contract;
- còn `window.alert()` và `window.confirm()` native;
- App Router chưa có loading/error/not-found boundary;
- `EnterpriseDataTable` khai báo nhưng chưa thực thi đầy đủ `defaultVisible`, `truncateLines` và sorting;
- hành vi focus, body scroll và nested dialog không đồng nhất giữa các domain.

Bản này không thay đổi API nghiệp vụ, backend RBAC, Celery routing, Bank workflow, Open edX semantics hoặc database schema.

## AccessibleDialog dùng chung

Thêm `frontend/components/ui/AccessibleDialog.tsx` làm primitive duy nhất cho modal và drawer đang hoạt động.

Contract gồm:

- render qua portal;
- `role="dialog"`, `aria-modal`, `aria-labelledby` và `aria-describedby`;
- initial focus qua `data-dialog-autofocus`;
- focus trap bằng Tab/Shift+Tab;
- Escape chỉ đóng dialog trên cùng;
- stack hỗ trợ nested dialog;
- body scroll lock có reference count;
- trả focus về control đã mở dialog;
- backdrop close có thể cấu hình;
- trạng thái busy ngăn đóng nhầm khi request đang chạy;
- placement giữa màn hình hoặc drawer bên phải;
- kích thước small/medium/large/xlarge/viewport.

Các modal/drawer ở Bank, Question Review, Quiz, Student detail, Analytics, AP Sync, Premises, Semesters và Question Edit đã chuyển sang primitive này.

## Feedback runtime thống nhất

Thêm `frontend/components/ui/FeedbackProvider.tsx`:

- toast region có semantic status;
- Promise-based confirmation dialog;
- không còn native `alert()` hoặc `confirm()`;
- AppShell và Student auto-map dùng chung feedback contract.

## App Router boundaries

Thêm:

- `frontend/app/loading.tsx`;
- `frontend/app/error.tsx`;
- `frontend/app/global-error.tsx`;
- `frontend/app/not-found.tsx`.

Các boundary cung cấp loading skeleton, thông báo lỗi dễ hiểu, mã lỗi/request context khi phù hợp và nút thử lại hoặc quay về khu vực an toàn.

## EnterpriseDataTable runtime contract

`EnterpriseDataTable` hiện thực thi thật:

- `defaultVisible` khi khởi tạo và khi khôi phục mặc định;
- `truncateLines` với 1/2/3 dòng;
- server-side sortable header;
- `aria-sort`;
- `sortKey`, `sortDirection` và `onSortChange`;
- page size `10/20/50/100` nhất quán với URL state.

Không chuyển filter/sort/pagination lớn sang client-side.

## Gate mới

Thêm `scripts/frontend-runtime-contracts-report.sh`, được tích hợp vào:

- `scripts/claude-code-review-pack.sh`;
- `scripts/uat-build-gate.sh`.

Gate kiểm tra 13 contract về dialog, feedback, route boundary và EnterpriseDataTable.

## Database

Không có migration mới. Alembic head giữ nguyên:

```text
0053_v25_9_16_7_2_64_16_5_4_diff_idempotency.py
```

## Boundary được bảo toàn

- Không reset database hoặc xóa volume.
- Không sửa tay `alembic_version`.
- Không khôi phục Assignment score write.
- Không thay Bank hierarchy hoặc Release/Quiz semantics.
- Không thay security closure của `.64.16.5.4`.
- Không thay worker/performance contract của `.64.16.5.5`.
