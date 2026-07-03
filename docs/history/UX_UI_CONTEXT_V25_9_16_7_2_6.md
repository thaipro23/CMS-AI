# UX/UI Context v25.9.16.7.2.6

## Trọng tâm UX

Bản này xử lý các lỗi gây khó chịu trong vận hành hằng ngày, không thêm màn hình lớn mới.

## Bank wording

Không dùng nữa:

```text
Chưa làm
Chưa làm hết
Đã public thư viện
```

Wording mới:

```text
Chưa có dữ liệu
Cần hoàn thiện
Cần xử lý tiếp
Cần sửa câu hỏi
Sẵn sàng chốt
Đã đưa lên CMS
```

## Bank card colors

Card trạng thái Bank phải có viền trái rõ:

- Xanh lá: đã đưa lên CMS.
- Xanh dương: sẵn sàng chốt.
- Cam: cần hoàn thiện/cần xử lý tiếp.
- Đỏ: cần sửa/lỗi.
- Xám: chưa có dữ liệu.

Nếu thấy tất cả card vẫn xám, kiểm tra cuối `frontend/app/globals.css` có block:

```css
/* v25.9.16.7.2.6 — Bank status wording + visible card borders */
```

## Jobs vs Audit

`/jobs`:

- Là nơi xem tiến trình xử lý chạy nền.
- Mặc định filter `Tất cả` để thấy job đã hoàn tất như AP sync.
- Có nhóm việc AP sync, class sync, teacher report, analytics, bank.

`/audit`:

- Là nơi xem nhật ký thao tác/lỗi.
- Không dùng để xem progress job.

## Semesters

Khi sửa học kỳ:

- Form phải lấy đúng Block 1/Block 2 theo `sort_order` hoặc tên/mã block.
- Không lấy nhầm block cũ khi backend trả danh sách không ổn định.

## Scrollbar

Cuối CSS có guard:

```css
html { overflow-y: scroll; scrollbar-gutter: stable; }
body { min-height: 100dvh; }
```

Mục tiêu: giảm lỗi mất thanh cuộn dọc phải F5.
