# v25.9.16.7.2.64.12 — UAT Runtime Verification + Frontend Build Fix

## Mục tiêu

Bản `.53` tiếp tục từ `.52` và tập trung vào **kiểm chứng build/runtime thật trên UAT** trước khi Claude AI hoặc reviewer kết luận chất lượng.

Không thêm nghiệp vụ mới, không đổi schema, không đổi classifier, không thay đổi RollNumber/CMS logic.

## Thay đổi chính

1. Sửa metadata frontend build bị stale:
   - `frontend/package-lock.json` version đồng bộ về `25.9.16.7.2.64.12`.
   - `frontend/Dockerfile` `NEXT_PUBLIC_APP_VERSION` fallback đồng bộ về `25.9.16.7.2.64.12`.

2. Thêm `scripts/frontend-build-verify.sh`:
   - kiểm tra `package.json`, `package-lock.json`, `Dockerfile`, `next.config.js`,
   - chạy `npm ci --include=dev` khi được bật,
   - chạy `npm run typecheck`,
   - chạy `npm run build`,
   - xác minh `.next/standalone/server.js` được tạo.

3. Thêm `scripts/uat-runtime-verify.sh`:
   - kiểm tra API `/health`, `/health/build`, `/health/readiness`,
   - kiểm tra RBAC scope audit,
   - kiểm tra analytics SLA, pilot acceptance, evidence pack,
   - kiểm tra frontend URL,
   - optional class doctor theo `CLASS_ID`,
   - xuất `RUNTIME_VERIFY_SUMMARY.md` và JSON evidence.

4. Nâng `scripts/uat-build-gate.sh`:
   - thêm version targets cho `frontend/Dockerfile`, `frontend/package-lock.json`, script verify mới,
   - gọi `frontend-build-verify.sh` khi `RUN_FRONTEND_BUILD=1`,
   - thêm `RUN_FRONTEND_INSTALL=1` để chạy `npm ci` trong UAT.

5. Nâng `scripts/claude-code-review-pack.sh`:
   - include frontend/runtime verification scripts,
   - ghi dependency status đầy đủ hơn,
   - hướng reviewer kiểm tra frontend build metadata.

## Safety

- Không migration mới.
- Không mutate dữ liệu.
- Không enqueue job.
- Không recalculate trong request.
- Không đọc raw tracking.log trong request.

## Latest migration

```text
0052_v25_9_16_7_2_27_learning_behavior_logic_calibration.py
```
