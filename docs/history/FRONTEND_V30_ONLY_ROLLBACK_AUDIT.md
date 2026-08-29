# Frontend v30 Only Rollback Audit — v25.9.16.5.36

## Scope

This package only restores AI Server `frontend/` from v25.9.16.5.30. It keeps non-frontend folders from v25.9.16.5.34 baseline.

## Verified

- `diff -qr v30/frontend work_v36_correct/frontend`: no differences.
- `diff -qr v34_non_frontend work_v36_correct_non_frontend`: no differences, except `CHANGELOG.md`, `README.md`, `RUN_V25_9_16_5_36.md`, and this audit document.
- Python compile check passed:

```bash
python3 -m compileall -q backend/app backend/alembic/versions openedx-connector-plugin/openedx_ai_connector openedx-unit-reset-plugin/openedx_unit_reset
```

- Frontend dependency install completed in sandbox:

```bash
cd frontend
npm ci --ignore-scripts --no-audit --no-fund
```

- Frontend TypeScript check passed:

```bash
npm run --silent typecheck
```

## Not claimed

`next build` was started and reached `Creating an optimized production build ...` but exceeded the sandbox timeout. This package does not claim a completed `next build` in sandbox. Build must be verified by Docker Compose on UAT.
