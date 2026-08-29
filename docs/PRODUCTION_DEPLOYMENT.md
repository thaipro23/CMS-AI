# Production Deployment Guide

## 1. Environment
Copy `.env.example` to `.env` and update:

```env
APP_ENV=production
AUTO_CREATE_TABLES=false
AUTH_MODE=jwt
USE_MOCK_OPENEDX=false
MOCK_LLM=false
OPENAI_API_KEY=...
OPENEDX_BASE_URL=https://your-openedx.example.edu
OPENEDX_CLIENT_ID=...
OPENEDX_CLIENT_SECRET=...
STORAGE_PROVIDER=minio
MINIO_ENDPOINT=https://s3.fpl.edu.vn
MINIO_BUCKET=ai-server
```

Với hạ tầng FPL hiện tại, dùng `STORAGE_PROVIDER=minio` và làm theo
[`EXTERNAL_MINIO.md`](EXTERNAL_MINIO.md). MinIO nằm trên VM riêng ngoài cụm,
không triển khai thành pod Kubernetes.

## 2. Database migrations

```bash
cd backend
alembic -c alembic.ini upgrade head
```

For dev only, `AUTO_CREATE_TABLES=true` can create tables automatically.

## 3. Run production compose

`docker-compose.prod.yml` là file production độc lập. Không merge với
`docker-compose.yml`, vì file development có MinIO local dùng credential demo.

```bash
docker compose --env-file .env.production -f docker-compose.prod.yml up --build -d
```

## 4. Monitoring

```bash
docker compose --env-file .env.production -f docker-compose.prod.yml --profile monitoring up -d prometheus grafana
```

Prometheus scrapes backend `/metrics`.

## 5. Storage note
MinIO trong `docker-compose.yml` chỉ dùng cho local development. Production FPL
kết nối `https://s3.fpl.edu.vn`, bucket private `ai-server`, bằng service account
riêng và luôn xác minh TLS.
