# v25.9.4 - Frontend Dependency Hotfix

## Problem

Frontend container could start with:

```txt
sh: next: not found
```

This happens when the bind mount `./frontend:/app` hides the dependencies installed in the image, or an old anonymous `/app/node_modules` volume is empty/stale.

## Fix

- Use named volumes for `frontend_node_modules` and `.next` cache.
- On frontend startup, check `node_modules/.bin/next`.
- If missing, run `npm install` automatically before `npm run dev`.
- Dockerfile now uses `npm ci || npm install`.

## Commands

```bat
docker compose down -v
docker compose up --build
```

For normal later runs:

```bat
docker compose down
docker compose up --build
```
