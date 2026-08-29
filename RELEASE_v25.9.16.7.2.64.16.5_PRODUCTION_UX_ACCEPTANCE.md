# Release v25.9.16.7.2.64.16.5

## Cross-browser, Responsive, Accessibility & Production UX Acceptance

Bản này tiếp tục trực tiếp từ `.64.16.4`, không viết lại frontend và không thay đổi nghiệp vụ. Mục tiêu là xử lý lớp lỗi cuối thường chỉ xuất hiện khi chạy trên kích thước màn hình, trình duyệt và phương thức tương tác khác nhau.

### EnterpriseDataTable responsive theo container

Trước đây CSS media query ẩn cột nhưng JavaScript vẫn tính width/sticky offset theo toàn bộ cột. Điều này có thể tạo khoảng trống sticky hoặc scroll ngang không cần thiết khi bảng nằm trong workspace hẹp.

`.64.16.5`:

- Dùng `ResizeObserver` để phân loại desktop/tablet/mobile theo chiều rộng thật của table shell.
- Có fallback `window.resize` khi trình duyệt không hỗ trợ `ResizeObserver`.
- Desktop giữ các cột người dùng đã chọn.
- Tablet ẩn cột `optional`.
- Mobile chỉ giữ cột `required`.
- Cột bị ẩn được đưa vào hàng “Chi tiết”, không làm mất thông tin.
- Width và sticky offset được tính lại sau khi quyết định cột thực sự hiển thị.
- Checkbox header thể hiện indeterminate khi mới chọn một phần trang.

### Accessibility

- Vùng cuộn bảng là `role="region"`, focusable và có nhãn.
- Header dùng `scope="col"`.
- Hàng chi tiết có `aria-expanded` và `aria-controls`.
- Phân trang là `nav`, trang hiện tại dùng `aria-current="page"`.
- Select page size có accessible name.
- Drawer khóa body scroll, có `aria-describedby`, Escape và focus return.
- CMS connection dùng live status.
- User menu đóng bằng Escape hoặc click bên ngoài.

### Cross-browser và mobile

- `matchMedia.addListener/removeListener` fallback cho Safari cũ.
- `inert` có fallback bằng `tabIndex=-1` để sidebar off-canvas không lọt focus.
- Hỗ trợ `100vh` + `100dvh`.
- Hỗ trợ iOS safe area.
- Touch target tối thiểu 44px trên coarse pointer.
- Hỗ trợ `forced-colors` và `prefers-reduced-motion`.
- Viewport tối thiểu 320px.

### Production UX evidence

Thêm:

```bash
scripts/production-ux-acceptance-report.sh
```

Script tạo:

- `production-ux-source-contract.json`
- `PRODUCTION_UX_BROWSER_UAT.md`

Static source gate không thay thế nghiệm thu trình duyệt thật.

### Boundary

- Không migration mới.
- Không Bootstrap, React-Bootstrap hoặc jQuery.
- Không đổi API/RBAC/Celery/Bank/Open edX semantics.
- Không khôi phục Assignment score write.
- Diagnostics UI vẫn không xuất hiện trong production.
