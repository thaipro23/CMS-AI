# v25.9.16.7.2.64.12 — Auth/RBAC Security Boundary Hardening

## Mục tiêu

Sửa ranh giới bảo mật/phân quyền trước production pilot rộng.

## Quy tắc mới

- Chỉ Open edX `is_superuser` / `is_super_admin` mới thành AI `SYSTEM_ADMIN` qua SSO bridge.
- `is_staff` Open edX không còn được map thành AI admin.
- `AI_ADMIN` group trong connector không auto-admin theo mặc định.
- Student Ops domain: `CAMPUS_OWNER`, legacy `CAMPUS_MANAGER`, `TEACHER_ASSIGNED`/AP teacher assignment.
- Quiz Bank domain: `DEPARTMENT_HEAD`, `SUBJECT_OWNER`, `QUESTION_REVIEWER`.
- Bank roles không mặc định xem lớp/sinh viên/analytics.
- Student Ops roles không mặc định có quyền Bank/Quiz.

## Backend chính

- `backend/app/core/security.py`
- `backend/app/api/routes/auth.py`
- `backend/app/services/business_rbac.py`
- `backend/app/api/routes/academic.py`
- `backend/app/services/academic_service.py`
- `openedx-connector-plugin/openedx_ai_connector/studio.py`
- `openedx-unit-reset-plugin/openedx_unit_reset/views.py`

## Frontend/Open edX MFE chính

- `frontend/context/AppContext.tsx`
- `frontend/app/users/page.tsx`
- `frontend/types/index.ts`
- `frontend-app-learning-patch/src/courseware/course/sequence/unit-reset/UnitResetButton.jsx`

## Safety

- No migration.
- No data reset.
- No fake data.
- No broad legacy role elevation.
- csrf_exempt timer config endpoint is HMAC-only.
- quiz timer postMessage no longer uses wildcard target origin.
