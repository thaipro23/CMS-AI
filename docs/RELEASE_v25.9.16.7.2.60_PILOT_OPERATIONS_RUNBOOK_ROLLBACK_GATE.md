# v25.9.16.7.2.64.12 — Pilot Operations Runbook + Rollback Gate

## Mục tiêu

Biến `Pilot Release Candidate` ở `.59` thành checklist vận hành pilot có thể dùng thật: preflight, deploy window, warm-up, pilot monitoring, rollback decision, evidence required và sign-off.

## Thay đổi chính

- Thêm `GET /api/health/pilot-operations`.
- Thêm `PilotOperationsService` read-only.
- UI `/analytics/learning` có panel `Pilot operations runbook`.
- Thêm `scripts/pilot-operations-runbook.sh` để xuất `pilot-operations.json` và `PILOT_OPERATIONS_RUNBOOK.md`.
- `uat-runtime-verify.sh`, `uat-build-gate.sh`, `claude-code-review-pack.sh` kiểm tra thêm pilot operations gate.

## Safety

Endpoint/script không đọc raw tracking.log, không gọi Open edX/AP/OpenAI, không enqueue job, không recalculate, không publish/rollback Bank Release và không mutate DB.

## Migration

Không có migration mới. Latest migration vẫn là `0052_v25_9_16_7_2_27_learning_behavior_logic_calibration.py`.
