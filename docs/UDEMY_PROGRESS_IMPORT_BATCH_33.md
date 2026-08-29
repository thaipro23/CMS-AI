# Batch 33 — Import điểm và tiến độ Udemy bằng tác vụ nền

Ngày đóng gói: 2026-08-06  
Baseline: Batch 32 — Import và quản lý kế hoạch Udemy  
Migration head mới: `0056_v25_9_16_7_2_64_33`

## 1. Mục tiêu

Batch 33 hoàn thiện bước thứ ba của lộ trình Udemy:

```text
Upload một hoặc nhiều báo cáo Udemy
→ xác định đúng môn theo Hệ + Học kỳ + Block
→ chống import trùng bằng SHA-256
→ xử lý nền trên Celery queue exports
→ đối chiếu sinh viên với roster AP
→ cập nhật snapshot tiến độ hiện tại
→ đánh giá chậm tiến độ theo kế hoạch active
→ tạo file Excel lỗi để xử lý lại
```

Không gọi Open edX và không chạy Full CMS đối với môn Udemy.

## 2. Giao diện

Trang sử dụng:

```text
/subject-management
```

### Import nhiều môn

Nút **Import điểm Udemy** nhận tối đa 50 file trong một lần. Tên file phải bắt đầu bằng mã môn:

```text
SOF3032_report.xlsx
MOB1014_export_01.xlsx
```

Hệ thống tự xác định `subject_delivery` trong đúng Hệ + Học kỳ + Block đang chọn.

### Import tại một môn

Tại dòng môn Udemy, nút **Import điểm** gắn file trực tiếp với môn đó nên không phụ thuộc tên file. Chế độ này chỉ nhận một file mỗi lần.

### Theo dõi và thử lại

- Tác vụ hiển thị tiến độ trên trang quản lý môn và trong `/jobs`.
- Modal tự cập nhật trạng thái từng file sau khi xếp hàng.
- File thất bại có nút **Thử lại** riêng, không cần chạy lại toàn bộ batch.
- File có dòng lỗi/không khớp AP có nút **Tải lỗi**.
- F5 hoặc chuyển trang không làm mất trạng thái vì parent job và từng file đều được lưu trong PostgreSQL.

## 3. Định dạng Excel được hỗ trợ

### 3.1 File tổng hợp ACMS

Nhận diện theo header, ví dụ:

```text
STT | Email | Name | Tiến độ hiện tại | Chậm tiến độ | Học kỳ | Block
```

Mỗi email được coi là một snapshot tổng. Nếu email lặp trong cùng file, hệ thống giữ giá trị tiến độ lớn nhất và lưu số dòng trùng vào metadata; không cộng dồn phần trăm.

File thực tế `export_udemy_SOF3032_683.xlsx` đã được dùng để kiểm tra parser: 38/38 sinh viên được đọc, không có dòng lỗi.

### 3.2 File export gốc Udemy dạng item

Parser ưu tiên nhận diện cột theo tên:

```text
Email
Name
Progress / Completion / Item progress
Class (nếu có)
```

Mỗi email có thể xuất hiện nhiều dòng item. Tiến độ môn được tính tương thích ACMS cũ:

```text
floor(tổng tiến độ item / item_count trong kế hoạch Udemy active)
```

### 3.3 Fallback ACMS cũ 25 cột

Khi file có đúng 25 cột nhưng header không nhận diện được:

```text
Email: cột 3
Họ tên: cột 2
Tiến độ item: cột 17
Dữ liệu bắt đầu từ dòng 2
```

Logic fallback được xây theo source `ImportUdemy.php` của ACMS cũ và đã kiểm thử bằng workbook tổng hợp mô phỏng 25 cột. Chưa có file export Udemy gốc 25 cột thực tế được cung cấp, vì vậy UAT production bắt buộc thử thêm một file nguyên gốc trước khi triển khai rộng.

## 4. Chuẩn hóa và kiểm tra dữ liệu

### File

- Chỉ nhận `.xlsx`.
- Tối đa 20 MB/file.
- Tối đa 200 MB/lần upload.
- Tối đa 50 file/lần.
- Tối đa 300.000 dòng/file.
- Tối đa 10.000 entry ZIP/XLSX.
- Tổng dữ liệu sau giải nén tối đa 400 MB/file.
- File phải nằm trong `LOCAL_STORAGE_PATH` trước khi worker đọc.
- Retry xác minh lại SHA-256 để phát hiện file đã bị thay đổi.

### Email

- Trim và chuyển lowercase để đối chiếu.
- Dòng thiếu email hoặc sai định dạng được ghi vào file lỗi.
- Không tự tạo sinh viên từ báo cáo Udemy.

### Tiến độ

- Nhận số, số thập phân và chuỗi có `%`.
- Nhận cell Excel định dạng phần trăm.
- Chặn số âm, `#N/A`, `#VALUE!`, `N/A`, `NULL` và giá trị không hữu hạn.
- Giá trị lớn hơn 100 được giới hạn về 100 và đánh dấu trong metadata.

## 5. Đối chiếu sinh viên AP

Thứ tự đối chiếu:

```text
1. Email trong roster AP của đúng Môn + Học kỳ + Block + Hệ
2. Nếu file có cột Lớp, dùng class_code để phân giải nhiều lớp
3. Email duy nhất trong AcademicStudent nhưng chưa thuộc roster hiện tại
4. Ambiguous hoặc unmatched
```

Trạng thái snapshot:

```text
matched_roster
matched_student_outside_roster
ambiguous
unmatched
```

Chỉ `matched_roster` được tính là đối chiếu hoàn chỉnh. Các trạng thái còn lại đều xuất hiện trong file lỗi để người vận hành sửa roster AP hoặc file nguồn.

## 6. Đánh giá chậm tiến độ

Hệ thống lấy phiên bản kế hoạch Udemy active mới nhất và chọn mốc gần nhất có:

```text
deadline_date <= ngày worker xử lý file
```

Sau đó:

```text
is_late = progress_percent < required_progress_percent
```

Nếu môn chưa có kế hoạch:

- Import vẫn hoàn thành.
- `is_late = null`.
- Không kết luận đạt/chậm.
- Với file item-level, mẫu số tạm lấy theo số item quan sát và trả cảnh báo.

## 7. Chống import trùng và retry

Khóa chống trùng mặc định:

```text
subject_delivery_id + SHA-256 file
```

- File đang `queued`, `running` hoặc đã `completed` được coi là đã import.
- Upload lại mặc định tạo batch `skipped`, không ghi đè snapshot và không cộng dữ liệu.
- Tùy chọn **Import lại có chủ đích** tạo một lần xử lý mới có audit rõ ràng.
- Batch `failed` có thể thử lại riêng; hệ thống sao chép file sang parent job mới, giữ liên kết `duplicate_of_batch_id` và không sửa lịch sử batch cũ.
- PostgreSQL advisory transaction lock giảm race condition khi hai người cùng upload một file; unique idempotency key là lớp bảo vệ cuối.

## 8. Mô hình dữ liệu

### `udemy_progress_import_batches`

Lưu một file và vòng đời xử lý:

```text
parent_job_id
subject_delivery_id
duplicate_of_batch_id
idempotency_key
file_name / file_hash / file_size_bytes
file_path / error_report_path
parser_format
status: queued | running | completed | failed | skipped
các bộ đếm matched/outside roster/unmatched/ambiguous/failed
request_json / result_json / error_message
requested_by / started_at / finished_at
```

### `udemy_student_progress`

Snapshot hiện tại theo:

```text
UNIQUE(subject_delivery_id, normalized_email)
```

Các trường chính:

```text
class_id / student_id
email / display_name
progress_percent
is_late
current_plan_week
required_progress_percent
current_deadline_date
match_status
source_format
last_import_batch_id / last_imported_at
metadata_json
```

### `udemy_progress_unmatched_rows`

Giữ chẩn đoán theo dòng:

```text
batch_id
row_number
email / display_name
raw_progress / normalized_progress
reason_code / reason_message
raw_json
```

Bản ghi của bảng này là nguồn tạo file Excel lỗi.

## 9. API mới

```http
POST /api/academic/udemy/progress/import/jobs
POST /api/academic/udemy/progress/import-batches/{batch_id}/retry
GET  /api/academic/udemy/progress/import-batches
GET  /api/academic/udemy/progress/import-batches/{batch_id}/errors.xlsx
GET  /api/academic/subject-deliveries/{delivery_id}/udemy-progress/summary
```

Quyền bắt buộc: `manage_settings` hoặc System Admin theo Business RBAC.

## 10. Celery và lưu trữ

Task:

```text
academic_udemy_progress_import_task
```

Queue:

```text
exports
```

Worker production cần chạy service `worker-heavy`, vì Compose hiện cấu hình:

```text
--queues=generation,exports
```

Backend và worker dùng chung volume:

```text
runtime_data:/app/.runtime
```

Nếu `ai-worker-heavy` đang `unhealthy`, cần kiểm tra healthcheck và xác nhận queue `exports` trước UAT; container Up nhưng không nhận queue sẽ làm job đứng ở `queued`.

## 11. Thành phần phải triển khai

```text
backend
worker-heavy
frontend
migration 0056
```

Không cần build/restart:

```text
worker thường
worker-analytics
beat
openedx-connector-plugin
openedx-unit-reset-plugin
Learning MFE
Tutor/Open edX image
```

## 12. Triển khai bằng tmux

Đặt patch tại:

```text
/tmp/ai-server-batch33-udemy-progress-import-deploy-patch.zip
```

### 12.1 Tạo session

```bash
tmux new -s batch33
```

### 12.2 Chép patch

```bash
cd /opt/ai-server

rm -rf /tmp/batch33-deploy
mkdir -p /tmp/batch33-deploy

unzip -q \
  /tmp/ai-server-batch33-udemy-progress-import-deploy-patch.zip \
  -d /tmp/batch33-deploy

PATCH_ROOT=/tmp/batch33-deploy/batch33_udemy_progress_import_deploy_patch
cp -a "$PATCH_ROOT"/. /opt/ai-server/
```

Kiểm tra marker:

```bash
grep -n "class UdemyProgressImportBatch" backend/app/models/academic.py
grep -n "0056_v25_9_16_7_2_64_33" backend/alembic/versions/0056_v25_9_16_7_2_64_33_udemy_progress.py
grep -n "academic_udemy_progress_import_task" backend/app/worker.py
grep -n "Import điểm Udemy" frontend/app/subject-management/page.tsx
grep -n "retryUdemyProgressImportBatch" frontend/lib/api.ts
```

### 12.3 Kiểm tra Compose

```bash
docker compose \
  --env-file .env.production \
  -f docker-compose.prod.yml \
  config >/tmp/batch33-compose-rendered.yml
```

Xác nhận worker-heavy nhận queue `exports`:

```bash
grep -nA15 '^  worker-heavy:' /tmp/batch33-compose-rendered.yml | grep -- '--queues=generation,exports'
```

### 12.4 Build

Không dùng `--no-cache`.

```bash
docker compose \
  --env-file .env.production \
  -f docker-compose.prod.yml \
  build \
  backend \
  worker-heavy \
  frontend \
  2>&1 | tee /tmp/batch33-build.log
```

Detach tmux: `Ctrl+B`, sau đó `D`. Vào lại:

```bash
tmux attach -t batch33
```

### 12.5 Migration

```bash
docker compose \
  --env-file .env.production \
  -f docker-compose.prod.yml \
  run --rm --no-deps \
  backend \
  alembic -c alembic.ini upgrade head
```

Kiểm tra:

```bash
docker compose \
  --env-file .env.production \
  -f docker-compose.prod.yml \
  run --rm --no-deps \
  backend \
  alembic -c alembic.ini current
```

Phải thấy:

```text
0056_v25_9_16_7_2_64_33 (head)
```

### 12.6 Recreate

```bash
docker compose \
  --env-file .env.production \
  -f docker-compose.prod.yml \
  up -d \
  --no-deps \
  --force-recreate \
  backend \
  worker-heavy \
  frontend
```

Kiểm tra:

```bash
docker compose \
  --env-file .env.production \
  -f docker-compose.prod.yml \
  ps backend worker-heavy frontend
```

Kiểm tra worker nhận queue:

```bash
docker exec ai-worker-heavy sh -lc \
  'celery -A app.worker.celery_app inspect active_queues --timeout=10'
```

Output phải có queue:

```text
exports
```

## 13. UAT bắt buộc

### 13.1 Import file tổng hợp thật

1. Chọn đúng Hệ, Học kỳ và Block.
2. Chọn môn `SOF3032` là Udemy.
3. Bấm **Import điểm** tại dòng môn.
4. Upload `export_udemy_SOF3032_683.xlsx`.
5. Job phải hoàn thành và đọc 38 sinh viên.
6. Cột Tiến độ Udemy phải cập nhật tổng sinh viên, số chậm và số cần đối chiếu.

### 13.2 Import file gốc 25 cột

1. Dùng file vừa export trực tiếp từ Udemy, không sửa thứ tự cột.
2. Kế hoạch active phải có `item_count` đúng.
3. Đối chiếu thủ công ít nhất 3 sinh viên với cách tính ACMS cũ.
4. Xác nhận email, progress, class và trạng thái chậm.

### 13.3 Chống trùng

1. Upload lại cùng file.
2. Kết quả phải là `skipped`.
3. Số snapshot không tăng.
4. Chọn **Import lại có chủ đích** và chạy lại; lịch sử có batch mới nhưng mỗi email vẫn chỉ có một snapshot hiện tại.

### 13.4 Dòng không khớp

1. Dùng file có email sai/không có trong AP.
2. Job vẫn hoàn thành phần hợp lệ.
3. Nút **Tải lỗi** xuất file `.xlsx` có dòng, email, tiến độ, mã lỗi và nội dung.

### 13.5 Retry riêng

1. Tạo một batch thất bại có file gốc còn trong runtime storage.
2. Bấm **Thử lại**.
3. Hệ thống tạo parent job và batch mới, không sửa lịch sử batch cũ.
4. Nếu file đã bị thay đổi checksum hoặc bị dọn, API phải chặn và yêu cầu upload lại.

### 13.6 Không có kế hoạch

1. Import cho môn Udemy chưa có kế hoạch.
2. Job vẫn hoàn thành.
3. `is_late` không được gán True/False.
4. UI không được kết luận sinh viên đạt/chậm cho tới khi Batch 34 hiển thị chi tiết.

## 14. Kết quả kiểm tra trước đóng gói

```text
Python py_compile: PASS
Regression Batch 31–33: 11 passed
TypeScript/TSX syntax transpile: PASS
Alembic head: 0056_v25_9_16_7_2_64_33
Standalone migration upgrade/downgrade smoke: PASS
Parser file tổng hợp thực tế: aggregate · 38 records · 0 issues
ZIP integrity và kiểm tra secret/private key: PASS (sau bước đóng gói)
```

Chưa chạy:

```text
Docker production build
Migration PostgreSQL trên UAT
Celery/Redis runtime thật
Browser E2E
UAT file export Udemy gốc 25 cột thật
```
