# Batch 27 — Quiz duplicate guard & Learning iframe UI contract

## Lỗi được xử lý

1. Người dùng bấm tạo Quiz/Final test nhiều lần cho cùng Course + bài học mà chưa khôi phục bản cũ, dẫn tới nhiều subsection cùng tồn tại và tổng số câu bị cộng dồn.
2. XBlock iframe đôi khi khởi tạo với theme khác Learning MFE; phải bật/tắt dark mode mới đồng bộ.
3. Sau khi Submit, feedback làm chiều cao nội dung thay đổi nhưng iframe không cập nhật kịp, phần cuối bị che cho tới khi F5.

## Thay đổi

### Chống cộng dồn Quiz

- AI Server chỉ cho phép một instance đang hiệu lực cho cùng `openedx_course_id + chapter_id + assessment_type`.
- Các trạng thái `creating`, `created`, `published` và `rollback_manual_required` đều được coi là còn hiệu lực.
- Giao diện Tạo Quiz nhận biết instance đang hiệu lực, hiển thị `Đã có Quiz/Final test` và yêu cầu Khôi phục trước.
- Open edX connector không còn âm thầm dùng lại chapter/sequential/vertical cùng tên khi tạo Quiz; nếu node cũ còn tồn tại thì trả lỗi rõ ràng.

### Đồng bộ theme iframe ngay lần mở đầu

- Learning MFE đọc `data-paragon-theme-variant` trên thẻ `html`, kết hợp các theme attribute/class hiện có và gửi theme sang LMS iframe ngay khi iframe load/mount.
- LMS iframe áp dụng theme nhận được và phản hồi trạng thái ready, không cần người dùng bật/tắt giao diện tối/sáng.

### Cập nhật chiều cao sau Submit

- Runtime trong iframe gửi lại thông điệp `plugin.resize` với kích thước nội dung thực tế.
- Dùng `ResizeObserver`, `MutationObserver`, submit/click/ajax hooks và một resize burst sau Submit để bắt các thay đổi feedback bất đồng bộ.
- Iframe có thể tăng hoặc giảm chiều cao; không khóa theo viewport cũ.

## Phạm vi triển khai

- AI Server backend + worker.
- AI Server frontend.
- `openedx-connector-plugin` trên CMS/Studio, version `0.1.5`.
- `openedx-unit-reset-plugin` trên LMS, version `0.4.14.6`.
- Learning MFE patch `UnitResetButton.jsx` và rebuild MFE.

Không có migration database.

## Xác minh đã chạy

- `py_compile` cho các file Python thay đổi: đạt.
- TypeScript/JSX transpile syntax check cho trang Quiz và `UnitResetButton.jsx`: đạt.
- Regression contract test Batch 27: `3 passed`.

Chưa chạy Docker build, browser E2E hoặc UAT thực tế với Learning MFE/Open edX.
