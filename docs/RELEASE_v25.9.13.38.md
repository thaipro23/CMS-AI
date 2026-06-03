# v25.9.13.38 - Rollback Clean Usage Key NameError Fix

## Fixed

- Fixed `name _clean_openedx_usage_key is not defined` in AI Server rollback flow.
- Added the same usage-key normalizer directly to `backend/app/modules/publisher/service.py` so rollback can normalize JSON/URL-encoded Open edX usage keys before calling CMS connector delete/verify.

## Files changed

- `backend/app/modules/publisher/service.py`
- `backend/app/core/config.py`
- `frontend/package.json`
- `.env.example`
- `openedx-connector-plugin/openedx_ai_connector/views.py` version only
