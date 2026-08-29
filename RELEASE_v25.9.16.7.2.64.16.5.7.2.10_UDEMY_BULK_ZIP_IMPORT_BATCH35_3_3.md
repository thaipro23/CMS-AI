# v25.9.16.7.2.64.16.5.7.2.10 — Batch 35.3.3 Udemy Bulk ZIP Import

## Scope

Adds a production-oriented bulk progress import workflow for Udemy without changing the existing domain split: Subject Management stays term-level, while progress import remains term + Block scoped.

## User flow

- Entry point in `Quản lý sinh viên Udemy` and `Quản lý môn học`.
- Select the Block when importing across subjects.
- Upload many `.csv/.xlsx` reports at once, or one `.zip` containing many reports.
- One persistent `AcademicBulkOperationJob` owns many `UdemyProgressImportBatch` children.
- Each child keeps independent duplicate/error/retry status.

## ZIP safety

- No filesystem extraction; members are read in memory and persisted only after validation.
- Rejects absolute paths and `..` traversal.
- Rejects encrypted members.
- Enforces max archive entries, max 50 Udemy reports, per-file size, total uncompressed size, and suspicious compression ratio.
- Does not recursively expand nested archives.
- Unsupported archive members are reported separately and do not block valid siblings.

## Import identity guard

For raw Udemy path reports, the importer reads `Tiêu đề lộ trình` and can detect:

- branch (`POLY` / `PTCD`),
- subject code,
- term token (`SP2026`, `SU2026`, `FA2026`).

A definite mismatch is rejected before queueing to avoid writing progress into the wrong subject/term/branch. Filename subject and report subject must agree when both are available.

## Compatibility

- Existing single-subject import remains supported.
- Existing multi-file API remains supported.
- `.xlsx`, UTF-8 `.csv`, legacy 25-column files, current 26-column files with `ID bên ngoài`, and the 7-column aggregate format remain supported.
- Existing SHA-256 idempotency and force-reimport behavior remain unchanged.
- No database migration; Alembic head remains `0057`.
