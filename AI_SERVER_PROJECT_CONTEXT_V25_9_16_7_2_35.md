# CONTEXT DỰ ÁN AI SERVER / OPEN edX CMS — BASELINE v25.9.16.7.2.35

Ngôn ngữ làm việc: tiếng Việt.
Vai trò: senior full-stack engineer / backend architect / front-end engineer / UX reviewer thực dụng cho AI Server + Open edX CMS FPT Polytechnic.

## Baseline mới nhất

```text
v25.9.16.7.2.35 — Analytics Post-Ingest Recalculate Orchestrator
zip: ai-server-openedx-v25.9.16.7.2.35-analytics-post-ingest-recalculate-orchestrator.zip
root trong zip: ai_server_openedx_v25_9_16_7_2_35
```

Bản `.35` tiếp tục từ `.34` và `.33`:

- `.33`: sửa toolbar action chi tiết lớp + `/analytics/learning` roster fallback từ AP.
- `.34`: đồng bộ version/docs + QA snapshot coverage.
- `.35`: sau mỗi batch ingest tracking.log, hệ thống tự enqueue recalculate học online theo lớp/course bị ảnh hưởng, có throttle/cooldown/cap để an toàn production.

Không có migration mới. Latest migration vẫn là:

```text
0052_v25_9_16_7_2_27_learning_behavior_logic_calibration.py
```

## Lý do bản `.35`

Nếu recalculate toàn bộ mỗi phút thì không an toàn với quy mô khoảng 5.000 sinh viên, 300 course, ~15.000 lượt học/kỳ. Ingest có thể chạy mỗi phút, nhưng recalculate phải là incremental-orchestrated:

1. Chỉ lấy event mới trong batch ingest vừa đọc.
2. Gom theo `course_id` và danh sách username bị ảnh hưởng.
3. Resolve `course_id` sang `class_id`.
4. Enqueue job theo lớp/course, không enqueue theo từng sinh viên.
5. Debounce class vừa tính xong bằng cooldown.
6. Giới hạn số job tạo sau mỗi lần ingest.
7. Tôn trọng global active analytics job limit.

## Backend thay đổi chính

### `backend/app/services/learning_analytics/analytics_core_service.py`

Thêm import:

```python
from sqlalchemy import and_, case, func, or_, text
```

Trong `run_ingest(...)`:

- Tạo `impacted_course_usernames: dict[str, set[str]]`.
- Khi insert event mới có `course_id`, thêm vào impacted set.
- Sau commit ingest, gọi:

```python
self.enqueue_post_ingest_recalculate_jobs(
    course_usernames=impacted_course_usernames,
    source='analytics_ingest_task',
)
```

- Ghi summary vào checkpoint `stats_json['post_ingest_recalculate']`.

Thêm helper:

```text
_class_scope_filter(...)
_resolve_recalculate_class_ids_for_courses(...)
enqueue_post_ingest_recalculate_jobs(...)
```

Course → class resolution:

1. `AcademicClassCourseMapping` direct class mapping.
2. `AcademicCourseMapping` fallback theo term/subject/block/campus/branch.

Job tạo ra:

```text
AcademicClassSyncJob.job_type = learning_analytics_recalculate
requested_by = system:analytics-ingest
request_json.source = analytics_ingest_task
request_json.cooldown_seconds = ...
request_json.impacted_user_count = ...
request_json.impacted_usernames_sample = first 20 only
```

### `backend/app/core/config.py`

Thêm settings:

```python
analytics_post_ingest_recalculate_enabled: bool = True
analytics_post_ingest_recalculate_cooldown_seconds: int = 900
analytics_post_ingest_recalculate_max_jobs_per_run: int = 10
```

## Env mới

```env
ANALYTICS_POST_INGEST_RECALCULATE_ENABLED=true
ANALYTICS_POST_INGEST_RECALCULATE_COOLDOWN_SECONDS=900
ANALYTICS_POST_INGEST_RECALCULATE_MAX_JOBS_PER_RUN=10
```

Gợi ý UAT ban đầu:

```env
ANALYTICS_INGEST_INTERVAL_SECONDS=60
ANALYTICS_MAX_LINES_PER_RUN=50000
ANALYTICS_POST_INGEST_RECALCULATE_COOLDOWN_SECONDS=900
ANALYTICS_POST_INGEST_RECALCULATE_MAX_JOBS_PER_RUN=5
ANALYTICS_BACKFILL_MAX_ACTIVE_JOBS=10
```

Sau khi ổn định có thể tăng:

```env
ANALYTICS_POST_INGEST_RECALCULATE_MAX_JOBS_PER_RUN=10
ANALYTICS_BACKFILL_MAX_ACTIVE_JOBS=20
```

## Safety/UX

- Không recalculate toàn bộ mỗi phút.
- Không tạo job theo từng sinh viên.
- Không tạo job trùng lớp nếu đã queued/running.
- Không tạo lại lớp vừa tính trong cooldown.
- Nếu thiếu mapping Bài/Session/video, rule hiện có vẫn tạo snapshot mềm `Chưa đủ dữ liệu`.
- Không dùng wording `gian lận`, `cheating`, `vi phạm chắc chắn` trên UI.
- Người dùng vẫn có nút thủ công `Tính lại học online` ở chi tiết lớp làm fallback, nhưng luồng chính là tự động sau ingest.

## Files đáng chú ý

```text
RUN_CURRENT.md
RUN_V25_9_16_7_2_35.md
UX_UI_CONTEXT_V25_9_16_7_2_35.md
docs/RELEASE_v25.9.16.7.2.35_ANALYTICS_POST_INGEST_RECALCULATE_ORCHESTRATOR.md
backend/app/tests/test_v25_9_16_7_2_35_post_ingest_recalculate_orchestrator.py
```

## Deploy

```bash
cd /opt/ai-server
unzip -o ai-server-openedx-v25.9.16.7.2.35-analytics-post-ingest-recalculate-orchestrator.zip -d /tmp/ai-server-v25.9.16.7.2.35
rsync -a --delete /tmp/ai-server-v25.9.16.7.2.35/ai_server_openedx_v25_9_16_7_2_35/ /opt/ai-server/
docker compose -f docker-compose.prod.yml --env-file .env.production build backend frontend worker beat
docker compose -f docker-compose.prod.yml --env-file .env.production up -d --force-recreate backend frontend worker beat
```

## Verify sau deploy

```bash
cd /opt/ai-server
docker compose -f docker-compose.prod.yml --env-file .env.production ps
docker compose -f docker-compose.prod.yml --env-file .env.production exec backend alembic current
curl -sS https://api-ai.cms-test.poly.edu.vn/api/health | jq
```

Kiểm tra job tự động:

```bash
docker compose -f docker-compose.prod.yml --env-file .env.production logs --tail=200 worker | grep -E "analytics_ingest_task|analytics_class_recalculate_task|post_ingest"
```

Kỳ vọng:

```text
/jobs có job Tính lại học online sau khi ingest có event mới.
Không có hàng loạt job trùng cho cùng lớp mỗi phút.
request_json.source = analytics_ingest_task.
```
