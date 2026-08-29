# AI Server / Open edX CMS — Context v25.9.16.7.2.64.16.5.5

## Baseline bắt buộc

```text
v25.9.16.7.2.64.16.5.5 — Performance & Worker Reliability
zip: ai-server-openedx-v25.9.16.7.2.64.16.5.5-performance-worker-reliability.zip
root: ai_server_openedx_v25_9_16_7_2_64_16_5_5
```

Tiếp tục trực tiếp từ `.64.16.5.5`; không dùng baseline cũ nếu người dùng không yêu cầu rõ.

## Database

Không có migration mới. Latest:

```text
0053_v25_9_16_7_2_64_16_5_4_diff_idempotency.py
```

## Contract mới

- Export báo cáo giảng viên lớn phải chạy background job; sync export chỉ cho dataset nhỏ có cap.
- API client dùng timeout, cancellation, request ID, bounded retry và auth-expiry event.
- Polling job dùng exponential backoff và AbortController.
- RBAC scope catalog dùng server-side search; không tải toàn bộ hierarchy.
- Celery workload tách queue/pool `interactive`, `sync`, `generation`, `exports`, `analytics`.
- Worker dùng late ack, reject-on-lost, prefetch 1, time limit và process recycling.
- Class analytics recalculate lọc tracking events theo roster AP của lớp.
- P0/P1 security closure của `.64.16.5.4` vẫn bắt buộc: read-only diff preview, cookie-only SSO, one-time ticket, logout/revoke và public error envelope.

## Quy tắc giữ nguyên

- Không reset DB, xóa volume hoặc sửa tay Alembic.
- Không khôi phục Assignment score write.
- Không thay Bank hierarchy, Release membership hoặc Open edX publish semantics.
- Backend enforce RBAC; frontend chỉ ẩn/hiện UI.
- Không trả raw exception cho người dùng.

## Việc tiếp theo đề xuất

```text
.64.16.5.6 — Frontend Runtime Contracts + Modal/Error Boundary
.64.16.5.7 — CI/E2E & Container Hardening
.64.16.5.8 — Maintainability Decomposition
.64.16.5.9 — Production Acceptance Closure
```

Trước khi tăng concurrency production, phải load test queue latency, memory và redelivery trên UAT.
