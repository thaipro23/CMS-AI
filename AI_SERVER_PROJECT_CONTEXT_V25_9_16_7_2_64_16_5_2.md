# AI SERVER / OPEN edX CMS — CONTEXT v25.9.16.7.2.64.16.5.2

## Baseline bắt buộc

```text
Version: v25.9.16.7.2.64.16.5.2 — Global Visual Polish All Pages
Zip: ai-server-openedx-v25.9.16.7.2.64.16.5.2-global-visual-polish-all-pages.zip
Root: ai_server_openedx_v25_9_16_7_2_64_16_5_2
```

Tiếp tục trực tiếp từ bản này. Không quay lại baseline cũ nếu người dùng không yêu cầu rõ ràng.

## Visual contract hiện tại

- Sidebar tối; topbar và workspace sáng.
- Không có theme switcher hoặc dark mode toàn trang.
- PageHeader, KPI, section, notice, status, empty/error state và table summary dùng SVG icon.
- Card có nền semantic nhạt, border nhẹ, bo góc vừa phải và shadow thấp.
- Bảng hiển thị đầy đủ cột mặc định, tự co giãn và xuống dòng; chỉ table container cuộn ngang khi cần.
- Người dùng vẫn có thể chủ động ẩn/hiện cột.
- Không dùng Unicode marker làm icon trạng thái.
- Không thêm Bootstrap, React-Bootstrap, jQuery hoặc Metronic.

## Phạm vi đã áp dụng

- Dashboard và toàn bộ Bank.
- Question review, Quiz và history.
- Student, Teacher và Analytics.
- Jobs, Audit và AP Sync.
- Premises và Semesters.
- Users/RBAC và Settings.
- Auth callback và redirect pages.

## Boundary nghiệp vụ

- Không thay API contract.
- Backend vẫn enforce RBAC và scope.
- Bank hierarchy giữ: Bộ môn → Môn → một Phiên bản môn cuối theo học kỳ → Bài → Câu hỏi.
- Release và Quiz là workflow đầu ra.
- Assignment score write vẫn externalized.
- Tác vụ nặng vẫn chạy Celery.
- Không fake dữ liệu.

## Database

Không có migration mới. Latest migration:

```text
0052_v25_9_16_7_2_27_learning_behavior_logic_calibration.py
```

Không reset DB, xóa volume hoặc sửa tay Alembic history.

## Verification

```text
Backend compileall: PASS
Frontend TypeScript: PASS
Release tests: 8 passed
Current UX regression: 41 passed
Business regression: 30 passed
Next build: 29/29 + standalone PASS
Global visual gate: 12/12
UX gate: 24/24
Security static: 20/20
Production browser source contract: 12/12
Maintainability: 0 blocker, 6 inherited warnings
```

Browser UAT với thiết bị, dữ liệu và tài khoản role thật vẫn bắt buộc trước production sign-off.
