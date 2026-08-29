# Verification — Bank redesign Batch 1

**Scope:** AppShell foundation and `/bank/departments` on baseline `v25.9.16.7.2.64.16.5.7.2.3`.

## Automated checks

| Check | Result | Evidence |
|---|---:|---|
| Frontend TypeScript strict check | PASS | `npm run typecheck` |
| Frontend ESLint, zero warnings | PASS | `npm run lint` |
| Next.js production build | PASS | 30/30 routes generated; `.next/standalone/server.js` present |
| Python compile | PASS | `python -m compileall -q backend/app` |
| Current baseline visual gates + Batch 1 source gates | PASS | 12/12 tests |
| Playwright Chromium desktop | PASS | 4/4 tests |
| Playwright Chromium mobile | PASS | 2/2 tests |
| Browser runtime errors | PASS | Every Playwright case asserts an empty `pageerror` list |

### Current source-gate command

```bash
PYTHONPATH=backend python -m pytest -q \
  backend/app/tests/test_v25_9_16_7_2_64_16_5_7_2_3_frontend_visual_ergonomics.py \
  backend/app/tests/test_bank_redesign_batch_one.py
```

Result: `12 passed`.

### Browser coverage

The `/bank/departments` route was rendered with authenticated API mocks at:

- 1440 × 960
- 1366 × 900
- 1024 × 768
- 768 × 900
- 390 × 844

Assertions cover:

- exactly one active Bank navigation item;
- fixed shell and main-only vertical scrolling;
- no body/document horizontal overflow;
- important table columns remain rendered;
- table-container-only horizontal scrolling at small widths;
- short result sets do not stretch the table section to viewport height;
- accessible create dialog initial focus, Escape close and focus return;
- mobile navigation drawer, overlay, Escape close and focus return;
- no browser runtime/hydration errors.

## Visual evidence

Files are committed in `docs/evidence/bank-redesign-batch-1/`:

```text
bank-departments-1440.png
bank-departments-1366.png
bank-departments-1024.png
bank-departments-768.png
bank-departments-390.png
bank-departments-390-drawer.png
bank-departments-create-dialog-1440.png
bank-departments-create-dialog-390.png
```

## Existing test-debt observation

A broader exploratory run included historical, version-locked source tests from `.64.16`, `.64.16.5.3` and `.64.16.5.7.2`. It produced `30 passed, 8 failed`. The failures assert obsolete literal versions, the removed global theme contract, an older hydration implementation, an older table constant name, or superseded Chapter button wording. These are stale historical assertions rather than browser/runtime regressions introduced by Batch 1. They were not rewritten in this batch because the request explicitly limits the first implementation scope and the current `.64.16.5.7.2.3` gate passes.

## Not verified in this environment

- real UAT SSO cookie exchange and CMS session bridge;
- live FastAPI/PostgreSQL data and production latency;
- every real role/scope combination (`SYSTEM_ADMIN`, `DEPARTMENT_HEAD`, `SUBJECT_OWNER`, `QUESTION_REVIEWER`);
- create/edit/delete against a live database and backend audit record;
- Chrome/Edge on the actual UAT host through VPN;
- production-like catalog volume.

No backend route, schema, migration, API contract, RBAC rule, Release/Quiz workflow, or Open edX integration semantics were changed.
