# v25.9.6 - Frontend `next: not found` Final Fix

## Problem
Frontend container starts but fails with:

```txt
sh: next: not found
```

This means `node_modules/.bin/next` is missing inside the runtime container.

## Root cause
Older packages used a runtime install or package-lock based install. On some Windows/Docker Desktop environments, this can fail or produce an image where runtime does not contain the expected `next` binary.

## Fix
- Frontend Dockerfile now installs dependencies during image build from the public npm registry.
- It copies only `package.json` before install, so stale or environment-specific `package-lock.json` URLs cannot break dependency install.
- Build fails immediately if `node_modules/.bin/next` is missing.
- Compose runs Next directly from `./node_modules/.bin/next`, not via an ambiguous shell lookup.
- Added `.dockerignore` files to avoid copying host `node_modules` or `.next` into the image.

## Required clean rebuild
Run:

```bat
docker compose down -v --remove-orphans
docker compose rm -sf frontend
docker image rm ai-server-openedx-v2596-frontend 2>nul
for /f "tokens=*" %i in ('docker images -q *frontend*') do docker rmi -f %i
docker compose build --no-cache frontend
docker compose up --build
```

If the image remove commands fail, ignore them and continue with `docker compose build --no-cache frontend`.
