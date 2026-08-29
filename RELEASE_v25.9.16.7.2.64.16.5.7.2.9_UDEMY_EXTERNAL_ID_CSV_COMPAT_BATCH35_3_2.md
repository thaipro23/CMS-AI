# v25.9.16.7.2.64.16.5.7.2.9 — Batch 35.3.2

## Udemy External ID / CSV compatibility hotfix

- Udemy progress import resolves required fields by header, not fixed column positions.
- Supports current Vietnamese Udemy export headers including the new optional `ID bên ngoài` column.
- Supports raw `.csv` in addition to `.xlsx`.
- Legacy 25-column `.xlsx` fallback remains for historical files.
- `ID bên ngoài` is ignored by the progress calculation and may move without shifting Email/progress mapping.
- No schema migration and no data migration.
