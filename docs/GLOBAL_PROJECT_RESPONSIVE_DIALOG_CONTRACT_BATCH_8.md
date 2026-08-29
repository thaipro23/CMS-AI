# Batch 8 — Global Project Responsive & Dialog Contract

## Phạm vi

Áp dụng contract bố cục và responsive dùng chung cho toàn bộ frontend, không chỉ module Bank.

## Vấn đề đã xử lý

1. Topbar có thể bị cuộn mất khi thao tác `Duyệt câu hỏi` vì `scrollIntoView()` tác động sai scroll container.
2. AppShell có nhiều lớp CSS legacy cạnh tranh giữa body scroll và main-content scroll.
3. Popup chỉ khóa `document.body`, trong khi vùng cuộn thật là `.enterprise-content`, khiến nền vẫn di chuyển và popup có cảm giác mất phần nội dung.
4. Popup review có thể thiếu chiều cao body khi header/footer chiếm không gian trên màn hình thấp.
5. Tablet/iPad và điện thoại chưa có một contract thống nhất cho sidebar drawer, topbar, filter, workflow action, table và popup.

## Quyết định giao diện

- Toàn hệ thống dùng một viewport `100dvh`.
- Sidebar và topbar nằm cố định trong AppShell.
- `.enterprise-content` là vùng cuộn dọc duy nhất.
- Table chỉ cuộn ngang trong table wrapper.
- Tablet dưới 1024px dùng sidebar drawer.
- Điện thoại dùng popup toàn màn hình để tránh cắt form và footer.
- Popup dùng 3 hàng: header / body scroll / footer.
- Khi popup mở, vùng cuộn AppShell được khóa cùng body.
- Breadcrumb giữ đầy đủ và cuộn ngang ở màn hình hẹp.

## Sửa riêng trang Bài học

- Nút `Duyệt câu hỏi` cuộn trực tiếp trong `.enterprise-content`, không cuộn body hoặc làm mất topbar.
- Review popup có chiều cao theo viewport và body cuộn độc lập.
- Footer review responsive, nút không tràn hoặc che nội dung.

## File thay đổi

- `frontend/app/layout.tsx`
- `frontend/styles/global-project-responsive-contract.css` — mới
- `frontend/components/ui/AccessibleDialog.tsx`
- `frontend/app/bank/_components/pages/ChapterWorkspacePage.tsx`

## Kiểm thử

Không chạy lint, typecheck, build hoặc browser test theo yêu cầu của người dùng.
