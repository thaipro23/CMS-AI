# v19 Topic Hotfix

## Problem
The v19 mock/demo topic extractor used single keyword frequency. That could create odd topic names such as:

- Dùng
- Tải
- Liệu
- Giới
- Dbcontext
- Rest Api

These are not meaningful learning topics. They are fragments extracted from Vietnamese text or technical terms with wrong capitalization.

## Fix
The topic extractor now uses:

1. Controlled technical topic rules first.
2. Multi-word fallback phrases only.
3. A broader Vietnamese/English stopword list.
4. Canonical topic names such as `REST API`, `HTTP Methods`, `DbContext`, `Entity Framework Core`, `Open edX Course Content`, `AI Question Bank`, and `Cost Control`.
5. Cleanup for old bad auto topics when `/courses/{course_id}/topics?refresh=true` is called.

## How to apply
After updating code, refresh topics from the UI using:

- Sync page → `Reload + Refresh Topics`

For a clean demo database:

```powershell
docker compose down -v
docker compose up --build
```

Then run `Sync Course Content` again.
