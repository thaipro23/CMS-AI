# Batch 4 — Table control spacing and inline notice visual hotfix

Phạm vi chỉ gồm giao diện và CSS.

## Đã sửa

- Xóa khoảng trắng giữa hàng `Mật độ / Cột hiển thị` và tiêu đề bảng bằng cách đặt `gap: 0` cho `EnterpriseDataTable` trong các trang hierarchy Bank.
- Tăng chiều cao an toàn của select mật độ và nút cột hiển thị lên 40px.
- Thu icon trong nút `Cột hiển thị` xuống 28px để không lớn hơn khung nút.
- Đặt chiều rộng tối thiểu ổn định cho hai control, tránh chữ/icon chồng lên border.
- Sửa layout `InlineNotice` theo grid 3 cột: icon, nội dung, action.
- Reset `min-width: 180px` legacy đang áp nhầm lên icon vì `VisualIcon` render bằng thẻ `span`.
- Thêm khoảng cách 14px giữa thông báo lỗi/trạng thái và panel bảng.
- Áp dụng sửa notice trong toàn bộ unified AppShell; sửa khoảng trắng table được giới hạn cho hierarchy Bank.

## File thay đổi

- `frontend/styles/bank-redesign-batch-one.css`
- `docs/BANK_TABLE_NOTICE_VISUAL_HOTFIX_BATCH_4.md`

Không chạy test, lint, build hoặc browser smoke test theo yêu cầu.
