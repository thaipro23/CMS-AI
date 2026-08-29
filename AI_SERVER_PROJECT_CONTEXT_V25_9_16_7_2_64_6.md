# CONTEXT DỰ ÁN AI SERVER / OPEN edX CMS — BASELINE v25.9.16.7.2.64.13

Ngôn ngữ làm việc: tiếng Việt. Vai trò: senior full-stack engineer / backend architect / frontend engineer / UX reviewer thực dụng cho AI Server + Open edX CMS FPT Polytechnic.

## Baseline mới nhất

```text
v25.9.16.7.2.64.13 — Question Bank Quiz Creation/Auto-map Workflow Split
zip: ai-server-openedx-v25.9.16.7.2.64.13-question-bank-quiz-creation-automap-workflow-split.zip
root: ai_server_openedx_v25_9_16_7_2_64_13
```

Bản `.64.6` tiếp tục từ `.64.5`, không có migration mới. Latest migration vẫn là:

```text
0052_v25_9_16_7_2_27_learning_behavior_logic_calibration.py
```

## Mục tiêu `.64.6`

Tiếp tục tách từng workflow còn lại để giảm God service, lần này tập trung vào **Question Bank Quiz Creation / Course CMS Auto-map / Native Problem Bank creation**.

## Thay đổi chính

### Question Bank Quiz Creation workflow

Thêm module:

```text
backend/app/services/question_bank/quiz_creation.py
```

Thêm service:

```text
QuestionBankQuizCreationWorkflowService
```

Đã tách khỏi `question_bank_service.py`:

```text
_latest_published_release_for_chapter
_release_component_ready
_offering_published_release_status
_quiz_action_for_chapter_title
_normalize_quiz_chapter_plan
_quiz_action_requires_release
_quiz_action_label
_quiz_production_status_for_mapping
_load_openedx_sections_for_quiz
_match_chapter_to_section
_format_offering_candidate
_select_offering_for_course
preview_quiz_auto_map
apply_quiz_auto_map
_validation_result
_target_counts_for_quiz
_published_release_question_rows
_build_release_quiz_plan
preview_quiz_from_release
create_quiz_from_release
```

`VersionedQuestionBankService` vẫn giữ public methods cũ và delegate sang workflow:

```text
_quiz_creation_workflow()
```

Không đổi route/API response shape.

## Behavior giữ nguyên

```text
- Preview/apply auto-map vẫn hỗ trợ quiz/final_test/assignment/skip.
- Final test vẫn map assessment_type='final_test'.
- Native Timed Exam vẫn bị chặn cho Quiz tự luyện.
- Custom timer vẫn force-save qua LMS unit-reset plugin sau khi có sequence/unit usage key thật.
- Native Problem Bank vẫn insert bằng connector.insert_problem_banks.
- Failed create vẫn đánh dấu CourseQuizInstance status='failed' kèm manual_cleanup_note.
```

## Maintainability

`question_bank_service.py` giảm còn khoảng 3153 dòng; workflow mới `question_bank/quiz_creation.py` khoảng 1164 dòng. `MaintainabilityContractService` đã track module mới.

## Tests/checks

```text
v64.6-specific tests: 6 passed
selected v61-v64.6 regression: 49 passed
backend/app + Open edX connector + unit-reset compileall: passed
bash syntax: passed
claude-code-review-pack: PASS, failures=0, warnings=0
uat-build-gate sandbox: WARN only do thiếu deps/node_modules/Docker/env hoặc skip frontend/review
```

## Deploy

```bash
cd /opt/ai-server

unzip -o ai-server-openedx-v25.9.16.7.2.64.13-question-bank-quiz-creation-automap-workflow-split.zip -d /tmp/ai-server-v25.9.16.7.2.64.13

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

## Roadmap tiếp theo

```text
.64.7 — Academic Sync Import/Reconciliation Workflow Split
.64.8 — Teacher Report Cache/Training Report Workflow Split
.64.9 — Question Bank Generation/Review Workflow Split
```
