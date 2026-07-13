# Release v25.9.16.7.2.64.13 — Performance Load Hardening

## Mục tiêu

Bổ sung cổng kiểm tra hiệu năng trước khi mở rộng UAT/pilot: cấu hình DB pool, page-size, batch connector, post-ingest job limit, index contract, queue pressure và table-growth estimates.

## Thay đổi chính

- Thêm `GET /api/health/performance-readiness`.
- Thêm `backend/app/services/performance_readiness.py`.
- Thêm panel `Hiệu năng vận hành` trong `/analytics/learning`.
- Thêm `scripts/performance-readiness-report.sh`.
- Runtime verify gọi thêm `/health/performance-readiness`.

## Safety

- Không scan raw `tracking.log` trong request.
- Không chạy `EXPLAIN ANALYZE` hoặc query plan nặng.
- Không enqueue job, không recalculate, không mutate DB.
- Không migration mới.

## Migration

Không migration mới. Latest vẫn là:

```text
0052_v25_9_16_7_2_27_learning_behavior_logic_calibration.py
```
