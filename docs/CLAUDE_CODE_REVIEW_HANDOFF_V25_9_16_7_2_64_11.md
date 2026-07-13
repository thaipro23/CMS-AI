# Claude Code Review Handoff — v25.9.16.7.2.64.12

Review target: **Security Attack Simulation + 20 Common Attack Hardening**.

Focus files:
- `backend/app/services/security_attack_simulation.py`
- `backend/app/core/security_headers.py`
- `backend/app/main.py`
- `backend/app/modules/openedx_connector/real.py`
- `openedx-unit-reset-plugin/openedx_unit_reset/views.py`
- `backend/app/api/routes/health.py`
- `frontend/app/ops/readiness/page.tsx`
- `scripts/security-attack-simulation-report.sh`

Expected properties:
- Read-only static attack simulation endpoint.
- No live exploit execution, brute force, network scan, external connector call, job enqueue, or DB mutation.
- Security headers applied globally.
- HMAC nonce/replay controls for connector/unit-reset.
- Upload pending filename uses `safe_upload_filename`.
