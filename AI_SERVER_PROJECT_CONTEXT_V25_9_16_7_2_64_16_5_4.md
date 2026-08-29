# AI Server / Open edX CMS — Context v25.9.16.7.2.64.16.5.4

## Baseline mới nhất

```text
v25.9.16.7.2.64.16.5.4 — Production Security P0/P1 Closure
zip: ai-server-openedx-v25.9.16.7.2.64.16.5.4-production-security-p0-p1-closure.zip
root: ai_server_openedx_v25_9_16_7_2_64_16_5_4
```

Tiếp tục trực tiếp từ `.64.16.5.3`.

## Thay đổi canonical

- Bank diff preview tuyệt đối read-only, `persist=False`.
- Lưu diff là endpoint riêng, yêu cầu `edit_questions` + `question.edit`.
- Diff persist có deterministic idempotency key, unique constraint và concurrent-race reuse.
- Production Open edX SSO dùng cookie HttpOnly-only; token không đi qua JS response/state.
- CMS bridge ticket có `jti`, tuổi 30–60 giây, Redis one-time claim và rate limit.
- JWT session có `jti`, TTL tối đa 2 giờ, logout/revoke qua Redis.
- Không còn `detail=str(exc)` trong route; error public được sanitize và có request ID.
- Table page size hỗ trợ 10/20/50/100; `defaultVisible` hoạt động thật.
- Có gate `scripts/production-security-closure-report.sh`.

## Database

Latest migration:

```text
0053_v25_9_16_7_2_64_16_5_4_diff_idempotency.py
```

`down_revision = 0052_v25_9_16_7_2_27`.

## Boundary giữ nguyên

- Bank hierarchy: Bộ môn → Môn → một phiên bản cuối theo học kỳ → Bài → Câu hỏi.
- Release/Quiz là workflow đầu ra.
- Assignment score write vẫn externalized.
- Backend enforce RBAC/scope.
- Heavy jobs vẫn qua Celery.
- Không reset DB, xóa volume hoặc sửa tay Alembic.

## Roadmap sau bản này

1. `.64.16.5.5` — Performance & Worker Reliability: async export, API timeout/cancel/backoff, Celery queues/reliability.
2. `.64.16.5.6` — Frontend Runtime Contracts: modal/a11y, route error boundary, toast/confirm, sortable/truncate table contract.
3. `.64.16.5.7` — CI/E2E & Container Hardening: PostgreSQL integration, Playwright, non-root/read-only/cap drop, migration deployment job.
4. `.64.16.5.8` — Maintainability decomposition: split API/types/services/CSS/god pages.
5. `.64.16.5.9` — Production acceptance and pilot evidence closure.
