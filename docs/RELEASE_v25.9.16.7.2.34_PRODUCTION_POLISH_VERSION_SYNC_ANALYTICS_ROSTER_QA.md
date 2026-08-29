# v25.9.16.7.2.34 — Production Polish Version Sync + Analytics Roster QA

## Summary

This release keeps the `.33` runtime behavior and adds production polish for version consistency and learning analytics roster QA visibility.

## Changes

- Synchronized version fallbacks to `25.9.16.7.2.34` in backend config, frontend package metadata, production compose, env examples, and AppShell footer fallback.
- Updated `RUN_CURRENT.md` to the `.34` package name/root path.
- Cleaned changelog ordering so `.34` and `.33` are at the top and the responsive sweep heading is correctly marked `.30`.
- Added explicit analytics roster QA fields to class behavior overview and summary contracts:
  - `roster_count`
  - `snapshot_count`
  - `missing_snapshot_count`
  - `data_status`
- Added snapshot coverage chips on `/analytics/learning` result view.
- Updated static regression tests for version sync and analytics roster QA.

## Migration

No migration.

Latest Alembic head remains:

```text
0052_v25_9_16_7_2_27_learning_behavior_logic_calibration.py
```

## Production QA

1. Verify `/api/health` and footer version show `25.9.16.7.2.34` when env is set.
2. Verify `/analytics/learning` result view shows AP roster total, snapshot count, and missing snapshot count.
3. Verify missing behavior snapshots still render as `Chưa đủ dữ liệu`, not as an empty class.
4. Verify `/student-management/classes/{class_id}` action buttons remain equal-width and wrapping on desktop/laptop.
