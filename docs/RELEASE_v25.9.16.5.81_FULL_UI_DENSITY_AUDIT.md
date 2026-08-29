# v25.9.16.5.81 — Full UI Density Audit Pass

## Mục tiêu
- Rà lại toàn bộ shell và các màn vận hành, không chỉ `/teacher-management`.
- Chặn header/topbar che nội dung trên mọi route.
- Nén các hero/card giới thiệu quá lớn, giữ action cần thiết nhưng bỏ phần mô tả trang trí chiếm chiều cao.

## Thay đổi chính
- Ép `.topbar`, `.workspace-topbar`, `.product-command-topbar`, `.workspace-student-management-topbar` về `position: static`.
- Compact toàn bộ hero/intro thường gặp: `.hero-card`, `.compact-hero`, `.ops-hero`, `.dashboard-command-hero`, `.dashboard-search-hero`, `.dashboard-hero`, `.access-hero`, `.quiz-hero`, `.page-intro.card`.
- Ẩn paragraph/hero glow/helper/hero steps không cần thiết trong khu vận hành.
- Nén KPI/card/table/filter/action button trên toàn hệ bằng CSS override cuối file.
- Giữ sticky trong bảng/scroll container nhưng reset `top: 0` để không chồng dưới header global.

## Kiểm tra
- Backend compile: `python3 -m compileall -q backend/app`.
- Frontend typecheck: `npm --prefix frontend run typecheck`.
- Frontend production build: `npm --prefix frontend run build`.
