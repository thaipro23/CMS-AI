# v25.9.13.44 - Frontend Docker Build Fix

Fixes a frontend Docker build failure where `npm run typecheck` failed with:

```text
sh: tsc: not found
```

Root causes addressed:

1. The Docker deps stage could reuse stale cached `node_modules` from an older build without TypeScript.
2. The lockfile generated in the previous packaging environment contained internal registry URLs, which could break a clean `--no-cache` build on a normal developer machine.

Changes:

- `frontend/Dockerfile` now installs build dependencies explicitly with `npm ci --include=dev`.
- The build calls local binaries directly: `./node_modules/.bin/tsc` and `./node_modules/.bin/next`.
- The deps stage verifies that both `tsc` and `next` exist before continuing.
- `frontend/package-lock.json` resolved URLs now use `https://registry.npmjs.org/`.

Recommended rebuild command:

```powershell
docker compose -f docker-compose.prod.yml --env-file .env.production build --no-cache frontend
docker compose -f docker-compose.prod.yml --env-file .env.production up -d
```
