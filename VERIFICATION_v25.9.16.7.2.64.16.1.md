# Verification — v25.9.16.7.2.64.16.1

## Compile và static checks

```text
Backend compileall: PASS
Frontend TypeScript typecheck: PASS
Shell syntax: PASS
Docker Compose YAML parse: PASS
```

Không tuyên bố ESLint PASS vì baseline không có ESLint config/package và `next lint` mở interactive setup. Không tự thêm hoặc nâng dependency lint trong hotfix UI production.

## Automated tests

```text
.64.16.1 release contract: 11 passed
Selected backend workflow/RBAC/security regression: 35 passed
```

Một assertion lịch sử từ `.61` bị loại khỏi regression vì yêu cầu `academic.manage_assignment_scores` cho CAMPUS_OWNER; quyền ghi Assignment đã được externalize hợp lệ từ `.64.10` và endpoint write trả HTTP 410.

## Frontend production build

Build env:

```text
NEXT_PUBLIC_APP_ENV=production
NEXT_PUBLIC_ENABLE_DIAGNOSTICS_UI=false
NEXT_PUBLIC_APP_VERSION=25.9.16.7.2.64.16.1
Next.js 14.2.35
```

Kết quả:

```text
Compiled successfully
Type validation successful
Generated static pages 29/29
Collecting build traces completed
.next/standalone/server.js created
```

## Read-only source gates

```text
UAT UX acceptance source contract: READY — 24/24, 0 blocker, 0 warning
Security attack simulation: READY — 20/20 protected, 0 blocker, 0 warning
Maintainability contract: READY_WITH_WARNINGS — 0 blocker, 6 inherited large-file warnings
```

Các gate tĩnh không thay thế browser visual acceptance bằng dữ liệu và role thật.

## Database boundary

```text
New Alembic migration: none
Latest migration: 0052_v25_9_16_7_2_27_learning_behavior_logic_calibration.py
```

Không reset DB, không xóa Docker volume, không sửa tay `alembic_version`, không chạy identity cleanup.
