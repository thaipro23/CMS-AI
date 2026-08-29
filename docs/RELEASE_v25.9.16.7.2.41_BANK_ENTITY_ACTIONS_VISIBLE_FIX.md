# v25.9.16.7.2.41 — Bank Entity Actions Visible Fix

## Problem

After Bank hierarchy pages were converted from large cards to compact tables, the old absolute-positioned `EntityActions` menu could be clipped by the table scroll wrapper or render outside the `Thao tác` cell. This made operators think the row actions were missing.

## Fix

- Added `EntityActions` inline variant for compact tables.
- Updated Bank hierarchy pages to render visible `Sửa` / `Xóa` actions in the row.
- Added explicit non-action placeholders:
  - `Đã khóa` for published/locked rows.
  - `Không có quyền` for permission-denied rows.
- Expanded the compact table action column and added CSS to prevent clipping.

## Migration

No migration.
