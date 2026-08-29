# Batch 32 — Import và quản lý kế hoạch Udemy theo phiên bản

Ngày đóng gói: 2026-08-05  
Baseline: Batch 31 — Quản lý môn học CMS/Udemy  
Migration head mới: `0055_v25_9_16_7_2_64_32`

## 1. Mục tiêu

Batch 32 hoàn thiện bước thứ hai của lộ trình Udemy: quản lý kế hoạch tiến độ cho từng môn đã chọn nền tảng Udemy theo đúng phạm vi:

```text
Hệ + Học kỳ + Block + Môn
```

Mỗi lần lưu hoặc import tạo một phiên bản mới. Phiên bản cũ được giữ nguyên để truy vết; chỉ một phiên bản active được dùng làm nguồn đánh giá tiến độ cho Batch 33–34.

## 2. Chức năng đã hoàn thành

### 2.1 Import kế hoạch từ Excel

Từ trang `/subject-management`, người dùng có quyền `manage_settings` có thể:

1. Bấm **Import kế hoạch Udemy**.
2. Tải file mẫu chuẩn.
3. Chọn file `.xlsx` tối đa 10 MB và 2.000 dòng.
4. Xem trước toàn bộ kết quả kiểm tra.
5. Tải file lỗi nếu dữ liệu chưa hợp lệ.
6. Xác nhận import khi không còn lỗi.

Parser tương thích file ACMS cũ có dòng tiêu đề:

```text
STT | Học kỳ | Block | Mã môn học | Tên môn học | Số lượng Item |
Week 1 | Tiến độ week 1 | ... | Week 10 | Tiến độ week 10
```

Không phụ thuộc cố định vào vị trí cột. Hệ thống nhận diện header theo tên, hỗ trợ đến 52 tuần và bỏ qua cột không liên quan.

### 2.2 Chuẩn hóa và kiểm tra dữ liệu

Các quy tắc bắt buộc:

- Môn phải tồn tại trong danh mục đã lấy từ AP.
- Phải có đúng bản ghi triển khai theo Học kỳ + Block + Hệ.
- Môn phải đang chọn nền tảng `udemy`.
- `Số lượng Item` là số nguyên lớn hơn 0.
- Mỗi mốc phải có đồng thời deadline và tiến độ.
- Deadline chấp nhận:
  - ngày Excel dạng serial;
  - `dd/mm/yyyy`;
  - `dd-mm-yyyy`;
  - `yyyy-mm-dd`.
- Tuần nằm trong khoảng 1–52 và không trùng.
- Deadline tăng dần theo tuần.
- Tiến độ từ 0 đến 100 và không giảm.
- Mốc cuối dưới 100% được cảnh báo nhưng vẫn cho lưu.
- Một môn không được xuất hiện hai lần trong cùng file.

Bộ chuẩn hóa tiếng Việt xử lý riêng ký tự `đ/Đ`, nên các header như `Tiến độ week 1` được nhận diện chính xác.

### 2.3 An toàn file Excel

Trước khi mở workbook, backend kiểm tra:

- đúng định dạng ZIP/XLSX;
- tối đa 5.000 thành phần trong archive;
- tổng dữ liệu sau giải nén không vượt 100 MB;
- file upload không vượt 10 MB;
- tối đa 2.000 dòng dữ liệu.

Workbook được đọc ở chế độ `read_only` để hạn chế bộ nhớ.

### 2.4 Preview bền vững và chống commit lặp

Preview được gắn token ngẫu nhiên 32 ký tự, thuộc đúng người tạo và hết hạn sau 2 giờ. Preview cũ được dọn tự động.

Mỗi commit Excel lưu `preview_token` vào metadata của phiên bản. Nếu client gửi lại cùng một commit do mất response hoặc bấm lặp, backend trả lại phiên bản đã tạo thay vì tạo thêm phiên bản mới. Một file được upload lại thành preview mới vẫn có thể tạo phiên bản mới có chủ đích.

Khi import nhiều môn, các delivery được khóa theo thứ tự ổn định để giảm nguy cơ deadlock. Toàn bộ commit nằm trong một transaction: một môn thất bại thì không môn nào bị lưu dở dang.

### 2.5 Trang chi tiết kế hoạch

Route mới:

```text
/subject-management/{deliveryId}/udemy-plan
```

Trang có:

- KPI phiên bản hiện tại, số item, số mốc, tiến độ mốc cuối.
- Form tạo phiên bản mới thủ công.
- Thêm/xóa mốc tới tối đa 52 tuần.
- Kiểm tra client-side trước khi gửi.
- Lịch sử toàn bộ phiên bản.
- Phân biệt nguồn `Excel` và `Thủ công`.
- Hiển thị người thực hiện, thời gian, file nguồn và ghi chú.

Tại trang `/subject-management`, cột **Kế hoạch Udemy** hiển thị:

```text
Chưa có kế hoạch
hoặc
vN · X item · Y mốc
```

và dẫn thẳng vào trang chi tiết.

## 3. Mô hình dữ liệu

### `udemy_subject_plans`

```text
id
subject_delivery_id
version
item_count
active
source                    manual | excel_import
source_file_name
source_file_hash
imported_by
imported_at
note
metadata_json
created_at
updated_at
```

Ràng buộc quan trọng:

```text
UNIQUE(subject_delivery_id, version)
CHECK(version >= 1)
CHECK(item_count > 0)
```

### `udemy_subject_plan_milestones`

```text
id
plan_id
week_number
deadline_date
required_progress_percent
sort_order
metadata_json
created_at
updated_at
```

Ràng buộc:

```text
UNIQUE(plan_id, week_number)
CHECK(week_number BETWEEN 1 AND 52)
CHECK(required_progress_percent BETWEEN 0 AND 100)
```

## 4. API mới

```http
GET  /api/academic/udemy/plans/import-template.xlsx
POST /api/academic/udemy/plans/import/preview
GET  /api/academic/udemy/plans/import/errors/{preview_token}.xlsx
POST /api/academic/udemy/plans/import/commit

GET  /api/academic/subject-deliveries/{delivery_id}/udemy-plan
GET  /api/academic/subject-deliveries/{delivery_id}/udemy-plan/history
POST /api/academic/subject-deliveries/{delivery_id}/udemy-plan
```

Quyền bắt buộc: `manage_settings` hoặc System Admin theo Business RBAC.

## 5. Thành phần phải triển khai

```text
backend
frontend
migration 0055
```

Không cần build/restart:

```text
worker
worker-heavy
worker-analytics
beat
openedx-connector-plugin
openedx-unit-reset-plugin
Learning MFE
Tutor/Open edX image
```

## 6. Triển khai bằng tmux

Đặt patch tại:

```text
/tmp/ai-server-batch32-udemy-plan-management-deploy-patch.zip
```

### 6.1 Tạo session

```bash
tmux new -s batch32
```

### 6.2 Chép patch

```bash
cd /opt/ai-server

rm -rf /tmp/batch32-deploy
mkdir -p /tmp/batch32-deploy

unzip -q \
  /tmp/ai-server-batch32-udemy-plan-management-deploy-patch.zip \
  -d /tmp/batch32-deploy

PATCH_ROOT=/tmp/batch32-deploy/batch32_udemy_plan_management_deploy_patch
cp -a "$PATCH_ROOT"/. /opt/ai-server/
```

Kiểm tra file:

```bash
grep -n "class UdemySubjectPlan" backend/app/models/academic.py
grep -n "0055_v25_9_16_7_2_64_32" backend/alembic/versions/0055_v25_9_16_7_2_64_32_udemy_plans.py
grep -n "def parse_workbook" backend/app/services/academic/udemy_plan.py
grep -n "Import kế hoạch Udemy" frontend/app/subject-management/page.tsx
```

### 6.3 Kiểm tra Compose

```bash
docker compose \
  --env-file .env.production \
  -f docker-compose.prod.yml \
  config >/tmp/batch32-compose-rendered.yml
```

### 6.4 Build backend và frontend

Không dùng `--no-cache`.

```bash
docker compose \
  --env-file .env.production \
  -f docker-compose.prod.yml \
  build \
  backend \
  frontend \
  2>&1 | tee /tmp/batch32-build.log
```

Detach tmux bằng `Ctrl+B`, sau đó `D`. Vào lại:

```bash
tmux attach -t batch32
```

### 6.5 Chạy migration

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
0055_v25_9_16_7_2_64_32 (head)
```

### 6.6 Recreate backend và frontend

```bash
docker compose \
  --env-file .env.production \
  -f docker-compose.prod.yml \
  up -d \
  --no-deps \
  --force-recreate \
  backend \
  frontend
```

Kiểm tra:

```bash
docker compose \
  --env-file .env.production \
  -f docker-compose.prod.yml \
  ps backend frontend
```

```bash
curl -fsS https://api-ai.cms-test.poly.edu.vn/api/health
```

## 7. UAT bắt buộc

### 7.1 Import file ACMS cũ

1. Mở `/subject-management`.
2. Bảo đảm môn đã chọn `Udemy`.
3. Bấm **Import kế hoạch Udemy**.
4. Upload file `udemy_setup.xlsx`.
5. Kiểm tra preview nhận đúng Học kỳ, Block, mã môn, số item, deadline và tiến độ.
6. Bấm xác nhận.
7. Cột Kế hoạch phải chuyển từ `Chưa có` sang `v1`.
8. Mở chi tiết và kiểm tra các mốc.

### 7.2 Tạo phiên bản mới

1. Sửa một deadline hoặc tiến độ.
2. Bấm **Lưu phiên bản v2**.
3. `v2` phải active.
4. `v1` phải còn trong lịch sử và ở trạng thái lịch sử.

### 7.3 Kiểm tra lỗi

- Import môn đang chọn CMS: phải bị chặn.
- Số item bằng 0 hoặc `#N/A`: phải báo lỗi.
- Chỉ nhập deadline mà thiếu tiến độ: phải báo lỗi.
- Deadline giảm hoặc trùng: phải báo lỗi.
- Tiến độ giảm: phải báo lỗi.
- Một môn lặp hai dòng: phải báo lỗi.
- Người dùng khác không được commit preview của người tạo.
- Commit lại cùng preview không được tạo thêm phiên bản.

## 8. Kết quả kiểm tra trước đóng gói

```text
Parser file udemy_setup.xlsx thực tế: PASS
LOG301: 6 item, 5 mốc, 20% → 100%: PASS
Regression Batch 31–32: 8 passed
Python py_compile: PASS
Alembic single head: 0055
Migration upgrade/downgrade SQLite smoke test: PASS
TS/TSX syntax transpile: PASS
Template XLSX inspect/render bằng artifact_tool: PASS
```

Bộ test lịch sử Academic cũ còn một số assertion hard-code phiên bản/mốc migration của các batch trước; chúng không phản ánh contract Batch 32 và không được sửa trong batch này.

Chưa chạy Docker production build, PostgreSQL UAT migration, browser E2E hoặc kiểm thử AP thật.
