# Verification — v25.9.16.7.2.64.16.3

## Static/compile checks

```text
Backend compileall: PASS
Frontend TypeScript: PASS
Shell syntax: PASS
Docker Compose YAML: PASS
```

## Tests

```text
Release contract .64.16.3: 9 passed
Selected current-contract regression: 63 passed
Historical assertions deselected: 14
```

Các assertion được deselect chỉ kiểm tra contract đã chủ động thay thế: version cũ, theme persistence toàn trang, selection column 52px cũ, hoặc readiness/security UI phải hiện trong production. Backend readiness/security endpoints và static service vẫn được giữ.

## Production build

```text
Next.js 14.2.35
Compiled successfully
Type validation successful
Generated static pages: 29/29
Build traces: completed
.next/standalone/server.js: present
```

Route quan trọng đã build:

```text
/student-management
/student-management/subjects/[subjectId]/classes
/student-management/classes/[classId]
/teacher-management
/teacher-management/teachers/[teacherId]/classes
/analytics/learning
```

## Read-only source gates

```text
UAT UX acceptance: READY — 24/24, 0 blocker, 0 warning
Security attack simulation: READY — 20/20 protected
Maintainability: READY_WITH_WARNINGS — 0 blocker, 6 inherited warnings
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

- Browser UAT tại 1440px, 1024px, 768px và 390px.
- UAT bằng SYSTEM_ADMIN, CAMPUS_OWNER và TEACHER_ASSIGNED thật.
- Xác minh URL state, mapping Course CMS, loading/error/empty states và analytics rows bằng dữ liệu UAT.
- Không tuyên bố production sign-off chỉ dựa trên static source gate.
