# v25.9.13.52 - Analytics PostgreSQL GROUP BY Fix

## Fixed

- Fixed `/api/analytics/overview` returning HTTP 500 on PostgreSQL when building `top_scopes`.
- The previous SQLAlchemy query generated separate bind parameters for `SELECT coalesce(ai_questions.topic, 'unknown')` and `GROUP BY coalesce(ai_questions.topic, 'unknown')`. PostgreSQL treated those as different expressions and raised `GroupingError`.
- Reused a single labeled expression and a SQL literal constant for the topic aggregation.

## Validation

- Ran Python compile validation for `backend/app`.

## Rebuild

Rebuild backend and worker only:

```bash
docker compose -f docker-compose.prod.yml --env-file .env.production build backend worker
docker compose -f docker-compose.prod.yml --env-file .env.production up -d backend worker
```

Then test:

```bash
curl -i "http://localhost:8000/api/analytics/overview?course_id=course-v1:FPT+cc+cc"
```
