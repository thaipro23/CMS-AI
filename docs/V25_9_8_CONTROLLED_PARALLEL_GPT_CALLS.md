# v25.9.8 - Controlled Parallel GPT Calls

Mục tiêu: tăng tốc generate bằng cách gọi GPT song song có kiểm soát, nhưng không bắn API ồ ạt gây 429/retry tốn tiền.

## Cách chạy batch

Ví dụ 50 câu, tỷ lệ 50/30/20, batch size 12:

```txt
EASY   25 = primary 12 + 12, delayed tail 1
MEDIUM 15 = primary 12,      delayed tail 3
HARD   10 = primary 10
```

Primary batches chạy trước với giới hạn song song `OPENAI_MAX_PARALLEL_CALLS`. Tail batch đợi primary xong, rồi gom phần lẻ và phần thiếu do primary lỗi/trùng:

```txt
Primary chạy: EASY 12, EASY 12, MEDIUM 12, HARD 10
Tail sau đó: EASY 1 + MEDIUM 3 + missing_from_failed_primary
```

Như vậy phần lẻ `1` và `3` không gọi riêng lẻ ngay từ đầu. Nó chờ xem các batch trước có lỗi không rồi gọi một thể để giảm request nhỏ và có cơ hội bù thiếu.

## Config

```env
OPENAI_PARALLEL_ENABLED=true
OPENAI_MAX_PARALLEL_CALLS=3
OPENAI_RETRY_MAX_ATTEMPTS=3
OPENAI_RETRY_BASE_SECONDS=2
GENERATION_TAIL_BATCH_WAIT_ENABLED=true
```

Default `max_parallel=3` để nhanh hơn tuần tự nhưng vẫn an toàn với rate limit.

## Batch tracking

Thêm bảng:

```txt
ai_generation_batches
```

Theo dõi từng batch:

```txt
phase: primary | tail | recovery | cache
status: queued | running | completed | partial_completed | failed | parse_failed | cache_hit
requested_questions
completed_questions
actual_input_tokens
actual_cached_input_tokens
actual_output_tokens
openai_response_id
error_message
```

API mới:

```txt
GET /api/jobs/{job_id}/batches
```

## Bảo toàn usage/cost

Nếu OpenAI trả response nhưng parse lỗi, hệ thống vẫn lưu usage/cost. Nếu primary lỗi trước khi có response, tail sẽ cố bù số câu thiếu.
