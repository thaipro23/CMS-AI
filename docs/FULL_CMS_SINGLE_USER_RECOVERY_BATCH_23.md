# Batch 23 — Full CMS single-user recovery

## Symptom

`Đồng bộ full CMS` reached the Open edX connector and matched the teacher, but all students were persisted as `missing`, while a direct single-student connector call could create a valid `auth_user` and `UserProfile`.

## Change

- Keep the existing bulk resolve/create call for efficiency.
- For each student whose bulk result is absent or `missing`, retry that exact RollNumber once as a single-user connector request with `create_missing=true`.
- Persist the exact single-user connector result into `openedx_user_mappings`.
- Add counters `single_retry_attempted` and `single_retry_recovered`.
- When no valid mapping remains, include up to five RollNumber-specific mapping notes in the HTTP 400 detail instead of showing only a generic HMAC/permission message.

## Identity policy preserved

- Student CMS username is exactly `student_code` / RollNumber.
- New usernames preserve case, e.g. `PH12345`.
- Lookup remains case-insensitive for legacy users.
- AP username is not a fallback.
- Missing RollNumber blocks user creation and enrollment.
