# Build lại từ đầu v25.9.13.43

Tài liệu này dùng cho trường hợp AI Server chạy riêng, Open edX/Tutor chạy riêng. Bản v25.9.13.43 đã sửa thêm lỗi build/runtime so với v25.9.13.42:

- Sửa model `QuestionEmbedding` khai báo nhầm composite index gây lỗi SQLAlchemy metadata khi backend start.
- Sửa frontend Dockerfile production: dùng Node 20, `npm ci`, `npm run typecheck`, `npm run build`, chạy production server thay vì dev server.
- Sửa `docker-compose.prod.yml`: có PostgreSQL, Redis, healthcheck, volume runtime, port mapping và build arg `NEXT_PUBLIC_API_BASE_URL`.
- Siết production validation: chặn `CHANGE_ME` trong DB/OpenAI/Open edX OAuth/JWT/HMAC/metrics.
- Giữ `AUTO_CREATE_TABLES=false`; production phải chạy Alembic migration.
- Chạy backend test suite: `25 passed, 2 skipped`.
- Chạy frontend typecheck: pass.

## 0. Các domain cần xác định trước

Ví dụ theo setup hiện tại của bạn:

```text
AI Frontend:  https://ai.cms-test.poly.edu.vn
AI Backend:   https://api-ai.cms-test.poly.edu.vn
Open edX CMS: https://scms-test.poly.edu.vn
Open edX LMS: https://cms-test.poly.edu.vn
MFE/App:      https://app.cms-test.poly.edu.vn hoặc https://apps.cms-test.poly.edu.vn
```

Nếu domain thật khác, sửa theo domain thật. Đừng copy nhầm `app` thành `apps` hoặc ngược lại.

## 1. Giải nén source mới trên server AI

```bash
mkdir -p /opt/ai-openedx
cd /opt/ai-openedx
unzip ai-server-openedx-v25.9.13.43-full-rebuild-hardening.zip
cd ai-server-openedx-v25.9.13.43-full-rebuild-hardening
```

Nếu bạn giải nén ra thư mục khác, chỉ cần `cd` đúng thư mục có file `docker-compose.prod.yml`.

## 2. Tạo `.env.production`

```bash
cp .env.production.example .env.production
```

Tạo secret trên Linux:

```bash
./scripts/generate-secrets.sh
```

Tạo secret trên Windows PowerShell:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/generate-secrets.ps1
```

Sửa `.env.production`:

```bash
nano .env.production
```

Các dòng bắt buộc phải thay:

```env
POSTGRES_PASSWORD=<mật khẩu postgres mạnh>
DATABASE_URL=postgresql+psycopg://ai_user:<mật khẩu postgres mạnh>@postgres:5432/ai_openedx
NEXT_PUBLIC_API_BASE_URL=https://api-ai.cms-test.poly.edu.vn
CORS_ALLOWED_ORIGINS=https://ai.cms-test.poly.edu.vn,https://scms-test.poly.edu.vn,https://cms-test.poly.edu.vn
METRICS_TOKEN=<secret random>
OPENAI_API_KEY=<OpenAI API key thật>
OPENEDX_CLIENT_ID=<OAuth client id thật bên Open edX>
OPENEDX_CLIENT_SECRET=<OAuth client secret thật bên Open edX>
OPENEDX_CONNECTOR_HMAC_SECRET=<secret random dùng chung với CMS plugin>
JWT_SECRET=<secret random>
AI_CONNECTOR_HMAC_SECRET=<copy giống OPENEDX_CONNECTOR_HMAC_SECRET>
```

Không để lại bất kỳ `CHANGE_ME` nào:

```bash
grep -n "CHANGE_ME" .env.production
```

Lệnh trên không được in ra dòng nào.

## 3. Cấu hình Open edX CMS container nhận `AI_CONNECTOR_*`

Bước này làm trên server Open edX/Tutor, không phải trong container AI Server.

Cách tự động bằng script trong source AI Server:

```bash
./scripts/tutor-ai-connector-override.sh '<OPENEDX_CONNECTOR_HMAC_SECRET>' 'admin' 'scms-test.poly.edu.vn,cms-test.poly.edu.vn,app.cms-test.poly.edu.vn'
```

Hoặc làm tay:

```bash
cd "$(tutor config printroot)"
mkdir -p env/local
nano env/local/docker-compose.override.yml
```

Nội dung:

```yaml
services:
  cms:
    environment:
      AI_CONNECTOR_PUBLISH_USERNAME: "admin"
      AI_CONNECTOR_ALLOW_ANONYMOUS_PUBLISH: "false"
      AI_CONNECTOR_HMAC_SECRET: "<giống OPENEDX_CONNECTOR_HMAC_SECRET>"
      AI_CONNECTOR_HMAC_SKEW_SECONDS: "300"
      AI_CONNECTOR_ALLOWED_DOWNLOAD_HOSTS: "scms-test.poly.edu.vn,cms-test.poly.edu.vn,app.cms-test.poly.edu.vn"
      AI_CONNECTOR_COMPONENT_PUBLISH_ENABLED: "false"
      AI_CONNECTOR_TAGGING_ENABLED: "true"
      AI_CONNECTOR_TAG_TAXONOMY_EXPORT_ID: "ai-learning-check"
      AI_CONNECTOR_TAG_TAXONOMY_NAME: "AI Learning Check"

  cms-worker:
    environment:
      AI_CONNECTOR_PUBLISH_USERNAME: "admin"
      AI_CONNECTOR_ALLOW_ANONYMOUS_PUBLISH: "false"
      AI_CONNECTOR_HMAC_SECRET: "<giống OPENEDX_CONNECTOR_HMAC_SECRET>"
      AI_CONNECTOR_HMAC_SKEW_SECONDS: "300"
      AI_CONNECTOR_ALLOWED_DOWNLOAD_HOSTS: "scms-test.poly.edu.vn,cms-test.poly.edu.vn,app.cms-test.poly.edu.vn"
      AI_CONNECTOR_COMPONENT_PUBLISH_ENABLED: "false"
      AI_CONNECTOR_TAGGING_ENABLED: "true"
      AI_CONNECTOR_TAG_TAXONOMY_EXPORT_ID: "ai-learning-check"
      AI_CONNECTOR_TAG_TAXONOMY_NAME: "AI Learning Check"
```

Restart Open edX CMS:

```bash
tutor local restart cms cms-worker
```

Kiểm tra:

```bash
docker exec -it tutor_local-cms-1 bash -lc 'env | grep AI_CONNECTOR'
docker exec -it tutor_local-cms-worker-1 bash -lc 'env | grep AI_CONNECTOR'
```

## 4. Kiểm tra DNS/sethost từ container

Vì bạn đang dùng sethost, cần chắc server/container cũng resolve được domain:

```bash
getent hosts scms-test.poly.edu.vn
getent hosts cms-test.poly.edu.vn
getent hosts app.cms-test.poly.edu.vn
```

Trong CMS container:

```bash
docker exec -it tutor_local-cms-1 bash -lc "getent hosts scms-test.poly.edu.vn && getent hosts cms-test.poly.edu.vn && getent hosts app.cms-test.poly.edu.vn"
```

Trong AI backend container sau khi chạy:

```bash
docker compose -f docker-compose.prod.yml --env-file .env.production exec backend bash -lc "getent hosts scms-test.poly.edu.vn && getent hosts cms-test.poly.edu.vn && getent hosts app.cms-test.poly.edu.vn"
```

Nếu không resolve được, thêm DNS thật hoặc thêm `/etc/hosts`/`extra_hosts` phù hợp.

## 5. Build sạch AI Server

Trên server AI:

```bash
docker compose -f docker-compose.prod.yml --env-file .env.production down --remove-orphans
```

Nếu muốn xóa sạch DB cũ để build lại từ đầu thật sự:

```bash
docker compose -f docker-compose.prod.yml --env-file .env.production down -v --remove-orphans
```

Cẩn thận: `down -v` xóa volume PostgreSQL/Redis/runtime của AI Server.

Build không cache:

```bash
docker compose -f docker-compose.prod.yml --env-file .env.production build --no-cache
```

Chạy:

```bash
docker compose -f docker-compose.prod.yml --env-file .env.production up -d
```

Xem log:

```bash
docker compose -f docker-compose.prod.yml --env-file .env.production logs -f backend
```

Backend sẽ tự chạy:

```bash
alembic -c alembic.ini upgrade head
```

Nếu muốn chạy migration thủ công:

```bash
docker compose -f docker-compose.prod.yml --env-file .env.production exec backend alembic -c alembic.ini upgrade head
```

## 6. Kiểm tra sau build

Health backend:

```bash
curl -i http://localhost:8000/api/health
```

Metrics có token:

```bash
curl -H "X-Metrics-Token: <METRICS_TOKEN>" http://localhost:8000/metrics | head
```

Frontend:

```bash
curl -i http://localhost:3000
```

Nếu đi qua Nginx/Caddy/domain, kiểm tra:

```bash
curl -i https://api-ai.cms-test.poly.edu.vn/api/health
curl -i https://ai.cms-test.poly.edu.vn
```

## 7. Kiểm tra Open edX connector

Từ AI backend container:

```bash
docker compose -f docker-compose.prod.yml --env-file .env.production exec backend bash
```

Trong shell container:

```bash
python - <<'PY'
from app.core.config import settings
print('CMS:', settings.openedx_cms_base_url)
print('LMS:', settings.openedx_lms_base_url)
print('HMAC configured:', bool(settings.openedx_connector_hmac_secret))
print('Allowed hosts:', settings.openedx_allowed_download_hosts)
PY
```

Sau đó vào UI AI Server, sync một course nhỏ trước, rồi publish thử 1 câu hỏi bằng dry-run trước khi publish toàn bộ.

## 8. Lệnh test trước khi build image nếu chạy local source

Backend:

```bash
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
PYTHONPATH=. APP_ENV=development AUTH_MODE=demo ALLOW_DEMO_ROLE_HEADER=true DATABASE_URL=sqlite+pysqlite:///:memory: pytest -q
```

Frontend nên dùng Node 20:

```bash
cd frontend
npm ci
npm run typecheck
npm run build
```

Nếu build frontend trên Windows/Node 22 bị treo ở `Collecting build traces`, hãy build bằng Docker hoặc Node 20. Dockerfile production đã dùng `node:20-alpine`.

## 9. Các lỗi thường gặp

### Backend không start vì Unsafe production configuration

Mở log:

```bash
docker compose -f docker-compose.prod.yml --env-file .env.production logs backend --tail=200
```

Sửa hết `CHANGE_ME`, kiểm tra `JWT_SECRET`, `METRICS_TOKEN`, `OPENEDX_CONNECTOR_HMAC_SECRET`, `OPENAI_API_KEY`, `OPENEDX_CLIENT_ID`, `OPENEDX_CLIENT_SECRET`.

### AI Server gọi CMS bị 403 HMAC

Kiểm tra secret hai bên giống nhau:

```env
OPENEDX_CONNECTOR_HMAC_SECRET=<bên AI server>
AI_CONNECTOR_HMAC_SECRET=<bên Open edX CMS container>
```

Kiểm tra giờ hai server không lệch quá 300 giây.

### Không tải được asset/transcript

Kiểm tra domain asset có nằm trong:

```env
OPENEDX_ALLOWED_DOWNLOAD_HOSTS=...
AI_CONNECTOR_ALLOWED_DOWNLOAD_HOSTS=...
```

### CORS lỗi trên browser

`CORS_ALLOWED_ORIGINS` phải chứa domain frontend đang mở trên trình duyệt, ví dụ:

```env
CORS_ALLOWED_ORIGINS=https://ai.cms-test.poly.edu.vn
```
