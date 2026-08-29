# CONTEXT DỰ ÁN AI SERVER / OPEN edX CMS — BASELINE v25.9.16.7.2.64.13

Ngôn ngữ làm việc: tiếng Việt. Vai trò: senior full-stack engineer / backend architect / front-end engineer / UX reviewer thực dụng cho AI Server + Open edX CMS FPT Polytechnic.

## Baseline mới nhất

```text
v25.9.16.7.2.64.13 — Academic Sync/Enrollment Mutation Workflow Split
zip: ai-server-openedx-v25.9.16.7.2.64.13-academic-sync-enrollment-mutation-workflow-split.zip
root: ai_server_openedx_v25_9_16_7_2_64_13
```

Bản `.64.5` tiếp tục từ `.64.4` và không có migration mới. Latest migration vẫn là:

```text
0052_v25_9_16_7_2_27_learning_behavior_logic_calibration.py
```

## Mục tiêu `.64.5`

Tiếp tục refactor theo từng workflow, lần này tách nhóm mutation CMS/Open edX khỏi `academic_service.py` mà không đổi public API contract hoặc response shape.

## Thay đổi chính

### Academic Sync/Enrollment Mutation Workflow

Thêm module:

```text
backend/app/services/academic/sync_enrollment.py
```

Thêm service:

```text
AcademicSyncEnrollmentWorkflowService
```

`AcademicService` hiện delegate các method sau sang workflow mới:

```text
_student_cms_username
_student_cms_email
_student_cms_payload
_upsert_teacher_cms_metadata
resolve_class_openedx_users
_upsert_enrollment_snapshot
sync_class_course_enrollment
sync_class_learning_insight
_try_auto_map_course_for_class
sync_class_full_cms_flow
```

Các workflow đã tách trước đó vẫn được giữ:

```text
backend/app/services/academic/access.py
backend/app/services/academic/roster.py
backend/app/services/question_bank/release_publish.py
backend/app/services/learning_analytics/operations.py
backend/app/services/learning_analytics/results.py
backend/app/services/learning_analytics/presentation.py
backend/app/services/question_bank/helpers.py
backend/app/services/academic/helpers.py
```

## Safety/compatibility

```text
Không đổi route/API response shape.
Không đổi business rule Student Ops access.
Không đổi mapping RollNumber/CMS username rule.
Không đổi enrollment semantics.
Không đổi learning insight snapshot write behavior.
Không thêm migration.
Không rewrite Open edX connector behavior.
```

## Deploy

```bash
cd /opt/ai-server
unzip -o ai-server-openedx-v25.9.16.7.2.64.13-academic-sync-enrollment-mutation-workflow-split.zip -d /tmp/ai-server-v25.9.16.7.2.64.13
rsync -a --delete /tmp/ai-server-v25.9.16.7.2.64.13/ai_server_openedx_v25_9_16_7_2_64_13/ /opt/ai-server/
docker compose -f docker-compose.prod.yml --env-file .env.production build backend frontend worker beat
docker compose -f docker-compose.prod.yml --env-file .env.production up -d --force-recreate backend frontend worker beat
```

Env:

```env
APP_VERSION=25.9.16.7.2.64.13
NEXT_PUBLIC_APP_VERSION=25.9.16.7.2.64.13
```

## Verify

```bash
curl -sS 'https://api-ai.cms-test.poly.edu.vn/api/health/maintainability-contract' \
  -H 'Authorization: Bearer <TOKEN>' | jq

curl -sS 'https://api-ai.cms-test.poly.edu.vn/api/health/production-pilot-final?branch=poly&campus=ph&sample_limit=5' \
  -H 'Authorization: Bearer <TOKEN>' | jq
```

## Kết quả kiểm tra trong artifact

```text
v64.5-specific tests: 6 passed
selected v61-v64.5 regression: 61 passed
backend/app + Open edX connector + unit-reset compileall: passed
bash syntax: passed
claude-code-review-pack: PASS, failures=0, warnings=0
uat-build-gate sandbox: WARN, failures=0, warnings=4, passes=25
```

Sandbox WARN là do thiếu/skip:

```text
backend deps / psycopg
frontend/node_modules
Docker / .env.production
RUN_FRONTEND_BUILD=0
RUN_REVIEW_PACK=0
```

## Phần còn lại nên tách tiếp

```text
.64.6 — Question Bank Quiz Creation/Auto-map Workflow Split
.64.7 — Academic Sync Import/Reconciliation Workflow Split
.64.8 — Teacher Report Cache/Training Report Workflow Split
```
