# Batch 12 — Global Scroll, Notice & Icon Structure Hotfix

## Phạm vi

Áp dụng contract cấu trúc đã chốt cho các route đang bị khóa cuộn hoặc chồng icon/thông báo:

- `/bank/history`
- `/student-management`
- `/student-management/subjects/{subjectId}/classes`
- `/student-management/classes/{classId}`
- `/teacher-management`
- `/teacher-management/teachers/{teacherId}/classes`
- `/teacher-management/classes/{classId}`
- `/analytics/learning`
- `/jobs`
- `/audit`
- đồng thời dùng chung cho `/ap-sync`, `/premises`, `/semesters`, `/users` và các route con dùng AppShell.

## Lỗi gốc

1. `html/body` bị khóa cuộn để AppShell dùng `.enterprise-content` làm scroll owner, nhưng một số route có thể kế thừa inline `overflow: hidden` hoặc `data-dialog-open` sau khi popup đóng/chuyển route.
2. Stylesheet responsive đặt `.enterprise-content` về `height: auto`, làm contract scroll phụ thuộc vào các CSS route legacy.
3. Selector legacy `.academic-inline-notice span { min-width: 180px; }` áp dụng cả vào `VisualIcon` vì icon render bằng thẻ `span`, gây icon chiếm vùng nội dung và đè chữ.
4. Một số màn dùng notice tự viết thay vì shared `InlineNotice`, nên cấu trúc icon/copy/action không thống nhất.

## Thay đổi

### AppShell

- Gắn `data-scroll-owner="workspace"` và ref trực tiếp vào `<main>`.
- Khi đổi route, nếu không còn dialog thật đang mount:
  - xóa `data-dialog-open` bị lưu lại;
  - xóa inline overflow/overscroll trên main;
  - xóa body overflow/padding lock bị lưu lại;
  - đưa main workspace về đầu trang.
- Fallback layout của các module ngoài Bank có sẵn `enterprise-standard-page` ngay từ lần render đầu.

### Scroll contract toàn hệ thống

- Sidebar/topbar vẫn cố định.
- `.enterprise-content` có `height: 100%`, `min-height: 0` và là scroll owner dọc duy nhất.
- `page-stack` dùng các hàng theo chiều cao nội dung để toàn bộ chiều dài trang được đưa vào scroll container.
- Chỉ table viewport được cuộn ngang.
- Dialog mở vẫn khóa đúng main workspace.

### Icon contract

- Icon của page identity, section header và visual section luôn `position: static`.
- Icon và copy là hai vùng flex độc lập.
- Xóa ảnh hưởng của inset/transform/z-index từ CSS legacy.

### Notice contract

- `InlineNotice` có class component riêng `enterprise-inline-notice`.
- `ActionMessage` có class component riêng `enterprise-action-message`.
- Layout notice chuẩn: `icon | copy | action`.
- Trên mobile, action chuyển xuống hàng riêng.
- Selector span legacy được thu hẹp chỉ còn nội dung trong `.notice-copy`.
- `/bank/history` và `/analytics/learning` chuyển về shared `InlineNotice`.

## File thay đổi

- `frontend/components/layout/AppShell.tsx`
- `frontend/components/ui/InlineNotice.tsx`
- `frontend/components/ui/ActionMessage.tsx`
- `frontend/app/bank/_components/pages/BankHistoryPage.tsx`
- `frontend/app/analytics/learning/page.tsx`
- `frontend/app/globals.css`
- `frontend/app/layout.tsx`
- `frontend/styles/global-workspace-scroll-notice-hotfix.css` (mới)

## Verification

Theo yêu cầu hiện tại, batch này không chạy lint, TypeScript check, unit test, production build hoặc browser smoke test. Cần xác minh trực tiếp sau khi deploy UAT trên các route và viewport thật.
