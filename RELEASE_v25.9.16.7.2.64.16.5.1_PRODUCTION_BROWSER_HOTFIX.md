# Release v25.9.16.7.2.64.16.5.1

## Production Browser Hotfix

Baseline trực tiếp: `v25.9.16.7.2.64.16.5`.

## Lỗi production/UAT được sửa

### Quiz auto-map 502

`POST /api/question-bank-v2/quiz/auto-map/preview` từng trả:

```text
name 'Department' is not defined
```

Nguyên nhân: `QuestionBankQuizCreationWorkflowService` sử dụng model `Department` để resolve scope nhưng module workflow tách riêng chưa import model này.

Fix: import `Department` trực tiếp từ `app.models.question_bank`. Không thay đổi request/response contract hoặc logic map Course CMS.

### Sidebar quá nhiều thông tin lặp

- Bỏ mô tả nhỏ dưới từng menu item.
- Bỏ footer trạng thái `CMS đã kết nối` và mã người dùng.
- Bỏ subtitle thương hiệu không cần thiết.
- Topbar chỉ giữ breadcrumb, trạng thái CMS, avatar và vai trò.

### Breadcrumb và page title Bank bị lặp

Các route Bank chỉ giữ breadcrumb cần thiết để nhận biết phạm vi cha. Page title không lặp tên department/subject/offering đã có trong breadcrumb.

Ví dụ:

```text
Ngân hàng câu hỏi > Bộ môn > Công nghệ thông tin
Môn học
```

thay vì lặp thêm `Môn học · Công nghệ thông tin` ở nhiều vị trí.

### Bảng tự động ẩn quá nhiều cột

Cơ chế responsive cũ của `.64.16.5` tự ẩn `optional/important` columns và chuyển sang row details. Cơ chế này không phù hợp yêu cầu vận hành thực tế.

Contract mới:

- Hiển thị toàn bộ cột mặc định.
- `table-layout: auto` và width theo nội dung/type.
- Cột số, index và action compact.
- Text/status/progress được xuống dòng.
- Không line-clamp nội dung bảng.
- Chỉ table container cuộn ngang khi thực sự cần.
- Người dùng vẫn có thể chủ động ẩn/hiện bằng `Cột hiển thị`.
- Reset storage key để preference auto-hidden cũ không tiếp tục làm mất cột sau deploy.

## Accessibility giữ nguyên

- Checkbox indeterminate.
- Sticky offsets theo cột thực tế.
- Table scroll region có label và keyboard focus.
- Pagination semantics.
- Mobile drawer/focus trap/Safari fallback.
- Reduced motion, forced colors và iOS safe-area.

## Database và nghiệp vụ

- Không có migration mới.
- Alembic head: `0052_v25_9_16_7_2_27_learning_behavior_logic_calibration.py`.
- Không thay RBAC backend, Celery, Open edX publish/rollback, Assignment externalization hoặc Bank hierarchy.
