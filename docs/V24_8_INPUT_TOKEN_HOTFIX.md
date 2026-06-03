# v24.8 - Responses Input Tokens Hotfix

## Mục tiêu

Sửa lỗi Estimate trả về `token_source = local_tiktoken_fallback_after_input_tokens_400` khi gọi `POST /v1/responses/input_tokens`.

## Nguyên nhân

Bản cũ gửi payload token-count giống payload generation, bao gồm cả field output/runtime như `store`. Endpoint `/v1/responses/input_tokens` chỉ dùng để đếm input token nên có thể nghiêm ngặt hơn `/v1/responses` và trả 400 với một số field.

## Cách sửa

`ModelGateway.count_responses_input_tokens_for_prompt()` giờ gọi token endpoint bằng payload riêng:

```json
{
  "model": "gpt-5-mini",
  "instructions": "Bạn là AI Learning Check Generator...",
  "input": "prompt thật",
  "text": {
    "format": {
      "type": "json_schema",
      "name": "learning_check_questions",
      "schema": {},
      "strict": true
    }
  }
}
```

Không gửi `store` sang `/v1/responses/input_tokens`.

Nếu OpenAI vẫn trả 400 do `text.format`/schema, backend tự retry payload tối giản:

```json
{
  "model": "gpt-5-mini",
  "instructions": "Bạn là AI Learning Check Generator...",
  "input": "prompt thật"
}
```

Sau đó cộng thêm local schema overhead để estimate vẫn an toàn cho hard stop.

## Token source mới

- `responses/input_tokens`: đếm bằng OpenAI token endpoint, payload có schema.
- `responses/input_tokens_minimal_plus_local_schema_overhead_after_400`: OpenAI từ chối payload có schema, retry minimal thành công, có cộng local schema overhead.
- `local_tiktoken_fallback_after_input_tokens_400_retry_...`: cả full và minimal đều fail, mới fallback local.

## Cost rule giữ nguyên

Estimate/hard stop vẫn nhân `safety_factor`.

Actual cost từ usage của `/v1/responses` không nhân `safety_factor`.
