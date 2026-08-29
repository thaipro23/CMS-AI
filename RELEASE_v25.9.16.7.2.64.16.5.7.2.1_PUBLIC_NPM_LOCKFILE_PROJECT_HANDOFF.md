# v25.9.16.7.2.64.16.5.7.2.1 — Public npm Lockfile & Project Handoff Hotfix

## Root cause

The `.64.16.5.7.2` lockfiles contained explicit tarball URLs under an OpenAI-internal Artifactory hostname. UAT could not access that hostname, so npm repeatedly timed out on dependencies such as `wrap-ansi`, `wrappy` and `yocto-queue`. `Exit handler never called!` was a secondary npm failure after the network timeouts.

## Changes

- Rewrites **365** frontend and **4** E2E `resolved` URLs to `https://registry.npmjs.org/`.
- Adds `frontend/.npmrc` and `e2e/.npmrc` with public registry and `replace-registry-host=always`.
- Forces the public registry during Docker npm pinning and `npm ci`.
- Adds `NPM_CONFIG_REGISTRY=https://registry.npmjs.org/` to GitHub Actions.
- Adds an early CI prerequisite that rejects private/internal lockfile URLs before npm install.
- Adds `scripts/npm-public-registry-lockfile-report.sh` and integrates it into review/UAT gates.
- Adds a complete project handoff for the next conversation.

## Boundary

- Preserves all `.64.16.5.7.2` Full Frontend Design Contract Closure changes.
- Does not change frontend business behavior, backend API, RBAC, Celery or Open edX semantics.
- No new migration; Alembic head remains `0053`.
- CI remains in the repository because the concrete lockfile issue is fixed. CI expansion is not a current project priority and should be left to its assigned owner unless explicitly requested.
