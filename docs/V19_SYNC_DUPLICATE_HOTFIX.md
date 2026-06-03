# v19 Sync Duplicate Hotfix

Fixes `duplicate key value violates unique constraint "uq_course_block"` when running **Sync Course Content** in mock mode.

## Root cause
The mock Open edX payload provides both `parent_block_id` and `children`. The previous `CourseTreeBuilder` connected both directions without checking duplicate edges, so the flattened course tree included the same block more than once. During `CourseSyncState` insert, PostgreSQL rejected duplicate `(course_id, block_id)` rows.

## Fix
- `CourseTreeBuilder` now keeps an edge set and traversal visited set.
- `flatten_blocks()` de-duplicates by `block_id`.
- Asset pages use page-specific block IDs to avoid collisions in multi-page PDF/PPTX extraction.

## How to apply in dev
Because your DB may already contain partial failed sync data, run:

```powershell
docker compose down -v
docker compose up --build
```

Then open `/sync` and run Sync again.
