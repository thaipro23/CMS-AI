# v24.9 - Actual Usage Reconciliation

Mục tiêu: sau khi generate xong, AI Server không chỉ lưu estimate trước khi chạy mà còn lưu usage thật do model trả về, để so sánh estimate vs actual.

## Luồng mới

1. Workflow/Generate build payload thật.
2. Estimate gọi `/v1/responses/input_tokens` để lấy input tokens trước khi enqueue.
3. Cost Control tính `estimated_raw_cost_usd` và `estimated_cost_usd`.
4. `estimated_cost_usd` vẫn nhân `safety_factor` để hard stop.
5. Worker gọi model thật.
6. Worker đọc usage thật từ response:
   - `input_tokens`
   - `input_tokens_details.cached_tokens`
   - `output_tokens`
7. Worker tính actual cost không nhân `safety_factor`.
8. Worker lưu reconciliation vào `ai_generation_jobs` và `ai_usage_log`.

## Field mới trong ai_generation_jobs

Estimate snapshot:

- `estimated_input_tokens`
- `estimated_cached_input_tokens`
- `estimated_uncached_input_tokens`
- `estimated_output_tokens`
- `estimated_raw_cost_usd`
- `estimated_cost_usd` - có safety factor
- `estimated_cost_vnd`
- `estimate_token_source`

Actual snapshot:

- `actual_input_tokens`
- `actual_cached_input_tokens`
- `actual_uncached_input_tokens`
- `actual_output_tokens`
- `actual_cost_usd` - không có safety factor
- `actual_cost_vnd`
- `usage_token_source`
- `estimate_accuracy_percent`

## Field mới trong ai_usage_log

- `uncached_input_tokens`
- `token_source`
- `raw_usage_json`

## Công thức actual cost

```text
uncached_input_tokens = input_tokens - cached_input_tokens

actual_cost =
  uncached_input_tokens / 1_000_000 * input_price
+ cached_input_tokens / 1_000_000 * cached_input_price
+ output_tokens / 1_000_000 * output_price
```

Actual cost không nhân `safety_factor`.

## Estimate accuracy

```text
estimate_accuracy_percent = 100 - abs(actual_cost - estimated_raw_cost) / actual_cost * 100
```

So sánh với `estimated_raw_cost_usd`, không so với `estimated_cost_usd`, vì `estimated_cost_usd` đã nhân safety factor.

## API/UI thay đổi

`GET /api/jobs` trả thêm:

- estimate tokens/cost
- actual tokens/cost
- cached tokens
- cost delta
- estimate accuracy
- token source

Dashboard thêm:

- Estimate accuracy
- Actual tokens
- Cost delta
- cached token count

User Analytics thêm:

- cached input tokens
- estimated cost
- actual cost
- estimate accuracy

