# v25.9.13.47 - Alembic publish table clean rebuild fix

This release fixes clean PostgreSQL rebuilds and mixed legacy Alembic/create_all databases where `ai_publish_batches` and `ai_publish_batch_items` may not exist before migration `0005_v25_9_13_42_scale_maintainability`.

Changes:

- `0001_initial_schema` now imports all current SQLAlchemy model modules before `Base.metadata.create_all()`.
- `0005_v25_9_13_42_scale_maintainability` creates publish batch tables with `CREATE TABLE IF NOT EXISTS` before altering/indexing them.

Rebuild local AI Server from scratch:

```bat
docker compose -f docker-compose.prod.yml --env-file .env.production down -v --remove-orphans
docker compose -f docker-compose.prod.yml --env-file .env.production up -d --build
```
