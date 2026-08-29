# CONTEXT DỰ ÁN AI SERVER / OPEN edX CMS — BASELINE v25.9.16.7.2.64.13

Ngôn ngữ làm việc: tiếng Việt. Vai trò: senior full-stack engineer / backend architect / front-end engineer / UX reviewer thực dụng cho AI Server + Open edX CMS FPT Polytechnic.

## Baseline mới nhất

```text
v25.9.16.7.2.64.13 — Teacher Report Cache/Training Report Workflow Split
zip: ai-server-openedx-v25.9.16.7.2.64.13-teacher-report-cache-training-workflow-split.zip
root: ai_server_openedx_v25_9_16_7_2_64_13
```

Bản `.64.8` tiếp tục từ `.64.7`, không có migration mới. Latest migration vẫn là:

```text
0052_v25_9_16_7_2_27_learning_behavior_logic_calibration.py
```

## Mục tiêu `.64.8`

Tiếp tục tách maintainability theo từng workflow. Bản này tách phần teacher-management/training report/cache ra khỏi `academic_service.py` nhưng giữ nguyên route/API response shape và cache semantics.

## Thay đổi chính

### Backend

Thêm module:

```text
backend/app/services/academic/teacher_report.py
```

Thêm service:

```text
AcademicTeacherReportWorkflowService
```

`AcademicService` hiện delegate các method:

```text
_teacher_report_scope_key
_teacher_report_search_match
_teacher_report_item_matches_filter
_teacher_report_item_allowed_for_decision
_teacher_report_public_item
_teacher_report_summary_from_items
_training_teacher_report_lite_fast
_training_teacher_report_from_cache
rebuild_training_teacher_report_cache
training_teacher_report
```

Các public route/worker vẫn gọi qua `AcademicService`, nên không đổi external contract:

```text
GET /api/academic/training/teachers
GET /api/academic/training/teachers/export
Celery teacher report rebuild/export jobs
```

### Maintainability contract

`backend/app/services/maintainability_contract.py` theo dõi thêm:

```text
backend/app/services/academic/teacher_report.py
```

## Safety

```text
Không migration
Không đổi Student Ops access boundary
Không đổi teacher report route/API response shape
Không đổi cache status: hit/lite/miss/bypass
Không đổi cache rebuild worker job semantics
Không đổi export teacher report semantics
Không đổi sync/enrollment/identity/publish/analytics behavior
```

## Checks đã chạy trong artifact

```text
v64.8-specific tests: 7 passed
selected academic workflow regression: 22 passed, 4 deselected stale doc-only checks
backend/app + Open edX connector + unit-reset compileall: passed
bash syntax: passed
claude-code-review-pack: PASS, failures=0, warnings=0
uat-build-gate sandbox: WARN only due missing deps/node_modules/Docker/env or skipped frontend/review
```

## Deploy

```bash
cd /opt/ai-server
unzip -o ai-server-openedx-v25.9.16.7.2.64.13-teacher-report-cache-training-workflow-split.zip -d /tmp/ai-server-v25.9.16.7.2.64.13
rsync -a --delete /tmp/ai-server-v25.9.16.7.2.64.13/ai_server_openedx_v25_9_16_7_2_64_13/ /opt/ai-server/
docker compose -f docker-compose.prod.yml --env-file .env.production build backend frontend worker beat
docker compose -f docker-compose.prod.yml --env-file .env.production up -d --force-recreate backend frontend worker beat
```

Set version:

```env
APP_VERSION=25.9.16.7.2.64.13
NEXT_PUBLIC_APP_VERSION=25.9.16.7.2.64.13
```

Verify:

```bash
curl -sS 'https://api-ai.cms-test.poly.edu.vn/api/health/maintainability-contract' \
  -H 'Authorization: Bearer <TOKEN>' | jq

curl -sS 'https://api-ai.cms-test.poly.edu.vn/api/health/production-pilot-final?branch=poly&campus=ph&sample_limit=5' \
  -H 'Authorization: Bearer <TOKEN>' | jq
```

## Phần còn lại nên tách tiếp

```text
.64.9 — Question Bank Generation/Review Workflow Split
.64.10 — Academic AP Sync Import/Reconciliation Workflow Split
.64.11 — Teacher Report Cache Optimization/Indexes if UAT EXPLAIN needs it
```
