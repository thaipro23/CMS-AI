# v25.9.16.7.2.64.13 — Maintainability Completion: Ops Readiness Split

## Mục tiêu

Tiếp tục `.63` cho đến phần maintainability thực dụng: tạo route vận hành riêng `/ops/readiness`, dùng split `frontend/lib/api/readiness.ts`, `frontend/types/readiness.ts`, và `OperationalGatePanel` thay vì tiếp tục nhồi operational gates vào màn nghiệp vụ.

## Thay đổi chính

- Thêm `/ops/readiness` cho Security, Performance, Release Candidate, Pilot Operations, Maintainability và Query Hotspot gates.
- Thêm `getQueryHotspots()` vào `frontend/lib/api/readiness.ts`.
- Thêm `QueryHotspotReport` vào `frontend/types/readiness.ts`.
- Thêm nav item `Readiness` trong nhóm Quản trị.
- Maintainability contract theo dõi thêm `/ops/readiness/page.tsx`.
- Không migration mới.

## Safety

- Trang `/ops/readiness` chỉ đọc.
- Không enqueue job.
- Không mutate dữ liệu.
- Không gọi raw tracking log.
- Không phá các endpoint cũ.
