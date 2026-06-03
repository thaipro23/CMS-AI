# Auth/RBAC Production Plan

## Current demo behavior
The local UI sends:

```http
X-User-Role: teacher
X-User-Id: demo-teacher
```

This is for development only.

## Production path
Use `AUTH_MODE=jwt` or `AUTH_MODE=openedx_sso`.

JWT claims expected:

```json
{
  "sub": "123",
  "email": "teacher@fpt.edu.vn",
  "role": "teacher",
  "courses": ["course-v1:FPT+PRN232+2026"]
}
```

## Permission enforcement
Backend enforces permissions using `require_permission`. Frontend disables buttons only for UX; backend remains source of truth.
