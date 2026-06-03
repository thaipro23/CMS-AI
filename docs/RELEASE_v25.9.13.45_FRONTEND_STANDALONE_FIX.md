# v25.9.13.45 - Frontend standalone Docker fix

## Fix

The v25.9.13.44 Dockerfile expects Next.js standalone output at `.next/standalone`, but `frontend/next.config.js` did not enable `output: 'standalone'`. As a result, `next build` succeeded but the Docker runner stage failed while copying `/app/.next/standalone`.

This release enables:

```js
output: 'standalone'
```

in `frontend/next.config.js`, so the production Dockerfile can copy `server.js` and the minimal runtime dependency set.

## Build command

```bash
docker compose -f docker-compose.prod.yml --env-file .env.production build --no-cache frontend
docker compose -f docker-compose.prod.yml --env-file .env.production up -d --build
```

## Notes

- Keep using the same `.env.production` from v25.9.13.44.
- If Docker still reuses old layers, run the frontend build with `--no-cache`.
