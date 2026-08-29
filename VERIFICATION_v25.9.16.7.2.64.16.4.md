# Verification — v25.9.16.7.2.64.16.4

## Static and compile

```text
Backend compileall: PASS
Frontend TypeScript: PASS
Shell syntax: PASS
Docker Compose YAML: PASS
```

## Tests

```text
Release contract .64.16.4: 9 passed
Selected current-contract regression: 50 passed
Historical assertions deselected: 11
```

Các assertion bị deselect chỉ kiểm tra version cũ, layout/wording đã được thay thế, diagnostics UI từng hiển thị trong production, hoặc quyền ghi Assignment đã bị externalize. Không sửa ngược nghiệp vụ hiện tại để làm xanh các assertion đó.

## Production build

```text
Next.js 14.2.35
Compiled successfully
Type validation successful
Generated static pages: 29/29
Finalizing page optimization: completed
Collecting build traces: completed
.next/standalone/server.js: present
```

Route trọng điểm đã build:

```text
/jobs
/audit
/ap-sync
/premises
/semesters
/settings
/users
```

## Read-only source gates

```text
UAT UX acceptance: READY — 24/24, 0 blocker, 0 warning
Security attack simulation: READY — 20/20 protected
Maintainability: READY_WITH_WARNINGS — 0 blocker, 6 inherited warnings
```

Sáu cảnh báo maintainability kế thừa:

```text
backend/app/api/routes/academic.py
backend/app/api/routes/question_bank_v2.py
frontend/lib/api.ts
frontend/types/index.ts
frontend/app/analytics/learning/page.tsx
frontend/app/globals.css
```

## Database boundary

```text
New Alembic migration: none
Latest migration: 0052_v25_9_16_7_2_27_learning_behavior_logic_calibration.py
Database reset: not performed
Volume deletion: not performed
alembic_version manual edit: not performed
```

## Remaining acceptance work

Static/build verification không thay thế browser UAT. Cần kiểm tra role thật, dữ liệu thật, responsive, keyboard, focus, URL state và destructive confirmation trên UAT trước production sign-off.
