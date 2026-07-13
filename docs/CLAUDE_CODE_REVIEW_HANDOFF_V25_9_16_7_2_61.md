# Claude Code Review Handoff — v25.9.16.7.2.64.12

Review target: Auth/RBAC Security Boundary Hardening.

Preserved gates:
- GET /api/health/release-candidate
- GET /api/health/pilot-operations

Focus files:
- backend/app/core/security.py
- backend/app/api/routes/auth.py
- backend/app/services/business_rbac.py
- backend/app/api/routes/academic.py
- backend/app/services/academic_service.py
- openedx-connector-plugin/openedx_ai_connector/studio.py
- openedx-unit-reset-plugin/openedx_unit_reset/views.py

Review claims:
- Only Open edX superuser/super_admin becomes AI SYSTEM_ADMIN through SSO.
- Student Ops and Quiz Bank permissions are separated.
- csrf_exempt unit timer config write path is HMAC-only.
- postMessage target origins are no longer wildcard.
