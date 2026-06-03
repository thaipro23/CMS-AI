# v25.9.13.41 - Tutor plugin env injection

This release keeps the v25.9.13.40 production hardening and adds a safer Tutor-plugin-based configuration path for the Open edX CMS connector.

## Changes

- Added `tutor-plugins/ai_learning_connector_env.py`.
- Added `docs/TUTOR_PLUGIN_AI_CONNECTOR_ENV.md`.
- Updated `openedx_ai_connector.views` so connector config is read from process env first, then Django settings.
- This means Open edX/Tutor can receive `AI_CONNECTOR_*` values through the Tutor plugin instead of manual `docker-compose.override.yml` edits.

## What still must match

AI Server `.env.production`:

```env
OPENEDX_CONNECTOR_HMAC_SECRET=<secret>
```

Open edX Tutor config:

```env
AI_CONNECTOR_HMAC_SECRET=<same secret>
```

## Production note

Do not paste real secrets into chat/logs. If a secret was exposed, rotate it in both AI Server and Open edX Tutor config.
