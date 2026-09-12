# Triển khai phục hồi job học vụ theo lô — 2026-09-12

Phạm vi release này là CMS-AI branch `feat/import-quiz-cms-old-su26`. Release có migration mới `0065_academic_job_batch_recovery` và phải rollout đồng thời `backend`, `frontend`, `worker` và `worker-heavy`.

Không chạy `docker compose down -v`, không xóa volume và không sửa tay bảng `alembic_version`.

## 1. Lấy source và kiểm tra cấu hình

Chạy từ thư mục deploy CMS-AI hiện tại:

```bash
git fetch origin
git switch feat/import-quiz-cms-old-su26
git pull --ff-only origin feat/import-quiz-cms-old-su26

docker compose --env-file .env.production -f docker-compose.prod.yml config >/tmp/cms-ai-academic-job-recovery-compose.yml
```

Các biến mới có giá trị mặc định an toàn; chỉ thêm vào `.env.production` nếu cần điều chỉnh:

```dotenv
ACADEMIC_BULK_SYNC_DISPATCH_WINDOW=4
ACADEMIC_BULK_SYNC_CONTINUE_DELAY_SECONDS=10
ACADEMIC_JOB_QUEUED_STALE_SECONDS=900
ACADEMIC_CLASS_SYNC_STALE_SECONDS=2400
ACADEMIC_BULK_SYNC_STALE_SECONDS=600
ACADEMIC_TEACHER_REPORT_STALE_SECONDS=6300
ACADEMIC_TEACHER_REPORT_EXPORT_SNAPSHOT_MAX_AGE_SECONDS=300
```

`ACADEMIC_BULK_SYNC_DISPATCH_WINDOW` được backend chặn trong khoảng 1–20. Giá trị production khuyến nghị là 4.

## 2. Backup và chạy migration

Backup PostgreSQL theo quy trình hiện hành trước khi chạy migration. Sau đó build image backend chứa migration rồi chạy service migration đúng một lần:

```bash
docker compose --env-file .env.production -f docker-compose.prod.yml build runtime-init migrate backend frontend worker worker-heavy

docker compose --env-file .env.production -f docker-compose.prod.yml run --rm migrate

docker compose --env-file .env.production -f docker-compose.prod.yml run --rm migrate alembic -c alembic.ini current
```

Kết quả cuối phải có:

```text
0065_academic_job_batch_recovery (head)
```

Migration chỉ bổ sung `parent_job_id`, `idempotency_key` và index cho `academic_class_sync_jobs`; không xóa dữ liệu job cũ.

## 3. Rollout đủ API, UI và hai worker

```bash
docker compose --env-file .env.production -f docker-compose.prod.yml up -d --no-deps --force-recreate backend frontend worker worker-heavy

docker compose --env-file .env.production -f docker-compose.prod.yml ps

docker compose --env-file .env.production -f docker-compose.prod.yml logs --tail=300 backend frontend worker worker-heavy
```

Không được bỏ qua `worker-heavy`: xuất Excel chạy ở queue `exports`. Auto-map và đồng bộ lớp chạy ở queue `sync` của worker thường.

## 4. Xác minh worker nhận đúng queue

```bash
docker compose --env-file .env.production -f docker-compose.prod.yml exec worker \
  sh -lc 'celery -A app.worker.celery_app inspect ping -d worker@$(hostname) --timeout=8'

docker compose --env-file .env.production -f docker-compose.prod.yml exec worker \
  sh -lc 'celery -A app.worker.celery_app inspect active_queues -d worker@$(hostname) --timeout=8'

docker compose --env-file .env.production -f docker-compose.prod.yml exec worker-heavy \
  sh -lc 'celery -A app.worker.celery_app inspect ping -d worker-heavy@$(hostname) --timeout=8'

docker compose --env-file .env.production -f docker-compose.prod.yml exec worker-heavy \
  sh -lc 'celery -A app.worker.celery_app inspect active_queues -d worker-heavy@$(hostname) --timeout=8'
```

Kết quả bắt buộc:

- `worker` trả `pong` và có queue `interactive`, `sync`;
- `worker-heavy` trả `pong` và có queue `generation`, `exports`.

## 5. UAT job Excel bị treo 55%

1. Mở `Tác vụ nền`, tải lại danh sách. Lệnh GET sẽ tự đối soát lease.
2. Job Excel cũ không còn heartbeat quá 6.300 giây phải chuyển từ `running` sang `failed`, nội dung báo worker bị gián đoạn và giữ nguyên phần trăm cuối để audit.
3. Bấm `Chạy lại tác vụ` ở drawer hoặc tại cảnh báo trên trang Quản lý giảng viên.
4. Xác nhận job trở về `queued`, sau đó `running`, `completed`; tải được file Excel.
5. Nếu job mới tiếp tục nằm `queued`, dừng UAT và kiểm tra `worker-heavy`/queue `exports`; không bấm tạo thêm nhiều job.

## 6. UAT Auto-map chạy theo lô

1. Chọn một học kỳ/cơ sở có nhiều hơn 4 lớp và bấm `Tự động ghép Course CMS` đúng một lần.
2. Mở `Tác vụ nền`; parent phải ở `running` và hiển thị số lớp hoàn tất, số lớp đang chạy/chờ, giới hạn 4.
3. Trong khi chạy, kiểm tra database:

```bash
docker compose --env-file .env.production -f docker-compose.prod.yml exec postgres \
  sh -lc 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c "SELECT parent_job_id, COUNT(*) AS active_children FROM academic_class_sync_jobs WHERE parent_job_id IS NOT NULL AND status IN ('\''queued'\'', '\''running'\'') GROUP BY parent_job_id ORDER BY active_children DESC;"'
```

Không parent nào được có `active_children > 4` khi dùng cấu hình mặc định.

4. F5 hoặc mở lại màn hình: chỉ có một parent cho cùng bộ lọc và không có child trùng `idempotency_key`.
5. Parent chỉ chuyển `completed` sau khi mọi child là `completed` hoặc `failed`; tiến độ không được kết thúc ngay sau bước xếp hàng.
6. Nếu worker bị ngắt, khởi động lại worker, tải trang Jobs để đối soát lease, rồi bấm `Chạy lại tác vụ`. Child cũ được retry theo từng cửa sổ 4, không fan-out toàn bộ.

Kiểm tra trùng child:

```bash
docker compose --env-file .env.production -f docker-compose.prod.yml exec postgres \
  sh -lc 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c "SELECT idempotency_key, COUNT(*) FROM academic_class_sync_jobs WHERE idempotency_key IS NOT NULL GROUP BY idempotency_key HAVING COUNT(*) > 1;"'
```

Kết quả phải là 0 dòng.

## 7. Kiểm tra nghiệp vụ sau Auto-map

Với ít nhất một lớp hoàn tất, xác nhận lần lượt:

- Course CMS được ghép đúng Org theo branch;
- tài khoản sinh viên/giảng viên được tạo hoặc sửa hồ sơ khi thiếu;
- giảng viên/campus admin có CMS staff theo chính sách hiện hành;
- sinh viên được enrollment vào course;
- lần đọc xác nhận ngay sau enrollment dùng primary, các báo cáo thông thường vẫn đọc replica;
- lượt lấy điểm chạy sau enrollment theo delay/bước đồng bộ hiện hành và không báo sai “không có sinh viên enrolled” do replica lag;
- Excel dashboard tải thành công.

## 8. Tiêu chí dừng/rollback

Dừng rollout và giữ bằng chứng log nếu migration không ở head, một trong hai worker không nhận đúng queue, parent có hơn 4 child active, hoặc retry tạo child trùng. Rollback image theo quy trình release hiện hành nhưng không downgrade migration và không xóa các job rows; hai cột mới tương thích ngược và nullable.
