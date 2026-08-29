# AI Server / Open edX CMS — Context v25.9.16.7.2.64.15

Baseline bắt buộc mới: `v25.9.16.7.2.64.15 — Scoped RBAC + Analytics Workspace Stabilization + Unified Table Contract`.

Zip: `ai-server-openedx-v25.9.16.7.2.64.15-scoped-rbac-analytics-table-contract.zip`  
Root: `ai_server_openedx_v25_9_16_7_2_64_15`

## Nguồn sự thật

1. Source code zip `.64.15`.
2. Alembic migration thực tế.
3. `.env.production.example` và `docker-compose.prod.yml`.
4. Context này.
5. Context cũ.

## Điểm mới

- `/analytics/learning` tải `GET /api/analytics/classes/{class_id}/workspace` cho summary/rows/doctor.
- Gate vận hành chỉ tải khi người có `ops.readiness.view` chủ động mở.
- `EnterpriseDataTable` có sticky offset động, `colgroup`, STT 64 px, selection 52 px và geometry contract dùng chung.
- Frontend đã bỏ hoàn toàn panel/request `Kiểm tra identity CMS/RollNumber`; không tự clear DB.
- RBAC theo scope hierarchy và được enforce ở backend lẫn UI.
- AP teacher assignment tự cấp effective `TEACHER_ASSIGNED` view permission, không cần gán tay.
- Model metadata khai báo index `ix_academic_classes_scope_lookup` đã được migration `0050` tạo.
- Production backend image chứa source-contract snapshot tại `/source-contract`; static readiness gates không còn đọc nhầm `/` và báo module 0 dòng/missing.

## RBAC chuẩn

```text
SYSTEM_ADMIN      → toàn hệ thống
DEPARTMENT_HEAD   → Department được gán và descendants
SUBJECT_OWNER     → Subject được gán và descendants
QUESTION_REVIEWER → permission + scope được gán và descendants
CAMPUS_OWNER      → lớp thuộc Campus được gán
TEACHER_ASSIGNED  → lớp AP phân công cho đúng username/email
```

Người dùng chỉ thấy route, menu và action phù hợp; mọi API vẫn kiểm tra permission/scope độc lập.

## Analytics permission split

```text
view_training_reports → xem kết quả analytics trong lớp được phép
view_ops_readiness    → xem SLA, evidence, pilot/readiness gates
manage_training_deadlines → enqueue/recalculate analytics
```

Giảng viên AP chỉ có view, không có recalculate.

## Database

Không có migration mới. Latest:

```text
0052_v25_9_16_7_2_27_learning_behavior_logic_calibration.py
```

Không tạo lại `ix_academic_classes_scope_lookup`.

## UAT HTTP nội bộ

Khi chạy HTTP qua file hosts:

```env
APP_ENV=uat
AUTH_COOKIE_SECURE=false
AUTH_COOKIE_SAMESITE=lax
DB_STATEMENT_TIMEOUT_MS=5000
```

Không dùng cấu hình này cho HTTPS production.

## Boundary kế thừa

- Không fake dữ liệu.
- Không reset DB/xóa volume/sửa tay `alembic_version`.
- Tác vụ nặng qua Celery.
- Bank hierarchy: Department → Subject → một final Subject Version/term → Chapter → Question.
- Release/Quiz là downstream workflow.
- Assignment score write externalized.
