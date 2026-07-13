# Claude Code Review Handoff — v25.9.16.7.2.64.12

Baseline:

```text
v25.9.16.7.2.64.12 — UAT Runtime Verification + Frontend Build Fix
```

## Review focus for `.53`

1. Confirm no business feature regression from `.52`.
2. Verify frontend build metadata is no longer stale:
   - `frontend/package-lock.json`,
   - `frontend/Dockerfile`,
   - `frontend/package.json`,
   - `docker-compose.prod.yml`.
3. Review `scripts/frontend-build-verify.sh` for safe UAT usage.
4. Review `scripts/uat-runtime-verify.sh` for read-only behavior and useful evidence.
5. Review `scripts/uat-build-gate.sh` integration with the frontend verifier.
6. Confirm no schema migration was added.

## Commands

```bash
cd /opt/ai-server

OUT_DIR=/tmp/ai-frontend-build-$(date +%Y%m%d-%H%M%S) \
EXPECTED_VERSION=25.9.16.7.2.64.12 \
RUN_NPM_CI=1 \
RUN_FRONTEND_BUILD=1 \
./scripts/frontend-build-verify.sh

OUT_DIR=/tmp/ai-runtime-verify-$(date +%Y%m%d-%H%M%S) \
API_BASE_URL=https://api-ai.cms-test.poly.edu.vn/api \
FRONTEND_URL=https://ai.cms-test.poly.edu.vn \
TOKEN='<TOKEN>' \
CLASS_ID='<CLASS_ID>' \
./scripts/uat-runtime-verify.sh

OUT_DIR=/tmp/ai-server-uat-build-gate-$(date +%Y%m%d-%H%M%S) \
STRICT=1 \
RUN_FRONTEND_BUILD=1 \
RUN_FRONTEND_INSTALL=1 \
RUN_REVIEW_PACK=1 \
./scripts/uat-build-gate.sh
```

## Guardrails

- Latest migration remains `0052_v25_9_16_7_2_27_learning_behavior_logic_calibration.py`.
- Scripts must not delete DB/volumes or mutate production data.
- Runtime verification must be read-only.
- Frontend build verifier may install npm dependencies in `frontend/node_modules` only when `RUN_NPM_CI=1`.
