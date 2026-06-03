# v9 → v15 Release Notes

This release upgrades the starter from a UI/demo scaffold into a production-ready foundation.

## v9 — Backend structure + migrations
- Added module folders for auth, Open edX connector, model gateway, publisher, cost control and jobs.
- Added Alembic migration setup.
- Added `AUTO_CREATE_TABLES` switch: dev can auto-create tables, production should run migrations.

## v10 — Real Open edX Connector
- Added connector adapter pattern: `MockOpenEdXConnector` and `RealOpenEdXConnector`.
- `RealOpenEdXConnector` supports OAuth2/client credentials or static access token.
- Existing service `OpenEdxClient` now wraps the connector factory.

## v11 — Auth/RBAC production-ready path
- Added `auth_mode=demo|jwt|openedx_sso`.
- Demo still uses `X-User-Role` for local testing.
- JWT mode can use claims: `sub`, `email`, `role`, `courses`.
- Permissions are enforced on backend routes, not just UI.

## v12 — GPT-5 mini real gateway + local fallback
- Model Gateway supports `openai`, `local`, and `auto` routing.
- Local mode uses OpenAI-compatible serving such as vLLM.
- API calls remain centralized behind cost governance.

## v13 — Publish to Open edX
- Added publisher service that converts approved questions to OLX and sends them to the connector.
- Added endpoints to publish one question or all approved course questions.
- Mock connector returns a mock Open edX block id; real connector calls configured plugin endpoint.

## v14 — Tests + CI
- Added pytest tests for cost estimation, quality checker and OLX export.
- Added GitHub Actions CI for backend tests and frontend build.

## v15 — Production Docker + monitoring hooks
- Added `docker-compose.prod.yml`.
- Added Prometheus `/metrics` endpoint and optional Prometheus/Grafana profiles.
- Added storage/provider comments to keep MinIO dev/demo only unless approved.

## Recommended next real-integration work
1. Install the Open edX connector plugin into Tutor/Open edX.
2. Configure `USE_MOCK_OPENEDX=false` and Open edX OAuth credentials.
3. Replace demo role selector with Open edX SSO/JWT.
4. Configure `MOCK_LLM=false` and `OPENAI_API_KEY`.
5. Set `AUTO_CREATE_TABLES=false` in production and run `alembic upgrade head`.
