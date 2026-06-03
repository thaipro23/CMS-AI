# v25.9.13.51 - Next.js SWC Debian Slim Fix

This release fixes frontend Docker build failures on Windows Docker Desktop/Alpine-based images:

```text
Failed to load SWC binary for linux/x64
Error loading shared library ld-linux-x86-64.so.2
```

Root cause: the lockfile installed the glibc SWC package `@next/swc-linux-x64-gnu`, while `node:20-alpine` does not include the glibc dynamic loader. The frontend Dockerfile now uses `node:20-bookworm-slim` for deps, builder and runtime stages.

## Build

```bat
docker compose -f docker-compose.prod.yml --env-file .env.production down -v --remove-orphans
docker compose -f docker-compose.prod.yml --env-file .env.production up -d --build
```

If backend becomes unhealthy after the frontend build passes, check runtime logs:

```bat
docker compose -f docker-compose.prod.yml --env-file .env.production logs backend --tail=250
```
