# v24.3 - Accurate Cost Metering

Mục tiêu: tính token/cost đúng hơn cho GPT thật qua Responses API.

## Thay đổi chính

1. Estimate trước khi generate dùng đúng payload thật và gọi:

```txt
POST https://api.openai.com/v1/responses/input_tokens
```

Backend build cùng prompt/schema/system instruction như lúc generate, rồi đếm input token trước khi queue job. Nếu job chia theo Node Coverage nhiều scope, backend gọi input token count cho từng model call dự kiến rồi cộng lại.

2. Estimate vẫn nhân `cost_safety_factor`.

Safety factor chỉ dùng cho Estimate và Hard Stop để phòng vượt ngân sách:

```txt
estimated_cost_usd = raw_estimated_cost_usd * cost_safety_factor
```

3. Actual cost không nhân safety factor.

Worker lấy usage thật từ Responses API:

```txt
input_tokens
input_tokens_details.cached_tokens
output_tokens
```

Rồi tính:

```txt
uncached_input_tokens = input_tokens - cached_input_tokens
actual_cost_usd =
  uncached_input_tokens / 1_000_000 * input_price
+ cached_input_tokens / 1_000_000 * cached_input_price
+ output_tokens / 1_000_000 * output_price
```

4. Có API lấy giá realtime:

```txt
GET /api/cost/pricing/realtime?model=gpt-5.4-mini&refresh=true
```

API này fetch trang pricing chính thức của OpenAI, parse giá Standard short-context, cache vào `/app/.runtime/openai-pricing-cache.json`, sau đó trả về giá input/cached/output. Nếu không có internet, model không xuất hiện trên pricing page, hoặc page đổi format, backend fallback về bảng giá project/admin settings.

5. Settings có thêm Cost Metering/Pricing.

Admin có thể chỉnh:

```txt
input price / 1M
cached input price / 1M
output price / 1M
safety factor
USD_TO_VND
```

## Endpoint cập nhật

```txt
POST /api/cost/estimate
GET  /api/cost/pricing/realtime
POST /api/questions/generate
```

`POST /api/cost/estimate` giờ có thể nhận cùng selection như generate:

```json
{
  "course_id": "course-v1:Business-Administration+DOM1051+FPS2026",
  "question_count": 20,
  "chunk_ids": ["chunk-id-1", "chunk-id-2"],
  "node_ids": ["block-v1:..."],
  "batch_size": 20,
  "use_node_coverage": true,
  "refresh_pricing": false
}
```

Response có thêm:

```json
{
  "estimated_input_tokens": 12345,
  "estimated_cached_input_tokens": 0,
  "estimated_uncached_input_tokens": 12345,
  "estimated_output_tokens": 6400,
  "estimated_raw_cost_usd": 0.01,
  "estimated_cost_usd": 0.015,
  "safety_factor": 1.5,
  "token_source": "responses/input_tokens",
  "pricing": {
    "source": "openai_pricing_page_cache"
  }
}
```

## Lưu ý production

OpenAI pricing có thể thay đổi, vì vậy không nên hard-code duy nhất trong code. Bản này ưu tiên realtime/cached pricing, fallback về admin settings để hệ thống vẫn chạy khi mất mạng.
