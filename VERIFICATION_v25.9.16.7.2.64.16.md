# Verification — v25.9.16.7.2.64.16

## Compile and static checks

```text
Backend compileall: PASS
Frontend TypeScript typecheck: PASS
Shell syntax: PASS
Docker Compose YAML parse: PASS
```

`npm run lint` is not claimed as passed because the inherited frontend has no ESLint configuration or ESLint packages; `next lint` opens the interactive setup prompt. No dependency or lint toolchain was added implicitly in this release.

## Automated tests

```text
.64.16 release contract: 10 passed
Selected RBAC/Analytics/Bank/Security regression: 42 passed
```

The selected regression suite excludes historical assertions that pin an older current-version string and assertions that require UAT/diagnostics interfaces to remain visible. Those interfaces are intentionally removed from the production frontend in `.64.16`.

## Frontend production build

Build environment:

```text
NEXT_PUBLIC_APP_ENV=production
NEXT_PUBLIC_ENABLE_DIAGNOSTICS_UI=false
NEXT_PUBLIC_APP_VERSION=25.9.16.7.2.64.16
Next.js 14.2.35
```

Result:

```text
Compiled successfully
Type validation successful
Generated static pages 29/29
Collecting build traces completed
.next/standalone/server.js created
```

Production UI checks:

```text
/ops/readiness is a frontend not-found route
No production static chunk contains “Kiểm tra GPT”
No production static chunk contains “Kiểm tra Open edX”
No production static chunk contains “Tính lại học online”
No production static chunk contains “UAT UX acceptance”
No production static chunk contains “Kiểm tra vận hành”
```

Backend readiness APIs remain available under their existing RBAC/security controls for monitoring and scripted evidence collection.

## Read-only source gates

```text
UAT UX acceptance source contract: READY — 24/24, 0 blocker, 0 warning
Security attack simulation: READY — 20/20 protected, 0 blocker, 0 warning
Maintainability contract: READY_WITH_WARNINGS — 0 blocker, 6 inherited large-file warnings
```

These source gates do not replace browser acceptance testing on the deployed production/UAT environment.

## Database boundary

```text
New Alembic migration: none
Latest migration: 0052_v25_9_16_7_2_27_learning_behavior_logic_calibration.py
```

No database reset, Docker volume deletion, manual `alembic_version` edit or identity cleanup is performed by this release.
