# v24.1 - Real GPT Runtime Hotfix

## Lỗi đã sửa

Ở bản trước, trang `/settings` lưu API key và `MOCK_LLM=false` vào runtime file trong container backend, mặc định `/tmp/ai-openedx-runtime-settings.json`.

Nhưng job generate chạy trong container `worker`. Backend và worker là 2 container khác nhau nên `/tmp` không dùng chung. Kết quả là UI báo đã có API key, backend đọc được settings, nhưng worker vẫn chạy theo `.env` cũ:

```env
MOCK_LLM=true
OPENAI_API_KEY=
```

Vì vậy generate vẫn ra mock hoặc job failed.

## Cách sửa

Runtime config đổi sang file dùng chung qua volume `/app`:

```env
RUNTIME_CONFIG_PATH=/app/.runtime/runtime-settings.json
```

Do `docker-compose.yml` đang mount `./backend:/app` cho cả `backend` và `worker`, nên cả hai container sẽ đọc cùng một file settings.

## File đã sửa

- `.env`
- `.env.example`
- `backend/app/services/runtime_settings.py`
- `backend/app/services/model_gateway.py`
- `backend/app/worker.py`
- `backend/app/api/routes/settings.py`
- `frontend/app/settings/page.tsx`
- `frontend/lib/api.ts`

## Thêm mới

Trang Settings có nút **Test GPT**.

Endpoint mới:

```http
POST /api/settings/runtime/test-model
```

Endpoint này chỉ admin dùng được. Nó gọi thử GPT thật với 1 câu hỏi nhỏ để kiểm tra API key/model/mock mode.

## Cách chạy lại

```bat
docker compose down
docker compose up --build
```

Sau đó vào:

```txt
http://localhost:3000/settings
```

Chọn:

```txt
Model provider: openai
Model name: gpt-5-mini
Bật MOCK_LLM: bỏ tick
OpenAI API key: nhập key
Save settings
Test GPT
```

Nếu Test GPT báo `provider: openai`, worker sẽ dùng GPT thật ở lần generate tiếp theo.
