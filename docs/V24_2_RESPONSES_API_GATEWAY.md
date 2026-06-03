# v24.2 - Responses API Gateway

## Mục tiêu

Bản v24.2 chuyển Model Gateway sang dùng OpenAI Responses API làm mặc định cho `gpt-5-mini`.

Luồng mới:

```text
AI Server
→ Cost Control Layer
→ Model Gateway
→ OpenAI Responses API /v1/responses
→ Structured JSON questions
→ Question Bank
→ Teacher Review
→ Chapter Library Publish
```

## Vì sao đổi sang Responses API

- Phù hợp hơn với GPT-5 mini và các model mới.
- Dùng Structured Outputs qua `text.format` thay vì `response_format` của Chat Completions.
- Output ổn định hơn cho schema `questions[]`.
- Chat Completions vẫn giữ dưới tên `chat_legacy` để fallback.

## Cấu hình mới

`.env` có thêm:

```env
OPENAI_API_MODE=responses
OPENAI_MODEL=gpt-5-mini
MOCK_LLM=false
OPENAI_API_KEY=sk-...
```

Trong trang `/settings`, admin có thể chọn:

```text
OpenAI API mode:
- responses: mặc định cho GPT-5 mini
- chat_legacy: fallback cũ cho OpenAI-compatible/local gateway
```

## Code chính đã sửa

```text
backend/app/services/model_gateway.py
backend/app/core/config.py
backend/app/schemas/settings.py
backend/app/services/runtime_settings.py
backend/app/api/routes/settings.py
frontend/app/settings/page.tsx
frontend/types/index.ts
frontend/lib/api.ts
```

## Hành vi mới

Nếu:

```text
MOCK_LLM=false
MODEL_PROVIDER=openai
OPENAI_API_MODE=responses
OPENAI_API_KEY có giá trị
```

thì Generate và Test GPT sẽ gọi:

```text
POST https://api.openai.com/v1/responses
```

Payload dùng:

```json
{
  "model": "gpt-5-mini",
  "input": [
    {"role": "system", "content": "Bạn là AI Learning Check Generator..."},
    {"role": "user", "content": "...prompt..."}
  ],
  "text": {
    "format": {
      "type": "json_schema",
      "name": "learning_check_questions",
      "schema": {"type": "object"},
      "strict": true
    }
  },
  "store": false
}
```

Gateway đọc output từ:

```text
response.output_text
hoặc output[].content[].text
```

rồi parse thành JSON:

```json
{
  "questions": []
}
```

## Local model

Nếu `MODEL_PROVIDER=local`, gateway vẫn dùng Chat Completions legacy vì phần lớn vLLM/local OpenAI-compatible server hiện ổn định hơn với `/v1/chat/completions`.

## Test

Vào `/settings`, admin bấm:

```text
Save settings
Test GPT
```

Nếu thành công sẽ thấy provider kiểu:

```text
openai_responses/gpt-5-mini qua responses
```
