# Verification — v25.9.16.7.2.64.15

## Static and compile gates

```text
Backend compileall: PASS
Frontend TypeScript typecheck: PASS
Shell syntax: PASS
Docker Compose YAML parse: PASS
```

## Automated tests

```text
.64.15 release contract: 11 passed
Selected analytics/RBAC/Bank regression: 27 passed
```

Historical source-string tests that pin an older current-version heading are intentionally not rewritten; the selected regression suite excludes only those stale version/text assertions.

## Frontend production build

```text
Next.js 14.2.35
Compiled successfully
Type validation successful
Generated static pages 29/29
Collecting build traces completed
.next/standalone created
```

## Read-only source gates

```text
UAT UX acceptance: READY — 24/24, 0 blocker, 0 warning
Security attack simulation: READY — 20/20, 0 blocker, 0 warning
Maintainability contract: READY_WITH_WARNINGS — 0 blocker, 6 inherited large-file warnings
```

These checks were executed against the `.64.15` source root. `backend/Dockerfile.prod` packages the same bounded source-contract snapshot at `/source-contract` so runtime checks do not report false missing-module blockers.

## Database boundary

```text
New migration: none
Latest migration: 0052_v25_9_16_7_2_27_learning_behavior_logic_calibration.py
ix_academic_classes_scope_lookup: declared in model metadata; migration 0050 remains source of schema creation
```

No database reset, volume deletion, manual `alembic_version` edit or identity cleanup is performed by this release.
