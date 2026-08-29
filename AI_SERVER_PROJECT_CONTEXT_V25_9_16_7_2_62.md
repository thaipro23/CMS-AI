# CONTEXT DỰ ÁN AI SERVER / OPEN edX CMS — BASELINE v25.9.16.7.2.64.13

## Baseline mới nhất

```text
v25.9.16.7.2.64.13 — Query Hotspot + Load Hardening
zip: ai-server-openedx-v25.9.16.7.2.64.13-maintainability-ui-contract-refactor.zip
root: ai_server_openedx_v25_9_16_7_2_64_13
```

Bản `.62` tiếp tục từ `.61 Auth/RBAC Security Boundary Hardening` và **không có Alembic migration mới**. Latest migration vẫn là:

```text
0052_v25_9_16_7_2_27_learning_behavior_logic_calibration.py
```

## Mục tiêu `.62`

Xử lý nhóm hiệu năng/load hotspot đầu tiên trước khi mở rộng pilot:

- giảm N+1 query ở `/api/jobs`;
- chuyển các endpoint thống kê sang SQL aggregate;
- siết cap các endpoint legacy dễ trả response lớn;
- thêm request timing header;
- thêm static query hotspot gate để không bỏ sót `.all()` trên bảng lớn;
- thêm script evidence cho reviewer/UAT.

## Thay đổi backend chính

### 1. `/api/jobs` giảm N+1 query

File:

```text
backend/app/api/routes/jobs.py
```

Trước đây mỗi job lại query `GenerationBatch` riêng. `.62` đổi sang một query aggregate:

```text
GROUP BY job_id, status, phase
```

để dựng `batch_summary` cho 100 job gần nhất.

### 2. `/api/questions/stats` dùng SQL aggregate

File:

```text
backend/app/api/routes/questions.py
```

Thay vì load toàn bộ `Question` rồi count bằng Python, dùng:

```text
GROUP BY Question.status
```

### 3. `/api/questions/draft-errors/reasons` dùng SQL aggregate

Dùng:

```text
GROUP BY Question.draft_error_reason
```

### 4. Legacy `/api/questions` cap nhỏ hơn

Legacy list endpoint giảm cap:

```text
1000 -> 300
```

UI nên dùng endpoint phân trang `/api/questions/page`.

### 5. `/api/courses/{course_id}/topics` dùng SQL aggregate

File:

```text
backend/app/api/routes/courses.py
```

Chunk count/token count theo topic chuyển sang aggregate thay vì loop toàn bộ chunk.

### 6. `/api/audit` non-admin bounded window giảm

File:

```text
backend/app/api/routes/audit.py
```

Window scan sau RBAC filter giảm từ:

```text
max(1000, page * page_size * 10)
```

thành:

```text
min(500, max(100, page * page_size * 5))
```

### 7. Assignment-defense scores phân trang

File:

```text
backend/app/api/routes/academic.py
```

Endpoint list score theo lớp thêm:

```text
page
page_size <= 500
```

và dùng `offset/limit`.

### 8. Request timing header

File:

```text
backend/app/main.py
```

Mỗi response có:

```text
X-Process-Time-Ms
```

để smoke/load test đo nhanh latency request.

### 9. Query hotspot static gate

Thêm service:

```text
backend/app/services/query_hotspot.py
```

Thêm endpoint:

```text
GET /api/health/query-hotspots
```

Tính chất:

```text
read-only
static source scan
không query database
không chạy EXPLAIN/ANALYZE
không enqueue job
không mutate dữ liệu
```

## Scripts

Thêm:

```text
scripts/query-hotspot-report.sh
```

Script xuất:

```text
query-hotspots.json
QUERY_HOTSPOT_SUMMARY.md
```

Đã cập nhật:

```text
scripts/uat-runtime-verify.sh
scripts/uat-build-gate.sh
scripts/claude-code-review-pack.sh
```

để biết đến query hotspot gate.

## Kết quả kiểm tra trong artifact

```text
v62-specific tests: 6 passed
selected v57/v58/v59/v60/v61/v62 regression: 32 passed
backend/app + Open edX connector + unit-reset compileall: passed
bash syntax: passed
claude-code-review-pack: PASS, failures=0, warnings=0
uat-build-gate sandbox: WARN only because psycopg/frontend node_modules/Docker/.env.production are unavailable
```

## Hạn chế trung thực

`query-hotspots` static scan vẫn còn báo nhiều `.all()` hotspot/blocker trong các service lớn như `academic_service.py`, `question_bank_service.py`, `analytics_core_service.py`. `.62` **không cố sửa ẩu toàn bộ** vì nhiều chỗ là clone/export/backfill/publish logic cần hiểu nghiệp vụ và test dữ liệu thật. Bản này xử lý các hotspot request trực tiếp đầu tiên và tạo gate/evidence để tiếp tục xử lý có kiểm soát.

## Deploy

```bash
cd /opt/ai-server
unzip -o ai-server-openedx-v25.9.16.7.2.64.13-maintainability-ui-contract-refactor.zip -d /tmp/ai-server-v25.9.16.7.2.64.13
rsync -a --delete /tmp/ai-server-v25.9.16.7.2.64.13/ai_server_openedx_v25_9_16_7_2_64_13/ /opt/ai-server/

docker compose -f docker-compose.prod.yml --env-file .env.production build backend frontend worker beat
docker compose -f docker-compose.prod.yml --env-file .env.production up -d --force-recreate backend frontend worker beat
```

## Verify nhanh

```bash
curl -sS 'https://api-ai.cms-test.poly.edu.vn/api/health/query-hotspots?max_items=200' \
  -H 'Authorization: Bearer <TOKEN>' | jq
```

```bash
curl -sSI 'https://api-ai.cms-test.poly.edu.vn/api/health/build' | grep -i X-Process-Time-Ms
```

## Next roadmap

Theo kế hoạch 4 bản, bản tiếp theo:

```text
v25.9.16.7.2.64.13 — Maintainability + UI Contract Refactor
```

Nhưng nếu muốn triệt để hiệu năng hơn trước `.63`, nên làm thêm một nhánh `.62.x` để xử lý dần remaining query hotspots do `GET /api/health/query-hotspots` báo ra.
