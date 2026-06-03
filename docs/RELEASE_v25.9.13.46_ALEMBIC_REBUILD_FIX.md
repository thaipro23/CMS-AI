# v25.9.13.46 - Alembic clean rebuild fix

Fixes a clean rebuild failure where `0001_initial_schema` created current SQLAlchemy metadata, including `ai_course_libraries`, and `0002_chapter_libraries` then tried to create the same table again.

## Changes

- Made `backend/alembic/versions/0002_chapter_libraries.py` idempotent.
- `ai_course_libraries` is now created with `CREATE TABLE IF NOT EXISTS`.
- `ai_questions` columns from v24 are now added with `ALTER TABLE ... ADD COLUMN IF NOT EXISTS`.
- Legacy unique constraint creation is guarded so it does not conflict with the newer chapter+difficulty constraint.
- Downgrade is conservative and does not drop publish/library history.

## Why this matters

A fresh Docker volume failed with:

```text
psycopg.errors.DuplicateTable: relation "ai_course_libraries" already exists
```

This happened because `0001_initial_schema` used current SQLAlchemy metadata instead of a frozen historical schema. This release keeps the legacy migration chain but makes `0002` safe for both clean builds and older upgraded databases.

## After upgrading

For a local rebuild from scratch:

```bash
docker compose -f docker-compose.prod.yml --env-file .env.production down -v --remove-orphans
docker compose -f docker-compose.prod.yml --env-file .env.production up -d --build
```
