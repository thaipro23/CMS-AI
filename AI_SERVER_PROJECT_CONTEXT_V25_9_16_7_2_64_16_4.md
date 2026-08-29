# AI Server / Open edX CMS — Context v25.9.16.7.2.64.16.4

## Baseline bắt buộc

```text
v25.9.16.7.2.64.16.4 — Operations + Catalog + Settings + RBAC UX
zip: ai-server-openedx-v25.9.16.7.2.64.16.4-operations-catalog-settings-rbac-ux.zip
root: ai_server_openedx_v25_9_16_7_2_64_16_4
```

Tiếp tục trực tiếp từ `.64.16.4`; không dùng baseline cũ nếu người dùng không yêu cầu rõ ràng.

## Frontend contract

- Sidebar dark; topbar và workspace light.
- Không có light/dark mode toàn trang.
- EnterpriseDataTable dùng column kind/priority và dense geometry.
- Bank review preview-first; Quiz là workbench ba bước.
- Training/Analytics là workflow Môn → Lớp → Kết quả.
- Operations/Catalog/RBAC dùng shared `OperationsWorkspace`.

## `.64.16.4` changes

- Jobs và Audit compact, detail drawer, URL state giữ nguyên.
- AP Sync: kế hoạch, dry-run, confirm, Celery progress và result workspace; không hard-code học kỳ.
- Premises/Semesters dùng EnterpriseDataTable; block editor responsive.
- Settings chia tab theo domain.
- RBAC user-first/scope-first; assignment detail và import trong drawer.
- StatusBadge hỗ trợ label nghiệp vụ explicit.

## Business boundaries

- Backend enforce RBAC.
- SYSTEM_ADMIN toàn quyền; Department/Subject/Reviewer/Campus/Teacher tuân thủ scope resolver.
- Bank hierarchy giữ: Department → Subject → một Subject Version cuối theo kỳ → Chapter → Question.
- Release và Quiz là workflow đầu ra.
- Assignment score write không được khôi phục.
- Tác vụ nặng chạy Celery.
- Không fake dữ liệu, không reset DB, không xóa volume, không sửa tay Alembic history.

## Database

Không có migration mới. Latest:

```text
0052_v25_9_16_7_2_27_learning_behavior_logic_calibration.py
```

## Verification

```text
Backend compileall PASS
TypeScript PASS
Release tests 9 passed
Selected regression 50 passed
Next build 29/29 + standalone PASS
UX 24/24 READY
Security 20/20 READY
Maintainability 0 blocker / 6 inherited warnings
```

## Roadmap

Bản tiếp theo hợp lý:

```text
v25.9.16.7.2.64.16.5 — Cross-browser, Responsive, Accessibility & Production UX Acceptance
```

Chỉ sửa theo browser UAT thật, sau đó chuyển `.65` Production Rollout.
