# v25.9.15.6.31.13 — Bank Business RBAC Roles

Bản này triển khai đúng phần phân quyền trong kế hoạch Bank-first:

```text
SYSTEM_ADMIN
  > DEPARTMENT_HEAD
      > SUBJECT_OWNER
          > QUESTION_REVIEWER
```

Open edX chỉ giữ quyền kỹ thuật tối thiểu. AI Server giữ quyền nghiệp vụ theo scope.

## 1. Bảng mới

```text
ai_rbac_roles
ai_rbac_permissions
ai_rbac_role_permissions
ai_user_role_assignments
```

Scope hỗ trợ:

```text
SYSTEM
DEPARTMENT
SUBJECT
SUBJECT_VERSION
CHAPTER
COURSE
```

## 2. Deploy

```bash
cd /opt/ai-server

docker compose -f docker-compose.prod.yml --env-file .env.production build backend frontend worker

docker compose -f docker-compose.prod.yml --env-file .env.production run --rm backend alembic upgrade head

docker compose -f docker-compose.prod.yml --env-file .env.production up -d --force-recreate backend frontend worker
```

Cập nhật version:

```env
APP_VERSION=25.9.15.6.31.13-bank-business-rbac
# Optional guarded one-time bootstrap endpoint. Leave empty/disabled if you bootstrap through Open edX superuser/AI_ADMIN.
RBAC_BOOTSTRAP_TOKEN=
```

## 3. Bootstrap admin đầu tiên

Khuyến nghị production: đăng nhập bằng Open edX superuser hoặc user thuộc group `AI_ADMIN`, rồi dùng màn `/users` để gán `SYSTEM_ADMIN`. Chỉ dùng bootstrap khi hệ thống chưa có `SYSTEM_ADMIN` nào trong bảng assignment. Endpoint API bootstrap bị khóa bằng `RBAC_BOOTSTRAP_TOKEN` trong production.

```bash
cd /opt/ai-server

docker compose -f docker-compose.prod.yml --env-file .env.production exec backend sh -lc '
python - <<"PY"
from app.db.session import SessionLocal
from app.services.business_rbac import BusinessRBACService

db = SessionLocal()
try:
    item, created = BusinessRBACService(db).bootstrap_system_admin(
        user_id="admin",
        email="admin@example.com",
        reason="Initial AI Server SYSTEM_ADMIN",
    )
    print("CREATED:", created)
    if item:
        print(item.id, item.user_id, item.role_code, item.scope_type, item.scope_id)
finally:
    db.close()
PY
'
```

Hoặc gọi API một lần:

```bash
curl -X POST http://api-ai.cms-test.poly.edu.vn/api/rbac/bootstrap/system-admin \
  -H 'Content-Type: application/json' \
  -H 'X-RBAC-Bootstrap-Token: <RBAC_BOOTSTRAP_TOKEN nếu production bật bootstrap>' \
  -d '{"user_id":"admin","email":"admin@example.com","role_code":"SYSTEM_ADMIN","scope_type":"SYSTEM","scope_id":"*","grant_reason":"Initial bootstrap"}'
```

Sau khi đã có `SYSTEM_ADMIN`, endpoint bootstrap sẽ từ chối tạo thêm. Các admin mới phải do `SYSTEM_ADMIN` gán trong `/users`.

## 4. Flow phân quyền đúng

### Admin web thêm Trưởng bộ môn

```text
/users
→ chọn user_id
→ role DEPARTMENT_HEAD
→ scope DEPARTMENT
→ chọn bộ môn CNTT
→ Gán quyền
```

### Trưởng bộ môn thêm Chủ môn

```text
/users
→ chọn user_id
→ role SUBJECT_OWNER
→ scope SUBJECT hoặc SUBJECT_VERSION
→ chọn DBI102 hoặc DBI102_SU26
→ Gán quyền
```

Backend kiểm tra DBI102/DBI102_SU26 có nằm trong bộ môn của Trưởng bộ môn không.

### Chủ môn thêm Người duyệt câu hỏi

```text
/users
→ chọn user_id
→ role QUESTION_REVIEWER
→ scope SUBJECT / SUBJECT_VERSION / CHAPTER
→ chọn môn/version/bài
→ Gán quyền
```

## 5. API chính

```text
GET    /api/rbac/me
GET    /api/rbac/roles
GET    /api/rbac/permissions
GET    /api/rbac/assignments
POST   /api/rbac/assignments
DELETE /api/rbac/assignments/{assignment_id}
POST   /api/rbac/bootstrap/system-admin
```

## 6. Quyền theo kế hoạch

| Permission | Admin web | Trưởng bộ môn | Chủ môn | Người duyệt |
|---|---:|---:|---:|---:|
| user.manage_all | ✅ | ❌ | ❌ | ❌ |
| department.manage_all | ✅ | ❌ | ❌ | ❌ |
| department.assign_head | ✅ | ❌ | ❌ | ❌ |
| subject.create | ✅ | ✅ | ❌ | ❌ |
| subject.update | ✅ | ✅ | ✅ | ❌ |
| subject.assign_owner | ✅ | ✅ | ❌ | ❌ |
| reviewer.assign | ✅ | ✅ | ✅ | ❌ |
| course.sync | ✅ | ✅ | ✅ | ❌ |
| document.manage | ✅ | ✅ | ✅ | ❌ |
| question.generate | ✅ | ✅ | ✅ | ❌ |
| question.edit | ✅ | ✅ | ✅ | ✅ |
| question.approve | ✅ | ✅ | ✅ | ✅ |
| question.reject | ✅ | ✅ | ✅ | ✅ |
| bank.release.create | ✅ | ✅ | ✅ | ❌ |
| bank.release.publish | ✅ | ✅ | ✅ có điều kiện | ❌ |
| quiz.preview | ✅ | ✅ | ✅ | ❌ |
| quiz.create_openedx | ✅ | ✅ | ✅ | ❌ |
| quota.manage | ✅ | ✅ | ❌ | ❌ |
| audit.view | ✅ | ✅ | ✅ | Chỉ scope của mình |

## 7. Lưu ý

- Bản này chưa tự sync Course Admin/Course Staff vào Open edX. Form có cờ `sync_openedx` để ghi nhận yêu cầu, nhưng sync kỹ thuật Open edX nên làm ở bản riêng sau khi chốt endpoint/permission trong Open edX.
- Bản này vẫn giữ legacy role `admin/teacher/reviewer/viewer` để tương thích UI/API cũ; effective role được nâng từ assignment RBAC khi user đăng nhập lại.
