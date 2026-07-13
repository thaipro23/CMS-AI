# Claude Code Review Handoff — v25.9.16.7.2.64.12

Review target: **AI Server / Open edX CMS v25.9.16.7.2.64.12 — Query Hotspot + Load Hardening**.

## Review focus

- `backend/app/api/routes/jobs.py`: batch summary aggregate, no N+1 per job.
- `backend/app/api/routes/questions.py`: question stats and draft-error reasons use SQL aggregate.
- `backend/app/api/routes/courses.py`: topics use SQL aggregate for chunk/token counts.
- `backend/app/main.py`: `X-Process-Time-Ms` header.
- `backend/app/services/query_hotspot.py` and `GET /api/health/query-hotspots`.
- `scripts/query-hotspot-report.sh`.

## Preserved gates

- `GET /api/health/release-candidate` remains the Release Candidate gate.
- `GET /api/health/pilot-operations` remains the Pilot Operations runbook.
- Security/RBAC hardening from `.61` must remain intact.

## Expected properties

- No Alembic migration.
- No raw tracking log scan in request path.
- Query hotspot scanner is static/read-only and does not query DB.
- Hot endpoints should prefer pagination/aggregate queries over unbounded `.all()`.
