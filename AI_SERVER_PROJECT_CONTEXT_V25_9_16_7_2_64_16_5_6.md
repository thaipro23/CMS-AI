# AI Server / Open edX CMS context — v25.9.16.7.2.64.16.5.6

## Baseline canonical

- Version: `v25.9.16.7.2.64.16.5.6`
- Release: `Frontend Runtime Contracts + Modal/Error Boundary`
- Zip: `ai-server-openedx-v25.9.16.7.2.64.16.5.6-frontend-runtime-contracts.zip`
- Root: `ai_server_openedx_v25_9_16_7_2_64_16_5_6`

Luôn tiếp tục trực tiếp từ source này, không quay lại baseline cũ.

## Thay đổi chính

- Mọi active modal/drawer dùng `AccessibleDialog`.
- Focus trap, initial focus, Escape, nested stack, focus return và body scroll lock được chuẩn hóa.
- Native alert/confirm đã bị loại bỏ; dùng `FeedbackProvider`.
- App Router có loading/error/global-error/not-found.
- EnterpriseDataTable thực thi `defaultVisible`, `truncateLines` và server sort contract.
- Frontend runtime contract gate được tích hợp vào review/UAT gates.

## Boundary kế thừa

- Security P0/P1 closure từ `.64.16.5.4` phải giữ nguyên.
- Performance/API/Celery reliability từ `.64.16.5.5` phải giữ nguyên.
- SSO production cookie-only.
- Bank diff preview không mutate.
- Teacher export lớn chạy Celery queue `exports`.
- API frontend có timeout/cancellation/backoff.
- Celery workload được chia queue.

## Database

Không có migration mới. Head hiện tại:

`0053_v25_9_16_7_2_64_16_5_4_diff_idempotency.py`

## Verification

- Backend compileall: PASS.
- TypeScript: PASS.
- Focused tests: 16 passed.
- Frontend runtime gate: 13/13.
- Review pack: 28/28.
- Next production build: 30/30 + standalone.

## Bước tiếp theo

Roadmap ưu tiên:

1. `.64.16.5.7 — CI/E2E & Container Hardening`
2. `.64.16.5.8 — Maintainability Decomposition`
3. `.64.16.5.9 — Production Acceptance Closure`
4. `.65 — Production Rollout & Operational Closure`

Browser UAT với dữ liệu và role thật vẫn bắt buộc trước production-wide sign-off.
