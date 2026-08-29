# Bank Chapter Scroll, Dialog Focus & Shared Structure — Batch 7

## Phạm vi

Tiếp tục từ Batch 6, ưu tiên route:

```text
/bank/chapters/{chapterId}
```

Các sửa đổi shared component được áp dụng toàn hệ thống.

## Lỗi đã xử lý

### 1. Icon `Danh sách câu hỏi` đè lên tiêu đề

Nguyên nhân là marker CSS legacy của `.section-head::before` dùng `position: absolute`, trong khi padding của header mới đã bị ghi đè.

Đã thay bằng icon thật trong layout flex và tắt marker pseudo-element tại khu vực danh sách câu hỏi.

### 2. Trang Bài 1 và nội dung bảng không cuộn dọc

- Ép `enterprise-content` tiếp tục là vùng cuộn dọc duy nhất của AppShell.
- Trang list/detail Bank dùng cùng scroll contract.
- Khu vực danh sách câu hỏi và table shell không còn khóa chiều cao hoặc cắt nội dung dọc.
- Chỉ wrapper bảng được phép cuộn ngang.

### 3. Popup nhập một ký tự bị nhảy con trỏ

Nguyên nhân nằm trong `AccessibleDialog`: effect quản lý focus phụ thuộc trực tiếp vào `onClose`, `busy` và `initialFocusRef`. Nhiều popup truyền callback inline nên mỗi lần input thay đổi, effect bị cleanup và autofocus chạy lại.

Đã sửa shared dialog:

- lưu callback/trạng thái biến động trong ref;
- effect focus + body scroll lock chỉ chạy khi popup thực sự mở/đóng;
- không autofocus lại theo từng lần re-render;
- không churn body scroll lock khi người dùng nhập liệu.

Sửa đổi này áp dụng cho toàn bộ popup dùng `AccessibleDialog` và wrapper `Modal` trong hệ thống.

### 4. Cột `Độ khó` không chứa đủ `Trung bình`

- Tăng cột lên 118px.
- Không cho header/cell xuống dòng.
- Sửa `EnterpriseDataTable` để width khai báo rõ ràng được áp dụng thật cho cả cột status/text, không chỉ index/number/action.

### 5. Đồng bộ cấu trúc trang

Chuẩn hóa shared contract:

- sidebar/topbar cố định;
- `enterprise-content` là vùng cuộn dọc;
- list/detail Bank cùng page structure;
- panel phát triển chiều cao tự nhiên;
- table chỉ cuộn ngang;
- popup body cuộn riêng, footer giữ nguyên vị trí.

## File đã sửa

```text
frontend/app/bank/_components/pages/ChapterWorkspacePage.tsx
frontend/app/bank/_components/BankQuestionEnterpriseTable.tsx
frontend/components/table/EnterpriseDataTable.tsx
frontend/components/ui/AccessibleDialog.tsx
frontend/styles/bank-redesign-batch-one.css
```

## Nghiệp vụ giữ nguyên

- Không đổi route.
- Không đổi API contract.
- Không đổi RBAC.
- Không đổi review/generation/release workflow.
- Không đổi URL state hoặc server-side pagination/filter/sort.

## Verification

Không chạy TypeScript check, lint, test, build hoặc browser smoke test theo yêu cầu của người dùng.
