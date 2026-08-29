# v25.9.16.7.2.64.16.5.5 — Performance & Worker Reliability

## Mục tiêu

Giảm các điểm nghẽn được nêu trong review production: export đồng bộ giữ HTTP worker, API frontend thiếu timeout/cancellation, polling dày, tải toàn bộ hierarchy RBAC và một Celery worker xử lý mọi workload. Bản này tiếp tục trực tiếp từ `.64.16.5.4`; các kiểm soát P0/P1 bảo mật vẫn được giữ nguyên. Không có migration mới. fileciteturn4file0

## Thay đổi chính

### Báo cáo giảng viên

- Export lớn chuyển sang `AcademicTeacherReportJob` và queue `exports`.
- Endpoint đồng bộ chỉ giữ compatibility cho dataset nhỏ, với hard cap mặc định 20 giảng viên hoặc 1.000 sinh viên.
- Job trùng filter/người yêu cầu được dedupe bằng request key.
- Worker tái dựng đúng requester context và backend RBAC thay vì dùng admin giả.
- Workbook được ghi trực tiếp vào shared storage, không dựng toàn bộ bytes rồi `write_bytes` thêm lần nữa.
- File cũ được dọn theo retention mặc định 48 giờ.
- Lỗi job trả mã `ACADEMIC_TEACHER_REPORT_FAILED`; exception thật chỉ nằm trong audit/log server.
- Frontend khôi phục job đang chạy sau F5, polling có AbortController và cho tải file sau khi hoàn tất.

### Frontend API runtime

- `apiFetch` có timeout GET/WRITE cấu hình được.
- Caller cancellation và timeout dùng AbortController.
- GET/HEAD retry có giới hạn cho 408/425/429/502/503/504; tôn trọng `Retry-After`.
- Mỗi request có `X-Request-ID`.
- 401 phát sự kiện `ai:auth-expired`; AppContext xóa session client và chuyển về trang logged-out.
- Polling Bank/Academic jobs dùng exponential backoff `1.5s → 3s → 5s → 10s` và dừng khi component rời trang.

### Danh mục RBAC

- Không eager-load toàn bộ Department → Subject → Offering → Chapter.
- Scope dropdown tìm kiếm server-side theo từ khóa và loại scope.
- API danh mục hỗ trợ query `q`, giới hạn 120 ký tự.
- `fetchAllPageItems` được giới hạn số page/item và tải song song theo batch; vượt ngưỡng yêu cầu chuyển sang server search.

### Celery

Các queue:

```text
interactive
sync
generation
exports
analytics
```

Production Compose có ba worker pool:

```text
worker             interactive,sync
worker-heavy       generation,exports
worker-analytics   analytics
```

Reliability:

- late acknowledgement;
- reject/redelivery khi worker lost;
- prefetch mặc định 1;
- visibility timeout lớn hơn hard task timeout;
- soft/hard time limit theo nhóm task;
- process recycling theo số task và memory;
- result expiration;
- broker retry khi startup.

### Analytics class recalculate

Class-level recalculate không còn đọc toàn bộ tracking events của Course khi tính một lớp. Video và Quiz event được lọc theo danh sách username trong roster AP của lớp trước khi materialize.

## Database

Không có migration mới. Alembic head vẫn là:

```text
0053_v25_9_16_7_2_64_16_5_4
```

## Known debt

- Static query-hotspot scan vẫn đánh dấu một số truy vấn `.all()` lịch sử cần EXPLAIN/UAT và refactor theo workload thực; bản này không tuyên bố đã đóng toàn bộ query debt.
- Chưa dùng SSE/WebSocket; exponential polling là bước giảm tải an toàn trước khi đổi transport.
- Chưa tách toàn bộ `frontend/lib/api.ts`, `academic_service.py` và `worker.py`.
- Queue concurrency phải được hiệu chỉnh bằng load test trên server thật, không tăng theo cảm tính.
