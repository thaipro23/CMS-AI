# v25.9.16.7.2.50 — Bank Quiz Final Test Production QA

## Summary

This release finalizes the compact Bank hierarchy UX for high-cardinality production usage. Operators can search, filter by operational status, see row counts, and keep the STT/action columns visible while scrolling wide tables.

## Runtime changes

- Adds `BankTableToolbar` to Bank hierarchy screens.
- Adds reusable bank status bucket/filter helpers.
- Adds sticky STT/action column CSS for production Bank tables.
- Preserves the inline actions visibility fix from `.41`.
- No backend schema change and no Alembic migration.

## Verification

- Static regression locks toolbar/filter usage on all four hierarchy pages.
- Static regression locks sticky action/STT CSS and no-card table UX.
