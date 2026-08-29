# CONTEXT DỰ ÁN AI SERVER / OPEN edX CMS — BASELINE v25.9.16.7.2.34

> Dùng file này để mở đoạn chat mới và tiếp tục phát triển.  
> Ngôn ngữ làm việc: tiếng Việt.  
> Vai trò mong muốn: senior full-stack engineer / backend architect / front-end engineer / UX reviewer thực dụng cho AI Server + Open edX CMS FPT Polytechnic.

## 0. Baseline mới nhất

```text
v25.9.16.7.2.34 — Production Polish Version Sync + Analytics Roster QA
zip: ai-server-openedx-v25.9.16.7.2.34-production-polish-version-sync-analytics-roster-qa.zip
root trong zip: ai_server_openedx_v25_9_16_7_2_34
```

Bản `.34` tiếp tục từ:

```text
v25.9.16.7.2.33 — Class Actions Toolbar + Learning Roster Fallback
```

Không có migration mới ở `.34`. Latest migration vẫn là:

```text
0052_v25_9_16_7_2_27_learning_behavior_logic_calibration.py
```

## 1. Stack kỹ thuật

```text
Frontend: Next.js + TypeScript
Backend: FastAPI + SQLAlchemy + Alembic
DB: PostgreSQL
Queue: Redis + Celery worker
Scheduler: Celery Beat
Open edX: Ulmo 3 / Tutor 21.0.6
```

Production/UAT hosts thường dùng:

```text
LMS: cms-test.poly.edu.vn
Studio/CMS: scms-test.poly.edu.vn
Learning MFE: app.cms-test.poly.edu.vn
AI Frontend: ai.cms-test.poly.edu.vn
AI Backend: api-ai.cms-test.poly.edu.vn
```

## 2. Thay đổi chính trong `.34`

1. Đồng bộ version/fallback về `25.9.16.7.2.34` ở:
   - `backend/app/core/config.py`
   - `frontend/package.json`
   - `docker-compose.prod.yml`
   - `frontend/components/layout/AppShell.tsx`
   - `.env.example`
   - `.env.production.example`
   - `README.md`
   - `RUN_CURRENT.md`

2. Dọn tài liệu:
   - `CHANGELOG.md` bắt đầu bằng `.34`, sau đó `.33`, sau đó `.32`.
   - Heading responsive sweep được sửa về `.30`, không còn ghi nhầm `.32`.
   - Thêm `RUN_V25_9_16_7_2_34.md`.
   - Thêm release note `.34` trong `docs/`.
   - Thêm `UX_UI_CONTEXT_V25_9_16_7_2_34.md`.

3. Analytics roster QA:
   - Class behavior overview có thêm `roster_count`, `snapshot_count`, `missing_snapshot_count`.
   - Behavior summary có thêm `roster_count`, `snapshot_count`, `missing_snapshot_count`, `data_status`.
   - Frontend `/analytics/learning` result view hiển thị thêm:
     - `Snapshot nhận định`: `snapshot_count/roster_count`
     - `Thiếu snapshot`: `missing_snapshot_count`

4. Tests:
   - Thêm `test_v25_9_16_7_2_34_version_sync_analytics_roster_qa.py`.
   - Cập nhật static tests cũ đang assert `.32` sang `.34`.

## 3. Thay đổi kế thừa quan trọng từ `.33`

1. `/student-management/classes/{class_id}`:
   - Toolbar action buttons cùng kích thước.
   - Desktop/laptop không bị ép thành một cột dọc.
   - Layout ngang và tự wrap; mobile responsive.

2. `/analytics/learning`:
   - AP roster là nguồn danh sách sinh viên gốc.
   - Sinh viên chưa có behavior snapshot vẫn hiện với nhãn `Chưa đủ dữ liệu`.
   - Fallback rows có reason `NO_BEHAVIOR_SNAPSHOT`.
   - Nếu có video/session progress nhưng chưa có snapshot, thêm `HAS_LEARNING_ACTIVITY`.

## 4. Quy tắc phát triển bắt buộc

1. Không fake dữ liệu. Nếu thiếu dữ liệu, UI ghi rõ `Chưa đủ dữ liệu`, `Chưa có snapshot`, `Chưa đồng bộ`.
2. Không reset DB, không xóa volume, không sửa tay `alembic_version`.
3. Không `docker compose down -v` trừ khi người dùng yêu cầu xóa dữ liệu rõ ràng.
4. Không dùng wording kết luận `gian lận`, `cheating`, `vi phạm chắc chắn`, `không học thật` trên UI.
5. Chỉ dùng nhãn mềm:
   - `Có dấu hiệu học thật`
   - `Có khả năng treo máy`
   - `Dấu hiệu bất thường cần kiểm tra`
   - `Chưa đủ dữ liệu`
   - `Chưa thấy bất thường rõ`
   - `Cần giáo viên xác minh`
6. Tác vụ nặng phải chạy worker/job nền.
7. RBAC phải enforce backend, không chỉ ẩn UI.
8. Bảng dài phải có STT và scroll ngang trong khung riêng.
9. Frontend không tự suy luận màu thông báo bằng keyword trong text; backend phải trả trạng thái rõ.

## 5. Deploy `.34`

```bash
cd /opt/ai-server

unzip -o ai-server-openedx-v25.9.16.7.2.34-production-polish-version-sync-analytics-roster-qa.zip -d /tmp/ai-server-v25.9.16.7.2.34

rsync -a --delete /tmp/ai-server-v25.9.16.7.2.34/ai_server_openedx_v25_9_16_7_2_34/ /opt/ai-server/

docker compose -f docker-compose.prod.yml --env-file .env.production build backend frontend worker

docker compose -f docker-compose.prod.yml --env-file .env.production up -d --force-recreate backend frontend worker
```

Nếu cần beat:

```bash
docker compose -f docker-compose.prod.yml --env-file .env.production build backend frontend worker beat

docker compose -f docker-compose.prod.yml --env-file .env.production up -d --force-recreate backend frontend worker beat
```

## 6. Env production nên set rõ

```env
APP_VERSION=25.9.16.7.2.34
NEXT_PUBLIC_APP_VERSION=25.9.16.7.2.34
NEXT_PUBLIC_API_BASE_URL=https://api-ai.cms-test.poly.edu.vn
FRONTEND_URL=https://ai.cms-test.poly.edu.vn
BACKEND_URL=https://api-ai.cms-test.poly.edu.vn
```

## 7. Verify nhanh sau deploy

```bash
cd /opt/ai-server

docker compose -f docker-compose.prod.yml --env-file .env.production ps

docker compose -f docker-compose.prod.yml --env-file .env.production exec backend alembic current

curl -sS https://api-ai.cms-test.poly.edu.vn/api/health | jq
```

Kỳ vọng:

```text
Version: 25.9.16.7.2.34
Alembic head: 0052_v25_9_16_7_2_27_learning_behavior_logic_calibration.py
```

## 8. Verify `/analytics/learning`

Mở:

```text
/analytics/learning?step=results&branch=poly&term_id=<TERM_ID>&campus=all&subject_id=<SUBJECT_ID>&class_id=<CLASS_ID>
```

Kỳ vọng:

```text
Tổng sinh viên = roster AP class.
Snapshot nhận định = snapshot_count/roster_count.
Thiếu snapshot = missing_snapshot_count.
Sinh viên thiếu snapshot vẫn hiện Chưa đủ dữ liệu.
Không báo sai 0 sinh viên nếu AP roster có sinh viên nhưng behavior snapshot chưa chạy.
```

## 9. Verify test đã chạy khi đóng gói

```text
10 passed
```

Test command đã chạy:

```bash
python3 -m pytest -q \
  backend/app/tests/test_v25_9_16_7_2_26_production_audit_hardening.py::test_version_is_synchronized_across_backend_frontend_and_footer \
  backend/app/tests/test_v25_9_16_7_2_30_responsive_device_ux.py::test_version_is_synchronized_for_current_release \
  backend/app/tests/test_v25_9_16_7_2_33_class_actions_behavior_roster_fallback.py \
  backend/app/tests/test_v25_9_16_7_2_34_version_sync_analytics_roster_qa.py
```

## 10. Việc có thể làm tiếp sau `.34`

1. Test production `/teacher-management` fast-lite với term thật.
2. Test production `/analytics/learning` trên 1–3 lớp thật có AP roster nhưng thiếu snapshot.
3. Rà `/bank/quiz` notice contract thêm bằng integration test nếu có token production.
4. Nếu `/analytics/learning` vẫn chậm ở lớp đông sinh viên, tối ưu query `_class_student_roster` và progress lookup bằng batch/index.
