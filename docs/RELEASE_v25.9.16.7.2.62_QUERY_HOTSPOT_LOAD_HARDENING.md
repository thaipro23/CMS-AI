# v25.9.16.7.2.64.13 — Query Hotspot + Load Hardening

## Mục tiêu

Xử lý nhóm hiệu năng đầu tiên sau `.61`: giảm N+1 query, chuyển các endpoint stats sang SQL aggregate, siết cap endpoint legacy và thêm evidence report cho `.all()` hotspots.

## Thay đổi chính

- `/api/jobs` không còn query batch từng job; chuyển sang aggregate theo `job_id/status/phase`.
- `/api/questions/stats` dùng SQL `GROUP BY status` thay vì load toàn bộ questions.
- `/api/questions/draft-errors/reasons` dùng SQL aggregate theo reason.
- `/api/courses/{course_id}/topics` dùng aggregate chunk count/token count theo topic.
- `/api/audit` non-admin giảm bounded scan window từ 1000 xuống max 500.
- Legacy `/api/questions` cap từ 1000 xuống 300; UI nên dùng `/api/questions/page`.
- Thêm `X-Process-Time-Ms` response header.
- Thêm `GET /api/health/query-hotspots`.
- Thêm `scripts/query-hotspot-report.sh`.

## Safety

- Không migration mới.
- Không query database trong static hotspot scanner.
- Không chạy EXPLAIN/ANALYZE trong request.
- Không enqueue job hoặc mutate dữ liệu.

## Migration

Không có migration mới. Latest vẫn là `0052_v25_9_16_7_2_27_learning_behavior_logic_calibration.py`.
