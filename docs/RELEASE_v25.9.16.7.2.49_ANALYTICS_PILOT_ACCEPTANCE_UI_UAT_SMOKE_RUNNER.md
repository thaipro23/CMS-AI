# Release v25.9.16.7.2.50 — UAT Evidence Pack + Acceptance Report Export

## Summary

This release surfaces the existing analytics pilot acceptance report directly in `/analytics/learning` and adds a UAT smoke runner script. It is read-only and safe for UAT/production verification.

## Changes

- Add `Kiểm thử pilot UAT` panel to `/analytics/learning`.
- Show pilot status, pilot readiness, broad-rollout readiness, checklist pass count, blocker/warning codes, pilot classes, sample students, and next actions.
- Add `scripts/analytics-uat-acceptance.sh` to verify build, readiness, RBAC scope, SLA, pilot acceptance, and class doctor in one command.
- Preserve all `.48` RBAC scope hardening and earlier analytics/bank/identity fixes.

## Safety

- No new Alembic migration.
- No job enqueue from the new UI panel.
- No recalculation in request.
- No raw tracking.log scan in request.
- No disciplinary/violation wording.
