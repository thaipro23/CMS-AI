# Batch 24 — Large Roster & Legacy CMS Identity Recovery

## Scope

- Removes the historical 500-student truncation from class CMS sync.
- Full CMS sync calculates the actual roster size and processes the entire class, up to `ACADEMIC_CLASS_SYNC_MAX_STUDENTS` (default 5000).
- Connector requests remain chunked by `OPENEDX_CONNECTOR_MAX_BATCH_SIZE` (default 100), so classes around 1000 students are processed in bounded batches.
- Full CMS no longer resolves the whole roster twice before enrollment.
- When a legacy Open edX account already owns the AP email under an AP-style username, the connector safely renames that existing user to the RollNumber, preserving user ID, profile, enrollment, grades, progress, and history.
- Email collision with multiple users or RollNumber collision is rejected rather than guessed.

## Deployment

AI Server rebuild/recreate: backend and worker.
Open edX connector update: deploy `openedx-connector-plugin` and recreate LMS/CMS runtimes that load the editable plugin.
No Alembic migration.
