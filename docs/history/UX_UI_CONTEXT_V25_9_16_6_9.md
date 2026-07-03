# UX/UI Context — v25.9.16.6.9

## Mục tiêu UI

Bản này đưa `/analytics/learning` gần production hơn bằng cách hiển thị trực tiếp trạng thái `Production readiness`.

## Thay đổi chính

- Dashboard Học online gọi thêm:
  - `GET /api/analytics/ops/production-readiness`
- Card đầu tiên hiển thị:
  - `Sẵn sàng production`
  - hoặc `Chưa sẵn sàng production`
- Hiển thị số blocker/cảnh báo.
- Nếu có issue, hiển thị các việc cần xử lý trước production.
- Không thêm từ kết luận vi phạm.
- Không đổi nhãn mềm hiện có.

## Nhãn an toàn giữ nguyên

```text
Có dấu hiệu học thật
Có khả năng treo máy
Dấu hiệu bất thường cần kiểm tra
Chưa đủ dữ liệu
Chưa thấy bất thường rõ
```

## Không hiển thị

```text
gian lận
cheating
không học thật
treo máy chắc chắn
vi phạm chắc chắn
```

## Lưu ý vận hành

Production readiness không thay thế kiểm thử thật, nhưng giúp quản trị thấy ngay:

- Tracking log đã mount chưa.
- Ingest bật chưa.
- Scheduler bật chưa.
- Đã ingest event chưa.
- Đã có snapshot học online chưa.
- Đang có quá nhiều job học online không.
