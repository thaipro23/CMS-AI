# v25.9.10 - Production Readiness Audit Fix

Phạm vi bản này theo yêu cầu: chưa làm Open edX connector plugin production và chưa hardening production SSO/CORS nâng cao. Hai mục đó để bản sau.

## Đã sửa

1. **Node Coverage token-weighted thật**
   - File: `backend/app/algorithms/node_coverage.py`
   - File: `backend/app/services/generation_planner.py`
   - Chia quota theo `effective_token_count` của nội dung học thật, không chia đều theo số node.
   - Lọc chunk giới thiệu/mục lục/quy định/lịch học/quá ngắn để không gửi vào GPT khi dùng Node Coverage.
   - Work item chỉ dùng các `teachable_chunk_ids` đã lọc.

2. **Audit log cho thao tác review/publish/batch**
   - File: `backend/app/api/routes/questions.py`
   - File: `backend/app/api/routes/publish.py`
   - File: `backend/app/worker.py`
   - Bổ sung log cho approve/reject/delete/repair/keep/status change/bulk approve/local publish/Open edX dry-run/Open edX publish/batch start/batch finish/job finish.

3. **Chuẩn hóa error type uppercase**
   - File: `backend/app/services/audit_log.py`
   - Error type chuẩn: `USER_ERROR`, `SYSTEM_ERROR`, `EXTERNAL_SERVICE_ERROR`, `VALIDATION_ERROR`, `AUTH_ERROR`.
   - Vẫn tương thích call cũ `user/system/external` bằng normalize.
   - Metadata audit tự redact key nhạy cảm như token, secret, api_key, password.

4. **Việt hóa thêm UI còn tiếng Anh**
   - Các trang/components chính đã đổi thêm nhãn tiếng Việt: dashboard, export, generate, audit, question filters/table/edit panel, cost estimate, diversity report.

5. **Migration chính thức v25.9.9/v25.9.10**
   - File: `backend/alembic/versions/0003_v25_9_9_readiness.py`
   - Bổ sung bảng/cột cho generation cache, token calibration, generation batches, audit logs, draft_error, duplicate, publish verification, usage reconciliation.
   - Normalize audit log cũ từ `user/system/external` sang uppercase.

6. **Version config**
   - Backend/frontend/env cập nhật lên `25.9.10`.

7. **Library resolution mở rộng**
   - File: `backend/app/services/library_service.py`
   - Không chỉ nhận `chapter` mà còn nhận `section/module/week` hoặc title chứa Chapter/Module/Week/Chương/Bài/Phần.
   - Nếu course thật không có chapter rõ, fallback về structural node phù hợp thay vì component/unit nhỏ.

## Cách chạy lại

```bash
docker compose down -v --remove-orphans
docker compose up --build
```

Production nên chạy migration:

```bash
cd backend
alembic upgrade head
```

Kiểm tra nhanh:

```bash
docker compose exec backend pytest -q
```

## Test GPT thật 50 câu 50/30/20

1. `.env`:

```env
MOCK_LLM=false
OPENAI_API_KEY=...
OPENAI_MODEL=gpt-5-mini
OPENAI_API_MODE=responses
OPENAI_PARALLEL_ENABLED=true
OPENAI_MAX_PARALLEL_CALLS=3
GENERATION_TAIL_BATCH_WAIT_ENABLED=true
OPENAI_PROMPT_CACHE_WARMUP_ENABLED=true
```

2. Vào `/workflow` hoặc `/generate`.
3. Chọn course đã sync, chọn node/chunk thật.
4. Số câu: `50`.
5. Tỷ lệ: Easy `50`, Medium `30`, Hard `20`.
6. Kiểm tra `/jobs/{job_id}/batches`:
   - EASY 25: primary 12 + 12, tail 1.
   - MEDIUM 15: primary 12, tail 3.
   - HARD 10: primary 10.
7. Kiểm tra `/audit` có batch start/finish/job finish.
8. Kiểm tra estimate vs actual: input/cached/output/cost.
