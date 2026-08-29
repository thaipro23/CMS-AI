# Full CMS Auto-Create Users Hotfix — Batch 22

## Symptom

`Đồng bộ full CMS` failed with HTTP 400:

> Chưa có sinh viên nào được map user CMS/Open edX chính xác theo RollNumber. Hãy chạy Tạo/kiểm tra user CMS trước rồi mới Enrollment Course CMS.

This contradicted the intended full-flow contract because the operator should not need to run a separate CMS-user action first.

## Root cause

The flow already called `resolve_class_openedx_users`, but actual user creation still depended on the optional `ACADEMIC_AUTO_CREATE_CMS_USERS` setting. When the setting was disabled, stale, or not propagated to the worker, the resolve step only checked users and enrollment immediately failed when no matched mappings existed. There was also no forced recovery retry before returning HTTP 400.

## Fix

- Added an explicit `create_missing` override to `resolve_class_openedx_users`.
- `Đồng bộ full CMS` now always calls the CMS user step with `create_missing=True` after Course CMS mapping exists.
- Enrollment is self-healing and always performs create/verify-by-RollNumber before querying mappings.
- Enrollment refreshes the SQLAlchemy session before reading newly committed mappings.
- If no valid RollNumber mapping is found, the flow performs one forced create/verify retry automatically.
- Enrollment connector calls retain `create_missing=True` as a final atomic safety net.
- The old message instructing operators to run a separate action was removed. A remaining failure now reports connector result counts and points to connector/HMAC/UserProfile permissions.

## Identity policy preserved

- Student CMS username is exactly `student_code/RollNumber`, preserving case.
- Existing users are resolved case-insensitively.
- AP username is never used as a student username fallback.
- Students without RollNumber are not created or enrolled.

## Deployment scope

Rebuild/recreate AI Server backend and Celery workers. Batch 22 remains cumulative from Batch 21 and includes the Batch 20 Open edX connector RollNumber changes.

No database migration is required.

## Verification status

Python AST parsing completed successfully for the modified service files. No unit tests, typecheck, Docker build, or UAT browser/connector test was run.
