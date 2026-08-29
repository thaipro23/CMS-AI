# CONTEXT DỰ ÁN AI SERVER / OPEN edX CMS — BASELINE v25.9.16.7.2.64.13

Ngôn ngữ làm việc: tiếng Việt. Vai trò: senior full-stack engineer / backend architect / frontend engineer / UX reviewer thực dụng cho AI Server + Open edX CMS FPT Polytechnic.

## Baseline mới nhất

```text
v25.9.16.7.2.64.13 — Analytics SLA/Evidence/Result Workflow Split
zip: ai-server-openedx-v25.9.16.7.2.64.13-analytics-sla-evidence-result-workflow-split.zip
root: ai_server_openedx_v25_9_16_7_2_64_13
```

Bản `.64.4` tiếp tục từ `.64.3`, không có migration mới. Latest migration vẫn là:

```text
0052_v25_9_16_7_2_27_learning_behavior_logic_calibration.py
```

## Mục tiêu `.64.4`

Tiếp tục tách maintainability theo từng workflow, tập trung vào các luồng analytics đọc/hiển thị lớn trong `analytics_core_service.py`:

```text
SLA vận hành
Pilot acceptance
UAT evidence pack
Learning dashboard/result
Export CSV
Video/student detail
Class behavior overview
Course-class mapping reliability
Class result doctor
Behavior summary/rows
```

Không đổi ingest/recalculate worker, không đổi route/API contract, không tạo migration.

## Module mới

```text
backend/app/services/learning_analytics/operations.py
backend/app/services/learning_analytics/results.py
```

### `operations.py`

Service:

```text
LearningAnalyticsOperationsWorkflowService
```

Chứa:

```text
analytics_sla_report
pilot_acceptance_report
analytics_uat_evidence_pack
```

### `results.py`

Service:

```text
LearningAnalyticsResultsWorkflowService
```

Chứa:

```text
learning_dashboard
export_learning_behavior_csv
video_students
student_behavior_detail
class_behavior_overview
analytics_course_class_mapping_reliability_report
class_result_doctor
behavior_summary
behavior_rows
```

## Core service behavior

`LearningAnalyticsCoreService` vẫn giữ public methods cũ, nhưng delegate sang workflow service:

```text
_analytics_operations_workflow()
_analytics_results_workflow()
```

Low-level helpers vẫn ở core để tránh rewrite sâu khi chưa có integration test đầy đủ:

```text
_course_for_class
_class_student_roster
_apply_behavior_common_filters
_class_course_mapping_diagnostics
analytics_enqueue_guard
production_readiness_report
analytics_data_quality_report
```

## Maintainability contract

`MaintainabilityContractService` theo dõi thêm:

```text
backend/app/services/learning_analytics/operations.py
backend/app/services/learning_analytics/results.py
backend/app/services/learning_analytics/presentation.py
```

## Safety

`.64.4` không làm các việc sau:

```text
Không đọc raw tracking.log trong request mới
Không đổi ingest/recalculate pipeline
Không enqueue job mới
Không mutate DB
Không đổi route/API response shape
Không đổi classifier/wording
Không đổi Open edX connector
Không tạo migration
```

## Tests/checks trong artifact

```text
v64.4-specific tests: 6 passed
selected v57-v64.4 regression: 74 passed
backend/app + Open edX connector + unit-reset compileall: passed
bash syntax: passed
claude-code-review-pack: PASS, failures=0, warnings=0
uat-build-gate sandbox: WARN only due missing deps/node_modules/Docker/env or skipped frontend/review
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

## Baseline trước đó

```text
.64.3 Question Bank Release/Publish Workflow Split
.64.2 Academic Access/Roster Workflow Split
.64.1 Maintainability Service/UI Split Completion
.64 Production Pilot Final QA + Rollback Drill
.63.1 Ops Readiness Split
.63 Maintainability + UI Contract Refactor
.62 Query Hotspot + Load Hardening
.61 Auth/RBAC Security Boundary Hardening
```

## Tiếp theo nên làm

```text
.64.5 — Academic Sync/Enrollment Mutation Workflow Split
.64.6 — Question Bank Quiz Creation/Auto-map Workflow Split
```
