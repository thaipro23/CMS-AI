# AI SERVER / OPEN edX CMS — CONTEXT v25.9.16.7.2.64.16.5.3

## Baseline bắt buộc

```text
v25.9.16.7.2.64.16.5.3 — Frontend Layout Integrity + Runtime Reliability Hotfix
zip: ai-server-openedx-v25.9.16.7.2.64.16.5.3-frontend-layout-runtime-reliability.zip
root: ai_server_openedx_v25_9_16_7_2_64_16_5_3
```

Tiếp tục trực tiếp từ bản này. Không quay lại baseline cũ khi source mới không có regression bắt buộc.

## Thay đổi canonical

### Backend

- Quiz auto-map đã import đủ `Department`, `SequenceMatcher`, `normalize_difficulty`.
- Academic sync/enrollment đã import đủ SQLAlchemy boolean helpers và `AcademicTerm`.
- Learning Analytics core đã import `json_safe_value`.
- `scripts/backend-runtime-name-audit.sh` quét toàn bộ backend bằng symbol table và là một phần của review/UAT gate.

### Frontend

- Sidebar tối; topbar/workspace sáng; không có theme switcher.
- Eyebrow + title + icon của trang hiển thị ở top bar.
- `PageHeader` không render title/description trong content; chỉ render page actions.
- `PageRoot` đăng ký class route cho `<main id="main-content">` và không tạo wrapper DOM.
- Không dùng row action menu `...`; action ít được hiển thị trực tiếp.
- `layout-integrity.css` là lớp CSS cuối, enforce spacing, divider, flow, wrapping và non-overlap toàn hệ thống.
- Bảng hiển thị đầy đủ cột mặc định; text tự xuống dòng; chỉ table container cuộn ngang.
- Next production build giới hạn 2 worker và trace trong frontend workspace.

## Business boundary giữ nguyên

- Bank hierarchy: Bộ môn → Môn → một phiên bản môn cuối theo học kỳ → Bài → Câu hỏi.
- Release và Quiz là workflow đầu ra.
- Assignment score write vẫn externalized.
- Backend enforce scoped RBAC.
- Tác vụ nặng chạy Celery.
- Không fake dữ liệu.
- Không reset DB, xóa volume hoặc sửa tay `alembic_version`.
- Không có migration mới; Alembic head vẫn là `0052_v25_9_16_7_2_27_learning_behavior_logic_calibration.py`.

## Verification gần nhất

```text
Backend compileall PASS
TypeScript PASS
Release contract 12 passed
Frontend regression 61 passed
Business regression 39 passed
Next.js 29/29 + standalone PASS
Backend runtime audit READY: 266 files, 0 undefined globals
Layout integrity READY 15/15
UX READY 24/24
Security READY 20/20
Maintainability 0 blocker, 6 warning kế thừa
```

Browser UAT với dữ liệu và role thật vẫn bắt buộc trước production sign-off.
