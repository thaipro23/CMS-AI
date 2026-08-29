# AI Server / Open edX CMS Context — v25.9.16.7.2.64.16.5.7.2

Canonical release: `v25.9.16.7.2.64.16.5.7.2 — Full Frontend Design Contract Closure`.

Tiếp tục trực tiếp từ `.64.16.5.7.1.1`.

## Contract frontend đã chốt

- Sidebar/topbar bám viewport; chỉ main content cuộn.
- Topbar sở hữu title/context; không render breadcrumb/title/description lặp trong content.
- Action danh sách nằm trong section header hoặc table toolbar.
- Một/hai row action hiển thị trực tiếp, không dùng menu `...` vô nghĩa.
- Section không lặp title/count với table summary.
- Bảng hiển thị đủ nội dung, wrap; cột phụ chỉ ẩn theo `defaultVisible` và người dùng bật lại được.
- Contextual back action thống nhất cho route lồng nhau.
- Modal giữa màn hình dùng cho create/edit/grant/review; drawer dùng cho read-only detail/log.
- Spacing theo hệ 4px; không chồng nội dung, không body horizontal scroll.

## Thay đổi nghiệp vụ kỹ thuật

- RBAC có batch endpoint cho nhiều scope trong một transaction.
- Không cấp mới `CAMPUS_MANAGER` legacy.
- Không migration mới; Alembic head `0053`.
- Frontend Docker build mặc định không chạy lặp lint/typecheck; Next build luôn chạy.
- Next child webpack build worker bị tắt để tránh treo build UAT.

## Verification

- Release tests 10 pass.
- Inherited selected regression 32 pass.
- Full frontend contract 30/30.
- Runtime 13/13; layout 15/15; security 15/15; performance 17/17.
- Review pack 31/31.
- Lint/typecheck/build PASS; 30/30 static pages; standalone present.

Browser UAT thật vẫn bắt buộc trước production-wide sign-off.
