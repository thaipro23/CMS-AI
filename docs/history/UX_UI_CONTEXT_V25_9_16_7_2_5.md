# UX/UI Context v25.9.16.7.2.5

## Fix vừa làm

- Sidebar desktop phải cố định ở mé trái, không chạy theo nội dung.
- Sidebar có scroll nội bộ để vẫn xem đủ menu khi màn hình thấp.
- Main content nằm ở cột phải, không bị sidebar fixed che.
- Mobile/tablet giữ layout 1 cột, sidebar không fixed.
- Toàn bộ link frontend bỏ underline ở normal/hover/focus/visited.
- Breadcrumb Academic/Workspace/Bank không underline.
- Footer link không underline.
- `/analytics/learning` tải từng khối mềm: dashboard, data quality, backfill plan, production readiness, pilot acceptance, rollout, monitoring. Khối lỗi sẽ báo tên khối, không làm sập toàn trang.

## CSS override chính

```css
@media (min-width: 1201px) {
  .product-sidebar.sidebar {
    position: fixed !important;
    top: 0 !important;
    left: 0 !important;
    height: 100dvh !important;
    overflow-y: auto !important;
  }
  .product-main.main-area { grid-column: 2 !important; }
}

a,
a:visited,
a:hover,
a:focus,
a:active {
  text-decoration: none !important;
}
```

## Điểm cần kiểm tra bằng mắt

1. Cuộn `/analytics/learning`, `/student-management/classes/{classId}`, `/jobs`, `/audit`.
2. Sidebar vẫn đứng yên trên desktop.
3. Không còn gạch dưới link ở breadcrumb/footer/table.
4. Bảng rộng vẫn chỉ cuộn ngang trong table wrapper, không làm ngang cả page.
