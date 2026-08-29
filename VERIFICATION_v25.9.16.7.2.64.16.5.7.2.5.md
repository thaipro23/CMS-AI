# Verification — v25.9.16.7.2.64.16.5.7.2.5

## Đã kiểm tra trong môi trường đóng gói

- Regression Batch 31–35.1: **32 passed**.
- Python syntax cho test mới: PASS.
- TypeScript/TSX transpile syntax: **9 file PASS**.
- Cross-file TypeScript check với declaration stub cho external React/Next modules: PASS.
- CSS brace/token/legacy class contract: PASS.
- JSON/package-lock parse và version sync: PASS.
- `docker-compose.yml`: YAML parse, 8 services PASS.
- `docker-compose.prod.yml`: YAML parse, 12 services PASS.
- Alembic head giữ nguyên `0057`; không có migration `0058`: PASS.
- Static contract xác nhận không còn `udemy-action`, custom Udemy notice hoặc wording `file tổng hợp ACMS`: PASS.
- Static contract xác nhận import/export recovery, ARIA tabs/panels/progress và EnterpriseDataTable: PASS.
- ZIP integrity: PASS.
- Sensitive-file scan và artifact hygiene: PASS.

## Không thể chạy trong môi trường đóng gói

`npm ci` cho frontend và E2E không hoàn tất vì npm gateway của môi trường trả 404 cho package hợp lệ (`yocto-queue@0.1.0` và `playwright-core@1.61.1`). Vì không có `node_modules`, các bước sau chưa được thực thi tại đây:

- `npm run typecheck` bằng dependency thật.
- Next.js production build.
- Playwright Chromium desktop/mobile.

Đây là giới hạn repository của môi trường đóng gói, không phải kết quả build thất bại từ source. Bộ Playwright `e2e/tests/udemy-ui-ux.spec.ts` đã được thêm để chạy tại UAT/CI có registry đầy đủ.

## Acceptance còn bắt buộc trên UAT

- Frontend production build.
- Playwright desktop/mobile tại 1440/1366/1024/768/390 px.
- Import/export thật qua Redis/Celery và F5 recovery.
- Permission matrix system admin, teacher và campus owner.
- Browser console/runtime error evidence.

Không đánh dấu production UI accepted trước khi hoàn tất các mục UAT trên.
