# Frontend v27 Local Feedback Audit — v25.9.16.5.38

## Kết luận

Bản này dùng lại frontend nền v25.9.16.5.27, không lấy các bản dark/cockpit v32-v34 và không lấy rollback v29/v30. Các thay đổi UI được giới hạn vào local operation feedback.

## Phạm vi thay đổi frontend

### `ChapterWorkspacePage.tsx`

- Thêm `ChapterActionKey` và `actionBusy` để loading theo từng hành động.
- Thêm `BusyLabel` inline dùng spinner nhỏ.
- Thêm `ChapterOperationStatus` cho tác vụ dài hạn upload/generate.
- Bỏ global `bank-loading-overlay` trong màn chapter.
- Upload tài liệu:
  - summary card `Tài liệu` hiện `Đang up tài liệu`.
  - nút `Tài liệu ({n})` hiện `Đang up tài liệu` khi job upload chạy.
  - nút `+ Gắn tài liệu` hiện `Đang up tài liệu` khi enqueue/upload.
- Tạo câu hỏi:
  - nút `Tạo câu hỏi` hiện `Đang tạo câu hỏi` khi job generate chạy.
  - nút tính chi phí hiện `Đang tính`.
  - nút xác nhận tạo hiện `Đang gửi yêu cầu`.
- Các nút nghiệp vụ:
  - `Kiểm tra thay đổi` → `Đang kiểm tra`.
  - `Chốt bộ đề` → `Đang chốt`.
  - `Public thư viện` → `Đang public`.
  - `Duyệt hết câu chờ` → `Đang duyệt`.
  - `Xóa tài liệu` → `Đang xóa`.

### `DepartmentsPage.tsx`

- Bỏ global loading overlay.
- Thay bằng inline status `role="status"`.
- Nút lưu trong modal hiện `Đang lưu`.

### `globals.css`

- Chỉ thêm CSS nhỏ cho inline busy/status rail.
- Không rewrite theme.
- Không thay token màu/bo góc toàn hệ thống.

## Accessibility

- Tác vụ dài hạn dùng `role="status"`, `aria-live="polite"`, `aria-busy="true"`.
- Progress indeterminate dùng `role="progressbar"` và `aria-label`.
- Không tự đưa focus vào banner trạng thái.
- Không dùng `role="alert"` cho trạng thái đang chạy bình thường.

## Kiểm tra đã chạy

- `npm ci --ignore-scripts --no-audit --no-fund`: OK.
- `npm run --silent typecheck`: OK.
- `python3 -m compileall ...`: OK.

## Giới hạn chưa claim

- Chưa claim `next build` pass trong sandbox.
- Cần xác nhận bằng Docker build frontend trên UAT.
