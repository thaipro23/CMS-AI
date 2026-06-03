# v25.9.5 - Frontend Runtime Dependency Fix

## Problem

Frontend container failed with:

```txt
Installing frontend dependencies...
npm error Exit handler never called!
sh: next: not found
```

This happened because the dev compose file mounted `./frontend:/app` and a named volume at `/app/node_modules`. On Windows/Docker Desktop, the mounted volume can hide the `node_modules` installed during image build. The runtime fallback tried to run `npm install`, but npm crashed before installing `next`.

## Fix

The frontend service now runs from the built Docker image and no longer bind-mounts `./frontend` or `/app/node_modules` in the default `docker-compose.yml`. Dependencies are installed during `docker build` via `npm ci`. Runtime only runs:

```txt
npm run dev
```

## Run

Use a clean restart to remove old bad volumes:

```bat
docker compose down -v --remove-orphans
docker compose build --no-cache frontend
docker compose up --build
```

Then open:

```txt
http://localhost:3000
```
