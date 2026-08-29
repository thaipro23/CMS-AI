# AI Server / Open edX — Handoff Batch 35.1

## Canonical

- Version: `v25.9.16.7.2.64.16.5.7.2.5`.
- Scope: Udemy UI/UX contract closure và browser acceptance suite.
- Previous baseline: Batch 35 `v25.9.16.7.2.64.16.5.7.2.4`.
- Alembic head giữ nguyên: `0057_v25_9_16_7_2_64_35`.

## Quyết định thiết kế

- Không tạo visual language riêng cho Udemy.
- Button/notice/table/tab/progress/modal phải dùng design system enterprise hiện có.
- Import và export được xem là persistent operation, không phải request ngắn phụ thuộc tab trình duyệt.
- Tab Cảnh báo là semantic scope riêng, không chỉ là nhãn hiển thị.
- Wording không mô tả import file là chuyển dữ liệu ACMS cũ.

## Thành phần chính

- `PersistentJobNotice` dùng chung.
- Dashboard Udemy mới với overview riêng, filter semantics, ARIA và job recovery.
- Import/plan dialog và các bảng phụ dùng `EnterpriseDataTable`/`InlineNotice`.
- CSS Udemy scoped và bỏ override màu button.
- Playwright Udemy desktop/mobile và static regression contract.

## UAT còn bắt buộc

Build frontend production và chạy browser UAT bằng tài khoản system admin, teacher, campus owner; xác nhận import/export thật với worker-heavy trước khi đánh dấu production accepted.
