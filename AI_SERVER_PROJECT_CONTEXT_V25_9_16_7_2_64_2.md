# CONTEXT DỰ ÁN AI SERVER / OPEN edX CMS — BASELINE v25.9.16.7.2.64.13

Ngôn ngữ làm việc: tiếng Việt. Vai trò: senior full-stack engineer / backend architect / front-end engineer / UX reviewer thực dụng cho AI Server + Open edX CMS FPT Polytechnic.

## Baseline mới nhất

```text
v25.9.16.7.2.64.13 — Academic Access/Roster Workflow Split
zip: ai-server-openedx-v25.9.16.7.2.64.13-analytics-sla-evidence-result-workflow-split.zip
root: ai_server_openedx_v25_9_16_7_2_64_13
```

Bản `.64.2` tiếp tục từ `.64.1`, không có migration mới. Latest migration vẫn là:

```text
0052_v25_9_16_7_2_27_learning_behavior_logic_calibration.py
```

## Mục tiêu `.64.2`

Tiếp tục hoàn thiện phần maintainability còn dang dở theo từng workflow, không refactor ẩu. Bản này tách workflow an toàn nhất trong `academic_service.py`:

```text
Student Ops access boundary
Class roster / list_class_students workflow
```

Các workflow mutation nặng như sync/enrollment/score update/publish/recalculate vẫn giữ nguyên để tránh regression.

## Thay đổi chính

### Academic access workflow

Thêm:

```text
backend/app/services/academic/access.py
```

Service:

```text
AcademicAccessWorkflowService
```

Phụ trách:

```text
access_decision(user)
assert_can_access_class(user, class_id)
assert_can_access_subject(user, subject_id)
```

Rule vẫn giữ:

```text
Student Ops visibility chỉ đến từ campus-scoped roles và AP teacher assignment.
Quiz Bank roles không tự cấp quyền xem lớp/sinh viên/AP analytics.
```

`AcademicService` delegate sang workflow mới để giữ backward-compatible API.

### Academic roster workflow

Thêm:

```text
backend/app/services/academic/roster.py
```

Service:

```text
AcademicRosterWorkflowService
```

Phụ trách:

```text
list_class_students(...)
learning_status filter
paging/search roster
assignment score hydration theo page_student_ids
quiz deadline schedule hydration cho visible page
student mapping item shaping qua parent service
```

`AcademicService.list_class_students(...)` giờ delegate sang workflow service mới, response shape không đổi.

### Maintainability contract

Cập nhật:

```text
backend/app/services/maintainability_contract.py
```

Theo dõi thêm:

```text
backend/app/services/academic/access.py
backend/app/services/academic/roster.py
```

## Safety

```text
Không có migration mới
Không đổi schema
Không đổi publish/sync/enrollment/recalculate/score mutation flows
Không thay đổi response contract của list_class_students
Không fake dữ liệu
Không reset DB/volume
```

## Test/check

```text
v64.3-specific tests: 6 passed
selected v57-v64.3 regression: 74 passed
backend/app + Open edX connector + unit-reset compileall: passed
bash syntax: passed
claude-code-review-pack: PASS, failures=0, warnings=0
uat-build-gate sandbox: WARN do thiếu deps/node_modules/Docker/.env.production hoặc skip frontend/review
```

## Deploy

```bash
cd /opt/ai-server
unzip -o ai-server-openedx-v25.9.16.7.2.64.13-analytics-sla-evidence-result-workflow-split.zip -d /tmp/ai-server-v25.9.16.7.2.64.13
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

## Việc còn lại nếu tiếp tục tách workflow

Nên làm tiếp từng bản nhỏ:

```text
.64.3 — Analytics SLA/Evidence/Result Workflow Split
.64.4 — Analytics SLA/Evidence/Result Workflow Split
.64.5 — Academic Sync/Enrollment Mutation Workflow Split
```

Không tách đồng thời nhiều workflow mutation nặng trong một bản.
