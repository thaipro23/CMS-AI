# v25.9.13.42 - Scale and maintainability

This release implements the P1/P2 hardening pass after v25.9.13.40 production security hardening.

## P1 changes

1. Added composite indexes for production filters and dashboard queries.
2. Reworked `/api/analytics/overview` to aggregate in SQL instead of loading all rows into Python.
3. Changed file upload to bounded chunk reads; Open edX asset/transcript downloads now check `Content-Length` before streaming.
4. Added `Idempotency-Key` support and row-lock guards for generation, publish and rollback paths.
5. Added opt-in integration tests for a real Open edX CMS connector.
6. Added explicit Open edX lifecycle fields separate from teacher review status.

## P2 changes

1. Split sync page widgets into `frontend/components/sync/SyncCourseWidgets.tsx`.
2. Added `CHANGELOG.md` and an ADR for lifecycle state separation.
3. Added standardized API error envelope.
4. Added GitHub Actions CI for backend compile/tests and frontend typecheck/build.
5. Added production deployment notes for this release.

## Migration

```bash
cd backend
alembic upgrade head
```

## Compatibility

The legacy fields `Question.status` and `Question.publish_status` remain available for older UI screens. New production dashboards should prefer `openedx_publish_status`, `openedx_verification_status`, `openedx_delete_status` and `openedx_manual_action_required`.
