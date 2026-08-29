# Verification — v25.9.16.7.2.64.16.5.6

## Kết quả tự động

```text
Backend compileall: PASS
Frontend TypeScript: PASS
Focused release/performance tests: 16 passed
Frontend runtime contract: READY — 13/13
Production security closure: READY — 15/15
Performance & worker reliability: READY — 17/17
Backend runtime name audit: READY
Frontend layout integrity: READY
```

## Production frontend build

Build được chạy trên bản sao byte-for-byte ở local filesystem để tránh độ trễ bất thường của mounted artifact filesystem.

```text
Next.js 14.2.35
Compiled successfully
Type validation successful
Static pages: 30/30
Finalizing page optimization: completed
Collecting build traces: completed
.next/standalone/server.js: present
Exit status: 0
```

## Review pack

```text
Claude code review pack: PASS
28 pass
0 warning
0 failure
```

## UAT build gate trong môi trường artifact

```text
36 pass
4 warning
0 failure
```

Bốn cảnh báo là giới hạn môi trường kiểm tra, không phải source failure:

1. Python runtime hiện tại thiếu `psycopg`, nên UAT gate không tự collect backend integration tests.
2. Frontend build bị skip trong lần chạy UAT gate vì production build đã được chạy và xác nhận riêng.
3. Docker Compose config chưa thể xác nhận khi không có Docker và `.env.production` UAT.
4. Review pack bị skip trong lần UAT gate rút gọn; review pack đã chạy riêng và đạt 28/28.

## Kiểm tra browser bắt buộc trên UAT

- Modal giữ focus bên trong bằng Tab/Shift+Tab.
- Escape chỉ đóng modal trên cùng.
- Nested confirmation không phá body scroll lock.
- Focus trả về đúng nút mở sau khi đóng.
- Semesters viewport dialog không cuộn ngang.
- Question Review centered dialog hoạt động ở 390px, 768px và 1366px.
- Route error boundary hiển thị nút thử lại.
- Not-found route không làm mất AppShell ngoài production policy.
- Column visibility khôi phục đúng `defaultVisible`.
- Truncate 1/2/3 dòng có tooltip hoặc đường xem đầy đủ khi nghiệp vụ cần.
- Server sort giữ URL state và gọi backend đúng contract.

## Database

Không có migration mới. Alembic head:

```text
0053_v25_9_16_7_2_64_16_5_4_diff_idempotency.py
```
