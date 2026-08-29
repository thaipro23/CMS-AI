# CONTEXT DỰ ÁN AI SERVER / OPEN edX CMS — BASELINE v25.9.16.7.2.64.13

Ngôn ngữ làm việc: tiếng Việt. Vai trò: senior full-stack engineer / backend architect / frontend engineer / UX reviewer thực dụng cho AI Server + Open edX CMS FPT Polytechnic.

## Baseline mới nhất

```text
v25.9.16.7.2.64.13 — Maintainability Service/UI Split Completion
zip: ai-server-openedx-v25.9.16.7.2.64.13-maintainability-service-ui-split-completion.zip
root: ai_server_openedx_v25_9_16_7_2_64_13
```

Bản `.64.1` tiếp tục từ `.64` và không có migration mới. Latest migration vẫn là:

```text
0052_v25_9_16_7_2_27_learning_behavior_logic_calibration.py
```

## Mục tiêu `.64.1`

Tiếp tục phần maintainability chưa xong sau `.63.1`: tách an toàn các phần helper/presentation/CSS ra khỏi các file lớn mà không refactor ẩu workflow nghiệp vụ nặng như sync, publish, enrollment, recalculate, analytics backfill.

## Thay đổi chính

### Backend service split

Thêm module helper thuần cho Academic:

```text
backend/app/services/academic/helpers.py
```

`academic_service.py` import lại các helper này để giữ compatibility:

```text
AccessDecision
_actor_names
_page
_boolish
_clean_token
_normalize_text_key
_natural_sort_key
_parse_openedx_course_id
_term_run_candidates
_suggest_course_run
_check
_validation_result
_json_safe_value
_safe_mapping_raw
_derive_mapping_status
```

Thêm module helper/constant thuần cho Question Bank:

```text
backend/app/services/question_bank/helpers.py
```

`question_bank_service.py` import lại helper/constant để giữ compatibility:

```text
slugify
normalize_text
normalize_code
normalize_title_match
extract_chapter_number
parse_openedx_course_id
normalize_academic_term_code
extract_block_course_tuple
title_similarity
safe_upload_filename
upload_extension
chunk_policy_for_material_source
bank_material_storage_dir
_ui_notice
BANK_UPLOAD_* constants
AUTO_RETIRE_* constants
```

Thêm presentation helper cho Learning Analytics:

```text
backend/app/services/learning_analytics/presentation.py
```

`analytics_core_service.py` gắn lại các staticmethod để không đổi call-site:

```text
_safe_label
_recommended_action_label
_parse_datetime_filter
_csv_setting_set
_sla_status
_timeline_weeks_from_sessions
_empty_class_behavior_overview_summary
_class_behavior_focus_count
_dominant_classification
_iso_or_none
```

### Frontend CSS split

Tách operational readiness/global gate CSS khỏi:

```text
frontend/app/globals.css
```

sang:

```text
frontend/styles/ops-readiness.css
```

`globals.css` import lại bằng:

```css
@import '../styles/ops-readiness.css';
```

### Maintainability gate

Cập nhật:

```text
backend/app/services/maintainability_contract.py
```

Gate hiện theo dõi thêm:

```text
backend/app/services/academic/helpers.py
backend/app/services/question_bank/helpers.py
backend/app/services/learning_analytics/presentation.py
frontend/styles/ops-readiness.css
```

## Safety

`.64.1` không làm các việc nguy hiểm:

```text
Không thêm migration
Không đổi schema
Không đổi API path nghiệp vụ
Không mutate dữ liệu
Không đổi publish/sync/enrollment/recalculate logic
Không đọc raw tracking.log mới trong request
Không thêm external call
```

## Kết quả kiểm tra

```text
v64.1-specific tests: 7 passed
selected v57-v64.1 regression: 56 passed
backend/app + Open edX connector + unit-reset compileall: passed
bash syntax: passed
claude-code-review-pack: PASS, failures=0, warnings=0
uat-build-gate sandbox: WARN do thiếu backend deps/psycopg, frontend node_modules, Docker/.env.production hoặc skip frontend/review
```

## Deploy

```bash
cd /opt/ai-server
unzip -o ai-server-openedx-v25.9.16.7.2.64.13-maintainability-service-ui-split-completion.zip -d /tmp/ai-server-v25.9.16.7.2.64.13
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
```

Final pilot gate của `.64` vẫn còn:

```bash
curl -sS 'https://api-ai.cms-test.poly.edu.vn/api/health/production-pilot-final?branch=poly&campus=ph&sample_limit=5' \
  -H 'Authorization: Bearer <TOKEN>' | jq
```

## Lưu ý tiếp theo

`.64.1` đã tách phần helper/presentation/CSS an toàn. Các phần còn lại trong `academic_service.py`, `question_bank_service.py`, `analytics_core_service.py` nên tiếp tục tách theo từng workflow có integration test riêng, ví dụ:

```text
academic roster/assignment workflow
question bank release/publish workflow
analytics SLA/evidence/result workflow
```
