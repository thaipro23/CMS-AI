# Batch 11 — Global Enterprise Screen Contract

## Phạm vi

Chuẩn hóa cấu trúc giao diện theo design contract của module Bank cho các route:

- `/student-management`
- `/student-management/subjects/{subjectId}/classes`
- `/student-management/classes/{classId}`
- `/teacher-management`
- `/teacher-management/teachers/{teacherId}/classes`
- `/teacher-management/classes/{classId}` qua màn chi tiết lớp dùng chung
- `/analytics/learning`
- `/jobs`
- `/audit`
- `/ap-sync`
- `/premises`
- `/semesters`
- `/users`
- `/training-management` legacy redirect

## Cấu trúc dùng chung

```text
AppShell
└── Main workspace
    ├── Topbar breadcrumb
    ├── Page identity
    │   ├── Icon
    │   ├── H1
    │   ├── Description
    │   └── Page actions
    ├── Feedback / notice
    ├── KPI / filter / workflow nếu có
    └── Content sections / EnterpriseDataTable
```

## Component mới

### `EnterpriseScreenHeader`

Kết hợp:

- đăng ký title, icon và breadcrumb cho topbar;
- hiển thị page identity trong main workspace;
- đưa primary/secondary action về cùng page identity;
- hỗ trợ description, meta, icon và tone.

### `EnterprisePageIdentity`

Chuẩn hóa một `h1`, icon trong flex layout, mô tả ngắn và action responsive.

### `EnterpriseSection`

Contract section dùng chung cho các batch tiếp theo khi cần chuyển dần các section legacy.

## CSS contract

File `frontend/styles/enterprise-screen-contract.css` chuẩn hóa:

- workspace padding và gap;
- page identity;
- card/section surface;
- section header;
- filter layout;
- action wrapping;
- table viewport;
- responsive 1024px, 768px và mobile;
- permission/empty state vẫn có đúng page context.

## Nghiệp vụ giữ nguyên

- Không thay API.
- Không thay query state.
- Không thay RBAC.
- Không thay server-side pagination/filter/sort.
- Không thay workflow đồng bộ, analytics, export hoặc audit.

## Chưa thực hiện trong batch này

- Chưa thiết kế chi tiết từng KPI/filter/table theo từng nghiệp vụ.
- Chưa thay đổi nội dung cột hoặc thứ tự action nghiệp vụ.
- Chưa chạy test, lint, typecheck, build hoặc browser smoke test theo yêu cầu người dùng.
