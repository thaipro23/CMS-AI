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
STORAGE_PROVIDER=s3
```

## 2. Database migrations

```bash
cd backend
alembic -c alembic.ini upgrade head
```

For dev only, `AUTO_CREATE_TABLES=true` can create tables automatically.

## 3. Run production compose

```bash
docker compose -f docker-compose.yml -f docker-compose.prod.yml up --build -d
```

## 4. Monitoring

```bash
docker compose --profile monitoring up -d prometheus grafana
```

Prometheus scrapes backend `/metrics`.

## 5. Storage note
MinIO is included for local development. For production organizations, switch to approved object storage such as AWS S3, Azure Blob, Google Cloud Storage or internal object storage.
