# AI Learning Server for Open edX CMS — v25.9.13.0

Starter implementation for an Open edX AI Learning Check system.

This release includes the full roadmap implementation from **v9 to v15**:

- Modular backend foundation
- Alembic migration setup
- Real/mock Open edX connector adapter
- Production-ready RBAC path
- GPT-5 mini / local OpenAI-compatible model gateway
- Question Bank + Review workflow
- Open edX OLX export and publish endpoint
- Cost governance: estimate, quota, hard stop, usage log
- Multi-page Next.js UI
- Tests, CI, monitoring hooks and production compose

## Run local demo

```bash
cp .env.example .env
docker compose up --build
```

Open:

- Frontend: http://localhost:3000
- API docs: http://localhost:8000/docs
- MinIO console: http://localhost:9001 (dev/demo only)

## Important modes

### Demo mode

```env
USE_MOCK_OPENEDX=true
MOCK_LLM=true
AUTH_MODE=demo
AUTO_CREATE_TABLES=true
```

### Real API-first mode

```env
USE_MOCK_OPENEDX=false
MOCK_LLM=false
AUTH_MODE=jwt
AUTO_CREATE_TABLES=false
OPENAI_API_KEY=...
OPENEDX_BASE_URL=https://your-openedx.example.edu
OPENEDX_CLIENT_ID=...
OPENEDX_CLIENT_SECRET=...
```

Then run:

```bash
cd backend
alembic -c alembic.ini upgrade head
```

## Pages

- `/dashboard` — statistics, governance, cost summary
- `/sync` — sync course content from Open edX
- `/generate` — manual/chunk generation mode
- `/review` — Teacher Review Queue
- `/question-bank` — all questions + filter/search/sort/edit
- `/export` — OLX preview/download and publish-to-Open-edX action
- `/jobs` — job monitor
- `/settings` — demo role/course settings

## Docs

- `docs/V9_TO_V15_RELEASE_NOTES.md`
- `docs/PRODUCTION_DEPLOYMENT.md`
- `docs/OPENEDX_REAL_INTEGRATION.md`
- `docs/AUTH_RBAC_PRODUCTION.md`
- `docs/API.md`
- `docs/FRONTEND_STRUCTURE.md`
- `docs/OPENEDX_EXPORT.md`

## Commit suggestion

```bash
git add .
git commit -m "feat: upgrade AI Open edX server from v9 to v15 production foundation"
```


## v16-v19 status

This version adds production-oriented algorithms from the 10/10 plan:

- Course tree traversal from Open edX blocks
- HTML/transcript/PDF/PPTX extraction layer
- Hash-based changed content detection
- Chunking with source references
- Topic extraction and topic coverage allocation
- Batch generation with topic allocation
- Source grounding and duplicate detection hooks
- Friendlier multi-page UI for Sync and Generate

See `docs/V16_TO_V19_RELEASE_NOTES.md`.


## v24 - Chapter/Module Libraries

Course tạo nhiều Library theo Chapter/Module. Khi AI sinh câu hỏi ở Unit/PDF/Video/HTML, backend tìm Chapter cha, import câu hỏi vào Library của Chapter đó và giữ `source_node_id` để Problem Bank trong Unit random/filter đúng nguồn. Xem `docs/V24_CHAPTER_LIBRARIES.md`.

## v24.2 - Responses API Gateway

Bản này mặc định dùng OpenAI Responses API cho GPT thật.

Cấu hình nhanh trong `.env` hoặc `/settings`:

```env
MODEL_PROVIDER=openai
OPENAI_MODEL=gpt-5-mini
OPENAI_API_MODE=responses
MOCK_LLM=false
OPENAI_API_KEY=sk-...
```

Trong `/settings`, admin có thể bấm **Test GPT**. Nếu OK, kết quả sẽ hiển thị `openai_responses/gpt-5-mini qua responses`.

Chat Completions cũ vẫn giữ dưới mode `chat_legacy` để fallback/local compatible.

## v24.3 Accurate Cost Metering

- Estimate trước khi chạy dùng `/v1/responses/input_tokens` cho payload Responses thật.
- Safety factor chỉ áp dụng cho Estimate/Hard Stop.
- Actual cost dùng usage thật và không nhân safety factor.
- Có API `GET /api/cost/pricing/realtime?model=...&refresh=true` để fetch/cache giá OpenAI realtime-ish.
