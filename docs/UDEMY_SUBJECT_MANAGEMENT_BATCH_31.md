# Batch 31 — Quản lý môn học CMS/Udemy theo Học kỳ và Block

Ngày đóng gói: 2026-08-05  
Baseline: `v25.9.16.7.2.64.16.5.7.2.3` + Batch 30  
Migration head mới: `0054_v25_9_16_7_2_64_31`

## 1. Mục tiêu

Batch 31 là nền tảng đầu tiên của lộ trình quản lý môn Udemy trên AI Server. Hệ thống có trang quản lý danh mục môn theo đúng phạm vi:

```text
Hệ + Học kỳ + Block + Môn
```

Mỗi môn trong một phạm vi chỉ có một trạng thái nền tảng:

```text
Chưa chọn | CMS | Udemy
```

Không lưu CMS/Udemy trực tiếp vào bảng môn dùng chung, vì cùng một mã môn có thể chạy CMS ở kỳ này nhưng chạy Udemy ở kỳ khác.

## 2. Chức năng đã hoàn thành

### 2.1 Trang `/subject-management`

- Chọn hệ Poly hoặc PTCĐ.
- Chọn Học kỳ và Block.
- Lọc theo nền tảng: Tất cả, Chưa chọn, CMS, Udemy.
- Tìm theo mã môn hoặc tên môn.
- KPI tổng môn, CMS, Udemy, chưa chọn và số lớp AP.
- Chọn nền tảng từng môn bằng segmented control.
- Chọn nhiều môn và cập nhật hàng loạt CMS/Udemy/Chưa chọn.
- Hiển thị số lớp, thời điểm lấy catalog AP và thời điểm cấu hình nền tảng.
- Cột “Kế hoạch Udemy” đã được dành sẵn cho Batch 32.

### 2.2 Lấy danh sách môn từ AP

Nút **Lấy danh sách tất cả môn** tạo tác vụ nền bền vững:

```text
POST /api/academic/subject-deliveries/catalog-refresh/jobs
```

Worker gọi nguồn AP `get-subject-cms`, upsert danh mục môn và tạo các bản ghi triển khai theo Học kỳ/Block. F5 hoặc rời trang không làm mất tác vụ; trạng thái được lưu trong `academic_bulk_operation_jobs` và hiển thị ở `/jobs`.

Các tác vụ cùng phạm vi đang chạy được tái sử dụng thay vì tạo trùng. PostgreSQL advisory lock và unique constraint bảo vệ trường hợp hai worker chạy đồng thời.

### 2.3 Mô hình dữ liệu mới

Bảng:

```text
academic_subject_deliveries
```

Các trường quan trọng:

```text
subject_id
term_id
block_id
branch
learning_platform       NULL | cms | udemy
active
configuration_source
configured_by
configured_at
catalog_refreshed_at
metadata_json
```

Ràng buộc:

```text
UNIQUE(subject_id, term_id, block_id, branch)
CHECK(learning_platform IS NULL OR learning_platform IN ('cms', 'udemy'))
```

Mỗi lần đổi nền tảng được lưu vào `metadata_json.platform_history`. Đổi CMS sang Udemy hoặc ngược lại không xóa Course mapping, enrollment, điểm hay dữ liệu lịch sử đã có.

### 2.4 Policy vận hành CMS/Udemy

Môn **CMS** hoặc **Chưa chọn** vẫn dùng luồng hiện tại.

Môn **Udemy**:

- Vẫn cho phép AP đồng bộ lớp, giảng viên, sinh viên và phân công.
- Không cho tạo/auto-map Course CMS khi toàn bộ các Block của môn trong kỳ đều là Udemy.
- Không cho chạy `cms_sync_check`, `cms_enrollment_sync`, `learning_sync`, `full_cms_sync` cho lớp thuộc delivery Udemy.
- Không cho enqueue tính lại Learning Analytics Open edX cho lớp Udemy.
- Worker kiểm tra lại nền tảng ngay trước khi chạy. Job CMS/Analytics đã xếp hàng trước lúc người dùng chuyển môn sang Udemy sẽ được hoàn tất ở trạng thái **bỏ qua**, không gọi Open edX.
- Auto-map hàng loạt loại các lớp Udemy khỏi phạm vi xử lý.

## 3. API mới

```http
GET   /api/academic/subject-deliveries
POST  /api/academic/subject-deliveries/catalog-refresh/jobs
PATCH /api/academic/subject-deliveries/{delivery_id}/platform
POST  /api/academic/subject-deliveries/platform/bulk
```

Quyền bắt buộc: `manage_settings` hoặc System Admin theo Business RBAC.

## 4. Thành phần phải triển khai

```text
backend
worker
worker-analytics
frontend
migration 0054
```

Không thay đổi:

```text
openedx-connector-plugin
openedx-unit-reset-plugin
frontend-app-learning MFE
Tutor/Open edX image
```

## 5. Triển khai bằng tmux

Đặt patch tại:

```text
/tmp/ai-server-batch31-udemy-subject-management-deploy-patch.zip
```

### 5.1 Tạo tmux

```bash
tmux new -s batch31
```

### 5.2 Chép patch

```bash
cd /opt/ai-server

rm -rf /tmp/batch31-deploy
mkdir -p /tmp/batch31-deploy

unzip -q \
  /tmp/ai-server-batch31-udemy-subject-management-deploy-patch.zip \
  -d /tmp/batch31-deploy

PATCH_ROOT=/tmp/batch31-deploy/batch31_udemy_subject_management_deploy_patch
cp -a "$PATCH_ROOT"/. /opt/ai-server/
```

Kiểm tra file:

```bash
grep -n "class AcademicSubjectDelivery" backend/app/models/academic.py
grep -n "subject-deliveries/catalog-refresh/jobs" backend/app/api/routes/academic.py
grep -n "academic_subject_catalog_refresh_task" backend/app/worker.py
grep -n "Lấy danh sách tất cả môn" frontend/app/subject-management/page.tsx
```

### 5.3 Kiểm tra Compose

```bash
docker compose \
  --env-file .env.production \
  -f docker-compose.prod.yml \
  config >/tmp/batch31-compose-rendered.yml
```

### 5.4 Build

Không dùng `--no-cache`.

```bash
docker compose \
  --env-file .env.production \
  -f docker-compose.prod.yml \
  build \
  backend \
  worker \
  worker-analytics \
  frontend \
  2>&1 | tee /tmp/batch31-build.log
```

Có thể detach tmux bằng `Ctrl+B`, sau đó `D`. Vào lại:

```bash
tmux attach -t batch31
```

### 5.5 Chạy migration

Dùng image backend vừa build, không khởi tạo lại dependency:

```bash
docker compose \
  --env-file .env.production \
  -f docker-compose.prod.yml \
  run --rm --no-deps \
  backend \
  alembic -c alembic.ini upgrade head
```

Kiểm tra migration:

```bash
docker compose \
  --env-file .env.production \
  -f docker-compose.prod.yml \
  run --rm --no-deps \
  backend \
  alembic -c alembic.ini current
```

Kết quả phải có:

```text
0054_v25_9_16_7_2_64_31 (head)
```

### 5.6 Recreate dịch vụ

```bash
docker compose \
  --env-file .env.production \
  -f docker-compose.prod.yml \
  up -d \
  --no-deps \
  --force-recreate \
  backend \
  worker \
  worker-analytics \
  frontend
```

Kiểm tra:

```bash
docker compose \
  --env-file .env.production \
  -f docker-compose.prod.yml \
  ps backend worker worker-analytics frontend
```

```bash
curl -fsS https://api-ai.cms-test.poly.edu.vn/api/health
```

Lưu ý: trạng thái healthcheck cũ của `worker-analytics` là một vấn đề Compose riêng. Batch 31 không thay đổi healthcheck đó; hãy kiểm tra log/health output nếu container vẫn hiện `unhealthy` nhưng tiến trình Celery đang chạy.

## 6. Kiểm thử UAT sau triển khai

1. Mở `/subject-management`.
2. Chọn Poly hoặc PTCĐ, Học kỳ và Block.
3. Bấm **Lấy danh sách tất cả môn**.
4. Chuyển trang hoặc F5; job vẫn phải xuất hiện và tiếp tục chạy.
5. Kiểm tra danh sách môn, số lớp và KPI.
6. Đặt một môn là CMS, một môn là Udemy, một môn để Chưa chọn.
7. F5 và xác nhận lựa chọn vẫn giữ nguyên.
8. Dùng chọn nhiều và cập nhật hàng loạt.
9. Với lớp của môn Udemy, thử Full CMS Sync; API phải trả 409 và thông báo môn đang là Udemy.
10. Chuyển một môn đang có job CMS chờ xử lý sang Udemy; worker phải ghi kết quả `skipped=true`, `skip_reason=udemy_platform`, không gọi Open edX.
11. Với môn CMS, các chức năng map Course và Full CMS phải hoạt động như trước.
12. Kiểm tra `/jobs` có nhãn **Lấy danh sách môn từ AP** và `/audit` có lịch sử cấu hình nền tảng.

## 7. Rollback

Migration 0054 chỉ tạo bảng mới, không sửa bảng dữ liệu cũ. Tuy nhiên downgrade sẽ xóa toàn bộ lựa chọn CMS/Udemy đã cấu hình trong bảng mới.

```bash
docker compose \
  --env-file .env.production \
  -f docker-compose.prod.yml \
  run --rm --no-deps \
  backend \
  alembic -c alembic.ini downgrade 0053_v25_9_16_7_2_64_16_5_4
```

Sau đó khôi phục source/image Batch 30 và recreate `backend`, `worker`, `worker-analytics`, `frontend`.

## 8. Kết quả kiểm tra trước khi đóng gói

```text
Python py_compile: PASS
Focused regression Batch 31: 4 passed
TypeScript/TSX syntax transpile: PASS
Alembic heads với SQLite test env: 0054... (một head)
ZIP integrity: PASS (full source và deploy patch)
```

Chưa thực hiện trong môi trường hiện tại:

```text
Docker production build
Frontend npm typecheck/build đầy đủ
Browser E2E
Kết nối AP thật
Migration PostgreSQL UAT
```

Lý do frontend typecheck đầy đủ không chạy được trong môi trường đóng gói: `node_modules` không có và registry nội bộ trả 404 cho một package lockfile. Kiểm tra cú pháp các file TypeScript/TSX thay đổi đã đạt.

## 9. Lộ trình còn lại

```text
Batch 32 — Import và quản lý kế hoạch Udemy
Batch 33 — Import điểm/tiến độ Udemy bằng tác vụ nền
Batch 34 — Màn hình điểm, cảnh báo, export và tích hợp quản lý đào tạo
Batch 35 — Migration dữ liệu ACMS cũ, hardening và kiểm thử production
```
