# Production deployment notes for v25.9.13.42

## Required database migration

Run Alembic before starting the new backend image:

```bash
cd backend
alembic upgrade head
```

This creates composite indexes, idempotency keys and explicit Open edX lifecycle columns.

## Idempotency

For operations that can be retried by browser/network/proxy, send a stable header:

```http
Idempotency-Key: <uuid-or-request-id>
```

Supported endpoints:

- `POST /api/generate`
- `POST /api/courses/{course_id}/openedx`
- `POST /api/questions/{question_id}/openedx`
- `POST /api/batches/{batch_id}/rollback`

## Production quality gates

Run before deploy:

```bash
cd backend
python -m compileall app
pytest -q
alembic heads

cd ../frontend
npm ci
npm run typecheck
npm run build
```

## Open edX live integration test

Only run after CMS connector plugin and HMAC are configured:

```bash
cd backend
OPENEDX_INTEGRATION_TEST=1 \
OPENEDX_INTEGRATION_COURSE_ID='course-v1:ORG+COURSE+RUN' \
pytest app/tests/test_openedx_plugin_integration.py -q
```
