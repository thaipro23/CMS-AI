# v25.9.16.7.2.64.12 — Maintainability + UI Contract Refactor

## Mục tiêu

Không thêm nghiệp vụ mới. Bản này tạo nền maintainability để dự án không tiếp tục phình các file lớn: chuẩn hóa Pydantic response contract cho readiness/gate endpoints, thêm frontend split modules và maintainability contract gate.

## Thay đổi chính

- Thêm `backend/app/schemas/readiness.py` với Pydantic contracts cho production/security/performance/query hotspot/release candidate/pilot operations/maintainability reports.
- Các readiness/gate endpoints trong `health.py` dùng `response_model` ổn định.
- Thêm `GET /api/health/maintainability-contract`.
- Thêm `backend/app/services/maintainability_contract.py` static source contract scan.
- Thêm `frontend/types/readiness.ts` và `frontend/lib/api/readiness.ts` để chặn tiếp tục phình monolithic `types/index.ts` và `lib/api.ts`.
- Thêm shared UI component `frontend/components/readiness/OperationalGatePanel.tsx` cho các gate UI sau này.
- Thêm `scripts/maintainability-contract-report.sh` và tích hợp vào runtime/build/review scripts.

## Safety

Read-only: không query database, không import heavy runtime modules, không enqueue job, không mutate dữ liệu, không migration.

## Known debt còn lại

Các large files vẫn còn lớn và được report thành warning, không che giấu: `academic_service.py`, `question_bank_service.py`, `analytics_core_service.py`, `frontend/lib/api.ts`, `frontend/types/index.ts`, `globals.css`.
