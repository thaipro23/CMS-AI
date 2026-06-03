# v25.9.13.30 - Users Analytics Review Log Fix

## Fixed

- Fixed `/api/users/analytics` 500 error caused by reading `QuestionReviewLog.action`.
- `QuestionReviewLog` stores `old_status` and `new_status`, so the users analytics endpoint now derives activity from status transitions:
  - `old_status == edited` or `new_status == edited` => edit count
  - `new_status == approved` => approved count
  - `new_status == rejected` => rejected count
  - `new_status == published` => published count

## Impact

- `/users` no longer crashes when a course has review logs.
- No database migration required.
- No CMS/Open edX plugin update required.
