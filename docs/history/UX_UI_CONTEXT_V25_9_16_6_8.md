# UX/UI Context — v25.9.16.6.8

## Trọng tâm

Bản này không thêm bảng UI phức tạp. Mục tiêu là làm dashboard Học online đủ an toàn để dùng production:

- Người dùng biết dữ liệu đã sẵn sàng hay chưa.
- Biết thiếu tracking log, thiếu session mapping, thiếu snapshot, thiếu duration.
- Có nút backfill học online để đưa lớp vào hàng đợi.
- Không làm dashboard query raw tracking log.

## Thay đổi trong `/analytics/learning`

Thêm strip trạng thái dữ liệu:

```text
Trạng thái dữ liệu: Sẵn sàng dùng / Cần backfill/cập nhật / Cần cấu hình dữ liệu
Tracking log: Đã mount / Chưa thấy
Events đã ingest
Snapshot học online
Lớp có thể backfill
```

Nếu có issue, hiển thị tối đa 3 gợi ý ngắn:

```text
Cần kiểm tra trước khi dùng production
<message> → <action>
```

Thêm nút:

```text
Backfill học online
```

Nút này không chạy request dài. Nó gọi API enqueue job và xem tiến trình ở `/jobs`.

## Nguyên tắc nhãn an toàn

Frontend vẫn chỉ render nhãn mềm:

```text
Có dấu hiệu học thật
Có khả năng treo máy
Dấu hiệu bất thường cần kiểm tra
Chưa đủ dữ liệu
Chưa thấy bất thường rõ
```

Không render từ:

```text
gian lận
cheating
không học thật
treo máy chắc chắn
vi phạm chắc chắn
```

## Khi nào production-ready

`/analytics/learning` nên được coi là dùng được khi:

```text
data_quality.readiness = READY
tracking_log = Đã mount
tracking_events_inserted > 0
session_count > 0
behavior_snapshot_count > 0
```

Nếu `NEEDS_BACKFILL`, vẫn xem được dữ liệu cũ nhưng nên bấm `Backfill học online`.

Nếu `CONFIG_NEEDED`, cần xử lý mount log/course mapping/session structure trước.
