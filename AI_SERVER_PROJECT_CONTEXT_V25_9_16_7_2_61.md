# AI Server / Open edX CMS — Context v25.9.16.7.2.64.13

## Baseline

```text
v25.9.16.7.2.64.13 — Auth/RBAC Security Boundary Hardening
zip: ai-server-openedx-v25.9.16.7.2.64.13-auth-rbac-security-boundary-hardening.zip
root: ai_server_openedx_v25_9_16_7_2_64_13
```

Bản `.61` tiếp tục từ `.60 Pilot Operations Runbook + Rollback Gate` và không có Alembic migration mới. Latest migration vẫn là:

```text
0052_v25_9_16_7_2_27_learning_behavior_logic_calibration.py
```

## Mục tiêu

Fix nhóm P0/P1 đầu tiên trong review `.60`: Auth/RBAC Security Boundary Hardening.

Quy tắc phân quyền mới:

```text
SYSTEM_ADMIN:
- Chỉ Open edX is_superuser / is_super_admin hoặc trusted ai_system_admin token.
- Open edX is_staff không còn auto admin.
- AI_ADMIN group không còn auto admin mặc định.

STUDENT_OPS:
- CAMPUS_OWNER / legacy CAMPUS_MANAGER
- TEACHER_ASSIGNED / AP teacher assignment
- Chỉ vận hành sinh viên/lớp/analytics/campus.

QUIZ_BANK:
- DEPARTMENT_HEAD
- SUBJECT_OWNER
- QUESTION_REVIEWER
- Chỉ vận hành bộ môn/môn/bank/review/release/quiz.
```

## Thay đổi chính

### Backend auth/SSO

File:

```text
backend/app/core/security.py
backend/app/api/routes/auth.py
openedx-connector-plugin/openedx_ai_connector/studio.py
```

Thay đổi:

- AI JWT `role=admin` bị reject nếu không có `is_superuser=true`, `is_super_admin=true` hoặc `ai_system_admin=true`.
- `/auth/openedx-session/exchange` chỉ cấp legacy `admin` nếu ticket từ Open edX superuser/super_admin.
- Open edX `is_staff` không tự thành AI admin.
- `AI_CONNECTOR_ADMIN_GROUPS` không còn auto-admin trừ khi bật opt-in `AI_CONNECTOR_ALLOW_ADMIN_GROUP=true`.

### Business RBAC domain split

File:

```text
backend/app/services/business_rbac.py
backend/app/schemas/rbac.py
backend/app/api/routes/rbac.py
frontend/app/users/page.tsx
frontend/types/index.ts
```

Thay đổi:

- Thêm role `CAMPUS_OWNER` và `TEACHER_ASSIGNED`.
- Giữ `CAMPUS_MANAGER` như legacy alias của chủ cơ sở.
- `ROLE_TO_LEGACY` không còn map `DEPARTMENT_HEAD`, `SUBJECT_OWNER`, `CAMPUS_OWNER/CAMPUS_MANAGER` thành legacy `teacher`.
- Non-admin business roles dùng `business_permissions`, không nâng role legacy.
- Import template RBAC hỗ trợ `CAMPUS_OWNER`, `TEACHER_ASSIGNED`, scope `CLASS`.

### Student Ops access

File:

```text
backend/app/api/routes/academic.py
backend/app/services/academic_service.py
```

Thay đổi:

- Academic sync/mutation không còn cho phép generic `sync_course` từ Bank role.
- Academic view không còn cho phép generic `view_questions`.
- `AcademicService.access_decision()` không còn dùng Bank subject ownership để cấp AP class/student visibility.
- Student Ops visibility chỉ đến từ system admin, campus role, hoặc AP teacher assignment.

### Unit Reset / quiz timer hardening

File:

```text
openedx-unit-reset-plugin/openedx_unit_reset/views.py
frontend-app-learning-patch/src/courseware/course/sequence/unit-reset/UnitResetButton.jsx
```

Thay đổi:

- `quiz_timer_config_upsert` csrf_exempt endpoint là HMAC-only.
- Staff cookie không còn được chấp nhận trên endpoint csrf_exempt này.
- Quiz timer `postMessage` không dùng wildcard target origin.
- Runtime JS kiểm tra allowed origin trước khi nhận timeout auto-submit message.

### CORS demo header hygiene

File:

```text
backend/app/main.py
```

Thay đổi:

- Production CORS không advertise `X-User-Role`, `X-User-Id`, `X-User-Email`, `X-Course-Ids`.
- Demo headers chỉ nằm trong allow headers khi không production và `ALLOW_DEMO_ROLE_HEADER=true`.

## Test/check đã chạy

```text
v61-specific tests: 7 passed
selected regression + auth/connector/rbac: 43 passed
backend/app + connector + unit reset compileall: passed
bash syntax scripts: passed
claude-code-review-pack: PASS, failures=0, warnings=0
```

Test đáng chú ý:

```text
backend/app/tests/test_v25_9_16_7_2_64_2_auth_rbac_security_boundary.py
backend/app/tests/test_openedx_connector_auth.py
backend/app/tests/test_v25_9_16_7_2_25_analytics_three_step_rbac_flow.py
backend/app/tests/test_v25_9_16_7_2_33_class_actions_behavior_roster_fallback.py
backend/app/tests/test_v25_9_16_7_2_48_campus_rbac_audit_hardening.py
backend/app/tests/test_v25_9_16_7_2_57_performance_load_hardening.py
backend/app/tests/test_v25_9_16_7_2_58_security_production_hardening.py
backend/app/tests/test_v25_9_16_7_2_59_pilot_release_candidate.py
backend/app/tests/test_v25_9_16_7_2_60_pilot_operations_runbook.py
```

## Deploy

```bash
cd /opt/ai-server
unzip -o ai-server-openedx-v25.9.16.7.2.64.13-auth-rbac-security-boundary-hardening.zip -d /tmp/ai-server-v25.9.16.7.2.64.13
rsync -a --delete /tmp/ai-server-v25.9.16.7.2.64.13/ai_server_openedx_v25_9_16_7_2_64_13/ /opt/ai-server/

docker compose -f docker-compose.prod.yml --env-file .env.production build backend frontend worker beat
docker compose -f docker-compose.prod.yml --env-file .env.production up -d --force-recreate backend frontend worker beat
```

Env:

```env
APP_VERSION=25.9.16.7.2.64.13
NEXT_PUBLIC_APP_VERSION=25.9.16.7.2.64.13
```

## Verify sau deploy

```bash
curl -sS 'https://api-ai.cms-test.poly.edu.vn/api/auth/me' \
  -H 'Authorization: Bearer <TOKEN>' | jq

curl -sS 'https://api-ai.cms-test.poly.edu.vn/api/rbac/me' \
  -H 'Authorization: Bearer <TOKEN>' | jq
```

Expected:

```text
Open edX superuser -> role admin / SYSTEM_ADMIN.
Open edX staff thường -> role viewer + business permissions nếu được phân công.
CAMPUS_OWNER/CAMPUS_MANAGER -> Student Ops only.
TEACHER_ASSIGNED/AP teacher -> lớp được AP phân công.
DEPARTMENT_HEAD/SUBJECT_OWNER/QUESTION_REVIEWER -> Quiz Bank only.
```

## Bước tiếp theo theo roadmap

```text
v25.9.16.7.2.64.13 — Query Hotspot + Load Hardening
```

Tập trung xử lý `.all()`, pagination/cursor, SQL aggregate/cache, query timing, lazy-load ops panels, và EXPLAIN UAT.
