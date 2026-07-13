# v25.9.16.7.2.64.12 — Pilot Release Candidate

## Mục tiêu

Đóng gói bản RC cho UAT/pilot bằng một gate go/no-go tổng hợp, không thêm nghiệp vụ mới và không thay đổi schema.

## Thay đổi chính

- Thêm `GET /api/health/release-candidate`.
- Thêm `ReleaseCandidateService` gom:
  - Production readiness
  - Security readiness
  - Performance readiness
  - UAT evidence pack
  - Pilot acceptance
- UI `/analytics/learning` có panel `Pilot Release Candidate`.
- Thêm `scripts/pilot-release-candidate-report.sh` xuất `release-candidate.json` và `PILOT_RELEASE_CANDIDATE_SUMMARY.md`.
- `scripts/uat-runtime-verify.sh` kiểm tra thêm release candidate endpoint.
- Claude review pack/build gate biết đến RC script.

## Safety

Read-only hoàn toàn:

- Không đọc raw tracking.log trong request.
- Không gọi Open edX/AP/OpenAI trong request.
- Không enqueue job hoặc recalculate.
- Không publish/rollback Bank Release.
- Không mutate database.
- Không dùng wording kết luận vi phạm cá nhân.

## Migration

Không có migration mới. Latest vẫn là `0052_v25_9_16_7_2_27_learning_behavior_logic_calibration.py`.
