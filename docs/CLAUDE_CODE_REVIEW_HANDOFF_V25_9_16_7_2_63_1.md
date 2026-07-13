# Claude Code Review Handoff — v25.9.16.7.2.64.12

Review target: **Maintainability + UI Contract Refactor / Ops Readiness Split**.

## Review focus

- `backend/app/schemas/readiness.py`
- `backend/app/services/maintainability_contract.py`
- `frontend/types/readiness.ts`
- `frontend/lib/api/readiness.ts`
- `frontend/components/readiness/OperationalGatePanel.tsx`
- `frontend/app/ops/readiness/page.tsx`
- `frontend/components/layout/AppShell.tsx`

## Preserved gates

- `GET /api/health/release-candidate`
- `GET /api/health/pilot-operations`
- `GET /api/health/maintainability-contract`
- `GET /api/health/query-hotspots`

## Expected properties

- Ops readiness UI is read-only.
- No database mutation, no job enqueue, no raw tracking log scan.
- New readiness code imports from `frontend/lib/api/readiness.ts` and `frontend/types/readiness.ts`.
- Existing analytics workflow remains backward compatible.
