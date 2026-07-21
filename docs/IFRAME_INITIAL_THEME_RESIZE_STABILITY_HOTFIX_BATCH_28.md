# Batch 28 — Initial iframe theme & resize stability hotfix

## Hiện tượng

1. Iframe XBlock ở lần mở đầu lấy dark/light theo hệ điều hành, không theo theme hiện tại của Learning MFE. Sau khi người dùng bật/tắt theme, iframe mới đồng bộ đúng.
2. Chiều cao iframe tăng liên tục sau khi runtime gửi `plugin.resize`.

## Nguyên nhân

### Theme lần đầu

Batch 27 gọi `detectHostThemeVariant()` ngay khi component/iframe mount. Khi Paragon chưa kịp đặt `data-paragon-theme-variant` trên thẻ `html`, code fallback ngay sang `prefers-color-scheme`. Vì vậy theme hệ điều hành bị gửi sang iframe trước theme đã lưu của CMS/MFE.

### Chiều cao tăng vô hạn

Runtime Batch 27 dùng `html/body.scrollHeight`, `offsetHeight` và đồng thời `ResizeObserver` trực tiếp trên `html/body`. Các kích thước này bao gồm chiều cao viewport hiện tại của iframe. Khi parent nhận `plugin.resize` và tăng height, viewport trong iframe cũng tăng; observer chạy lại, đo height mới lớn hơn và gửi tiếp. Đây là vòng phản hồi dương.

## Thay đổi

### Theme

- Không fallback sang `prefers-color-scheme` trong contract MFE → iframe.
- Ưu tiên theo thứ tự:
  1. `data-paragon-theme-variant` / theme attribute thực tế;
  2. preference theme lưu trong localStorage;
  3. class hiện tại;
  4. stylesheet theme đang active;
  5. màu nền thực tế của MFE.
- Nếu theme chưa sẵn sàng thì chỉ yêu cầu resize, chưa gửi theme đoán.
- Poll trong 6 giây đầu và bắt sự kiện stylesheet load để đợi Paragon khôi phục preference.

### Resize

- Bỏ hoàn toàn `html/body.scrollHeight` và `offsetHeight` khỏi phép đo.
- Đo đáy nội dung thực tế từ problem, feedback, form, bảng, media và các phần tử có nội dung.
- Không `ResizeObserver` trên `html` hoặc `body`.
- Observer chỉ theo dõi problem/content nodes; node feedback mới được tự động đăng ký.
- Gom các event bằng `requestAnimationFrame`, thêm tolerance 4 px và giới hạn hợp lý 50.000 px.
- Vẫn hỗ trợ tăng/giảm chiều cao sau Submit, AJAX và feedback động nhưng không tự kích hoạt vòng lặp viewport.

## Phiên bản

- `openedx-unit-reset`: `0.4.14.7`

## Phạm vi triển khai

- Learning MFE patch: `UnitResetButton.jsx` và rebuild MFE.
- LMS unit-reset plugin: `views.py`, `setup.py`, sau đó restart LMS/LMS worker.
- Không cần build lại AI Server frontend/backend/worker.
- Không có migration database.

## Kiểm tra đã chạy

- Python `py_compile`: đạt.
- JavaScript runtime `node --check`: đạt.
- Targeted regression tests Batch 27 + Batch 28: `6 passed`.

Chưa chạy browser E2E hoặc UAT thật.
