# v25.9.13.35 - Authoring Library URL Fix

## Changes
- Fix Studio authoring MFE library link path from `/authoring/libraries/{library_key}` to `/authoring/library/{library_key}`.
- Keep `OPENEDX_AUTHORING_MFE_BASE_URL` as the base, for example `http://apps.local.openedx.io/authoring`.

## Files changed
- `backend/app/modules/publisher/service.py`
- `backend/app/core/config.py`
- `frontend/package.json`
- `.env.example`
- `openedx-connector-plugin/openedx_ai_connector/views.py` version only
