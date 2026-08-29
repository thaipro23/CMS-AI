# AI SERVER / OPEN edX CMS — CONTEXT v25.9.16.7.2.64.16.3

## Baseline bắt buộc

```text
v25.9.16.7.2.64.16.3 — Training Operations + Analytics UX
zip: ai-server-openedx-v25.9.16.7.2.64.16.3-training-operations-analytics-ux.zip
root: ai_server_openedx_v25_9_16_7_2_64_16_3
```

Tiếp tục trực tiếp từ `.64.16.3`; không dùng baseline cũ nếu người dùng không yêu cầu rõ.

## UI contract hiện tại

- Sidebar tối cố định; topbar và content sáng.
- Không có theme switcher toàn hệ thống.
- `EnterpriseDataTable` dùng column kind/priority và ẩn cột phụ trước khi cuộn ngang.
- Production ẩn diagnostics/UAT controls bằng `NEXT_PUBLIC_ENABLE_DIAGNOSTICS_UI=false`.
- Không thêm Bootstrap, React-Bootstrap, Metronic hoặc jQuery.

## Thay đổi `.64.16.3`

- Thêm `frontend/components/training/TrainingWorkspace.tsx`.
- Thêm `frontend/styles/training-analytics-ux.css`.
- Student subject classes và teacher classes dùng `EnterpriseDataTable`/URL state.
- Teacher classes không còn bảng ma trận điểm rộng.
- Analytics là wizard ba bước: Môn → Lớp → Xem kết quả.
- Mapping/data error có empty state nghiệp vụ, không lộ raw `Failed to fetch`.
- Student class detail không còn control ghi Assignment; chỉ đọc snapshot bên ngoài.
- `useAcademicTableState` hỗ trợ `block_id`.

## Boundary bắt buộc

- Không fake dữ liệu.
- Không reset DB, xóa volume hoặc sửa tay `alembic_version`.
- Backend enforce RBAC; frontend chỉ ẩn route/action theo capability.
- SYSTEM_ADMIN toàn hệ thống; CAMPUS_OWNER theo cơ sở; TEACHER_ASSIGNED theo AP assignment.
- Bank hierarchy: Bộ môn → Môn → một phiên bản cuối theo học kỳ → Bài → Câu hỏi.
- Release/Quiz là workflow đầu ra.
- Assignment score write externalized, không khôi phục.
- Tác vụ nặng chạy Celery.

## Database

Không có migration mới. Latest:

```text
0052_v25_9_16_7_2_27_learning_behavior_logic_calibration.py
```

## Verification

```text
Backend compileall: PASS
Frontend TypeScript: PASS
Release tests: 9 passed
Selected regression: 63 passed
Next build: 29/29 + standalone PASS
UX gate: READY 24/24
Security static: READY 20/20
Maintainability: 0 blocker, 6 warnings kế thừa
```

## Bản tiếp theo theo roadmap

```text
v25.9.16.7.2.64.16.4 — Operations + Catalog + Settings + RBAC UX
```

Phạm vi dự kiến: Jobs, Audit, AP Sync, Cơ sở, Học kỳ, Settings và Người dùng/Phân quyền. Nếu browser UAT `.64.16.3` có regression, tạo hotfix trước thay vì thêm feature.
