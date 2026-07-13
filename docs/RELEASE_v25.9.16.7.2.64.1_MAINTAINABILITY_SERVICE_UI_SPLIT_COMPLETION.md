# v25.9.16.7.2.64.12 — Maintainability Service/UI Split Completion

## Mục tiêu

Tiếp tục phần còn dang dở sau `.63.1`: tách các phần an toàn khỏi những file lớn mà không refactor ẩu workflow nghiệp vụ nặng.

## Thay đổi chính

- Tách helper thuần của `academic_service.py` sang `backend/app/services/academic/helpers.py`.
- Tách helper/constant thuần của `question_bank_service.py` sang `backend/app/services/question_bank/helpers.py`.
- Tách presentation helper của `analytics_core_service.py` sang `backend/app/services/learning_analytics/presentation.py`.
- Tách ops/readiness CSS khỏi `frontend/app/globals.css` sang `frontend/styles/ops-readiness.css`.
- Maintainability contract theo dõi các module split mới.

## Safety

- Không đổi schema.
- Không thêm migration.
- Không thay đổi publish/sync/enrollment/recalculate logic.
- Không đổi API path nghiệp vụ.
- Không mutate dữ liệu.

## Migration

Không có migration mới. Latest migration vẫn là `0052_v25_9_16_7_2_27_learning_behavior_logic_calibration.py`.
