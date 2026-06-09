# v25.9.15.3.4.2 - Migration Idempotency Hotfix

## Why

The legacy `0001_initial_schema` migration creates tables from the current SQLAlchemy metadata. On a fresh/cleared test database it can therefore create columns that later historical migrations try to add again.

Observed failure:

```text
psycopg.errors.DuplicateColumn: column "concept_id" of relation "ai_questions" already exists
[SQL: ALTER TABLE ai_questions ADD COLUMN concept_id VARCHAR]
```

## Fix

- `0006_v25_9_14_0_concepts.py` is now idempotent:
  - skips `ai_concepts` creation if table already exists
  - skips `concept_id`, `concept_title`, `concept_key` if columns already exist
  - skips indexes if already present
- `0007_v25_9_14_1_question_family_id.py` is now idempotent:
  - skips `question_family_id`, `variant_no`, `source_evidence` if columns already exist
  - skips index if already present

## How to apply

Rebuild backend/worker and run migrations again.

```bash
docker compose -f docker-compose.prod.yml --env-file .env.production build --no-cache backend worker

docker compose -f docker-compose.prod.yml --env-file .env.production run --rm backend alembic upgrade head

docker compose -f docker-compose.prod.yml --env-file .env.production up -d --force-recreate backend worker frontend
```

No data migration is required.
