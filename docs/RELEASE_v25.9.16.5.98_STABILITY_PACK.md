# Release v25.9.16.5.98 Stability Pack

Bao gồm:

- v96 Production Build Verification + Smoke Test Pack
- v97 Connector Sync Contract Lock
- v98 Data Cache Invalidation

## Files touched

- `backend/app/api/routes/health.py`
- `backend/app/services/academic_service.py`
- `backend/app/services/openedx_student_insight.py`
- `openedx-connector-plugin/openedx_ai_connector/student_insight.py`
- `scripts/production-build-verify.sh`
- `scripts/smoke-test-prod.sh`
- `backend/app/tests/test_v25_9_16_5_98_connector_contract_and_cache.py`
- version bump in frontend package/AppShell

## Safety notes

- No database migration.
- No UI redesign.
- No change to quiz deadline policy.
- No change to Assignment workflow.
- Connector must be restarted on LMS/CMS after deploy.
