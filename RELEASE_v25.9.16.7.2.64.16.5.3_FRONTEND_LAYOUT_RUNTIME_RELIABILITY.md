# Release v25.9.16.7.2.64.16.5.3

## Frontend Layout Integrity + Runtime Reliability Hotfix

Baseline trực tiếp: `v25.9.16.7.2.64.16.5.2 — Global Visual Polish All Pages`.

## 1. Runtime reliability

### Quiz auto-map

Đã sửa các tên được sử dụng nhưng chưa import trong workflow Quiz:

```text
Department
SequenceMatcher
normalize_difficulty
```

Endpoint ảnh hưởng:

```text
POST /api/question-bank-v2/quiz/auto-map/preview
```

Release test chạy trực tiếp nhánh match Section bằng `SequenceMatcher` và nhánh resolve tên bộ môn bằng `Department`.

### Audit toàn backend

Thêm `scripts/backend-runtime-name-audit.sh`, dùng Python symbol table để quét toàn bộ `backend/app/**/*.py`. Audit hiện quét 266 file và không còn tên global chưa được định nghĩa hoặc lỗi cú pháp.

Audit cũng phát hiện và sửa các import tiềm ẩn khác:

- `and_`, `or_`, `AcademicTerm` trong Academic sync/enrollment.
- `json_safe_value` trong Learning Analytics core.

Script được tích hợp vào review pack và UAT build gate.

## 2. Page chrome và markup

- `PageHeader` chỉ còn action của trang.
- Eyebrow, SVG icon và `h1` được đăng ký lên top bar qua `PageShellContext`.
- Bỏ hoàn toàn `enterprise-page-header-copy` và `enterprise-page-description` khỏi output trang.
- `PageRoot` đăng ký class layout rồi trả Fragment; `<main id="main-content">` nhận trực tiếp `page-stack` và class route.
- Giảm một wrapper DOM ngoài cùng nhưng vẫn giữ landmark và route layout hiện có.

## 3. Action UX

- Bỏ các row menu `...`, `•••` và `⋮` trong frontend production.
- Nếu một dòng có một hoặc hai thao tác, các nút được hiển thị trực tiếp.
- Bank question review tiếp tục preview-first; duyệt/từ chối/sửa đầy đủ nằm trong drawer, không tạo menu ẩn vô ích.
- Premises, Semesters, Student, Teacher và các entity Bank dùng action trực tiếp.

## 4. Layout integrity toàn frontend

Thêm lớp CSS cuối `frontend/styles/layout-integrity.css` để thống nhất:

- spacing token;
- margin/padding/gap;
- border và divider;
- page/section/card flow;
- header/action wrapping;
- table cell wrapping và sticky separator;
- alert icon ở normal flow;
- modal/drawer header-body-footer;
- form/grid responsive;
- forced colors và reduced motion.

Đã loại bỏ negative margin trong active frontend CSS. Decorative pseudo-element không được phép che nội dung. Body không cuộn ngang; table container tự cuộn khi thật sự cần.

## 5. Production build stability

`frontend/next.config.js` giữ `output: 'standalone'` và giới hạn:

```text
experimental.cpus = 2
experimental.outputFileTracingRoot = frontend workspace
```

Việc này tránh Next.js tạo hàng chục static-generation worker trên host expose nhiều CPU logic và tránh trace sibling artifact không liên quan.

## 6. Không thay đổi

- Không thêm Bootstrap, React-Bootstrap, jQuery hoặc Metronic.
- Không thay API contract.
- Không thay backend RBAC hoặc scope inheritance.
- Không thay Celery workflow.
- Không thay Bank hierarchy, Release, Quiz, publish hoặc rollback semantics.
- Không khôi phục Assignment score write.
- Không có migration mới; Alembic head vẫn là `0052`.
