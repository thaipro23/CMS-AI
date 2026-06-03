# Chạy bản dev trên Windows

File `.env` đã được tạo sẵn ở thư mục gốc project.

Chạy bằng CMD:

```bat
cd ai-server-openedx-v23-compact-ui
docker compose up --build
```

Chạy bằng PowerShell:

```powershell
cd ai-server-openedx-v23-compact-ui
docker compose up --build
```

Mở:

- Frontend: http://localhost:3000
- Backend docs: http://localhost:8000/docs
- MinIO: http://localhost:9001

Nếu muốn dùng GPT thật:

1. Vào `/settings` bằng role admin.
2. Tắt `MOCK_LLM`.
3. Nhập `OPENAI_API_KEY`.
4. Giữ model `gpt-5-mini` hoặc đổi model bạn muốn.

Lưu ý: `.env` trong bản này là cấu hình demo/dev, không dùng nguyên cho production.


## Giao diện compact

Bản này đã giảm density UI để ở Chrome zoom 100% nhìn gần giống cảm giác bản cũ khi bạn để 75%. Các phần đã thu gọn gồm sidebar, topbar, card, bảng, button, input, modal và khoảng cách giữa các khối.


## Fix lỗi frontend: `sh: next: not found`

Nếu frontend báo `sh: next: not found`, nguyên nhân thường là volume `node_modules` cũ bị rỗng/stale. Chạy:

```bat
docker compose down -v
docker compose up --build
```

Từ v25.9.4, frontend container cũng tự kiểm tra `node_modules/.bin/next`; nếu thiếu thì tự chạy `npm install` trước khi chạy dev server.


## Fix lỗi frontend `sh: next: not found` / `npm error Exit handler never called`

Bản v25.9.5 đã bỏ mount `node_modules` runtime cho frontend. Nếu máy bạn đã chạy bản v25.9.4 và còn volume lỗi cũ, chạy sạch bằng:

```bat
docker compose down -v --remove-orphans
docker compose build --no-cache frontend
docker compose up --build
```

Không cần chạy `npm install` trong container nữa. Dependencies được cài trong bước `docker build`.

## Fix frontend `next: not found`

If frontend logs show:

```txt
sh: next: not found
```

run a clean frontend rebuild:

```bat
docker compose down -v --remove-orphans
docker compose rm -sf frontend
docker compose build --no-cache frontend
docker compose up --build
```

In v25.9.6, the frontend Dockerfile installs dependencies during image build from the public npm registry and verifies `node_modules/.bin/next` exists before the image can start.
