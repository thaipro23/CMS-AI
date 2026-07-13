# v25.9.16.7.2.64.14 — Training/Ops UX Completion + UAT UX Acceptance Gate

## Mục tiêu

Hoàn thiện UX cho bốn màn vận hành/đào tạo có dữ liệu lớn mà không thay đổi Bank workflow hoặc schema database:

```text
/teacher-management
/student-management
/jobs
/audit
```

Bản này phát triển trực tiếp từ `v25.9.16.7.2.64.13 — Bank Workflow UX Completion`.

## Thay đổi chính

### Training

- `/teacher-management` dùng `EnterpriseDataTable` với sticky identity/action columns, page size 20/50/100, column visibility và density.
- `/student-management` dùng cùng table contract cho danh sách môn.
- Filter quan trọng được giữ trong URL: `q`, `status`, `page`, `page_size`, `density`, `term_id`, `branch`, `campus`.
- Search debounce 350 ms; API vẫn phân trang server-side.
- Giữ nguyên lightweight teacher report `include_classes=false` và tác vụ Excel nền.
- Không khôi phục Assignment score write.

### Operations

- `/jobs` gom các nguồn job như cũ nhưng phân trang client-side trên tập bounded đã tải; filter/group/page/density giữ trong URL.
- Progress bar có `role=progressbar` và ARIA value.
- `/audit` dùng `EnterpriseDataTable`, tìm kiếm server-side và xuất CSV theo đúng filter + RBAC.
- Endpoint mới: `GET /api/audit/export.csv` với cap 50.000 dòng cho system admin; non-admin vẫn fail-closed theo bounded visibility window hiện có.

### Semantic status

- `StatusBadge` dùng icon + text + color; màu không còn là tín hiệu duy nhất.
- Enterprise table giữ loading/error/empty/pagination contract và vùng scroll ngang focusable.

### UAT UX acceptance gate

Endpoint mới, read-only:

```text
GET /api/health/uat-ux-acceptance
```

Gate kiểm tra source contract cho:

- EnterpriseDataTable trên bốn màn chính.
- URL-preserved state.
- loading/empty/pagination wiring.
- keyboard-focusable horizontal table container.
- semantic StatusBadge.
- Audit search/export RBAC contract.
- Ops readiness integration.

`READY` chỉ có nghĩa source contract đạt; vẫn phải chạy browser UAT thật.

## Database

Không có migration mới. Migration cuối vẫn là:

```text
0052_v25_9_16_7_2_27_learning_behavior_logic_calibration.py
```

## Boundary giữ nguyên

```text
Bộ môn → Môn học → một Phiên bản môn cuối theo học kỳ → Bài/Chapter → Câu hỏi
```

Release và Quiz là workflow đầu ra. Assignment score write vẫn externalized.

## Kết quả kiểm tra source

```text
backend compileall: passed
frontend typecheck: passed
.64.14 release tests: 8 passed
selected Bank/Training/security regression: 22 passed
shell syntax: passed
UX acceptance static gate: READY, 24/24 checks, 0 blocker, 0 warning
maintainability contract: READY_WITH_WARNINGS, 0 blocker, 6 large-file warnings kế thừa
```

Frontend production build trong sandbox đã đạt:

```text
Compiled successfully
Linting and checking validity of types
Generated static pages 29/29
Finalizing page optimization
```

Sandbox tiếp tục timeout tại `Collecting build traces`, giống giới hạn đã ghi nhận ở `.64.13`. Vì `.next/standalone` chưa được tạo trong sandbox, cần chạy `docker compose ... build frontend` hoặc `scripts/frontend-build-verify.sh` trên UAT để chốt standalone trace trước sign-off.

Audit CSV có UTF-8 BOM và trung hòa giá trị bắt đầu bằng `=`, `+`, `-`, `@` để hạn chế spreadsheet formula injection.
