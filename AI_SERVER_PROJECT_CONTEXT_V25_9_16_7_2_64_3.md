# CONTEXT DỰ ÁN AI SERVER / OPEN edX CMS — BASELINE v25.9.16.7.2.64.13

Ngôn ngữ làm việc: tiếng Việt. Vai trò: senior full-stack engineer / backend architect / front-end engineer / UX reviewer thực dụng cho AI Server + Open edX CMS FPT Polytechnic.

## Baseline mới nhất

```text
v25.9.16.7.2.64.13 — Analytics SLA/Evidence/Result Workflow Split
zip: ai-server-openedx-v25.9.16.7.2.64.13-analytics-sla-evidence-result-workflow-split.zip
root: ai_server_openedx_v25_9_16_7_2_64_13
```

Bản `.64.3` tiếp tục từ `.64.2` và không có migration mới. Latest migration vẫn là:

```text
0052_v25_9_16_7_2_27_learning_behavior_logic_calibration.py
```

## Mục tiêu `.64.3`

Tiếp tục tách maintainability theo từng workflow, lần này tập trung vào **Question Bank Release/Publish/Rollback/Audit**. Không đổi route contract, không đổi schema, không rewrite publish semantics khi chưa có integration test sâu với Open edX.

## Thay đổi chính

### Backend

Thêm module workflow:

```text
backend/app/services/question_bank/release_publish.py
```

Thêm service:

```text
QuestionBankReleasePublishWorkflowService
```

Các public/private methods trong `VersionedQuestionBankService` giờ delegate sang workflow mới:

```text
release_readiness
list_course_quiz_instances
rollback_course_quiz_instance
_normalize_release_term_slug
_release_offering_term_slug
release_library_key
_release_library_key_needs_term_upgrade
_library_key_same
_reset_release_openedx_state_for_key_change
_cleanup_stale_release_keys_for_chapter
_release_questions_for_version
create_release
cancel_failed_release
release_publish_audit
_release_publish_course_id
publish_release_to_openedx
```

Workflow mới dùng `__getattr__` delegation về parent service cho các helper thấp tầng còn lại, nên đây là behavior-preserving split thay vì rewrite lớn.

### Maintainability contract

Cập nhật:

```text
backend/app/services/maintainability_contract.py
```

Theo dõi thêm:

```text
backend/app/services/question_bank/release_publish.py
```

## Không đổi trong `.64.3`

```text
Không đổi schema database
Không đổi API route contract
Không đổi Open edX publish connector contract
Không đổi quiz creation flow
Không đổi bank dashboard/search flow
Không đổi academic/analytics runtime flow
```

## Tests/checks đã chạy

```text
v64.3-specific tests: 6 passed
selected v57-v64.3 regression: 68 passed
backend/app + Open edX connector + unit-reset compileall: passed
bash syntax: passed
claude-code-review-pack: PASS, failures=0, warnings=0
uat-build-gate sandbox: WARN only due missing backend deps/psycopg, frontend node_modules, Docker/.env.production, or skipped frontend/review
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

Verify:

```bash
curl -sS 'https://api-ai.cms-test.poly.edu.vn/api/health/maintainability-contract' \
  -H 'Authorization: Bearer <TOKEN>' | jq

curl -sS 'https://api-ai.cms-test.poly.edu.vn/api/health/production-pilot-final?branch=poly&campus=ph&sample_limit=5' \
  -H 'Authorization: Bearer <TOKEN>' | jq
```

## Roadmap workflow split tiếp theo

```text
.64.4 — Analytics SLA/Evidence/Result Workflow Split
.64.5 — Academic Sync/Enrollment Mutation Workflow Split
.64.6 — Question Bank Quiz Creation/Auto-map Workflow Split
```

## Quy tắc vẫn giữ nguyên

```text
Không fake dữ liệu
Không reset DB / không xóa volume / không sửa tay alembic_version
Không dùng wording gian lận/cheating trên UI
Tác vụ nặng chạy worker/job nền
Phân quyền enforce backend
Dashboard/health/readiness endpoints read-only
```
