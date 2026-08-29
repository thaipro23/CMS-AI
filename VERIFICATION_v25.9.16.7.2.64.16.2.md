# Verification — v25.9.16.7.2.64.16.2

## Static and compile checks

```text
Backend compileall: PASS
Frontend TypeScript: PASS
Shell syntax: PASS
Docker Compose production YAML: PASS
Docker Compose development YAML: PASS
```

## Tests

```text
Release contract .64.16.2: 8 passed
Selected Bank/Quiz/RBAC regression: 48 passed
Historical assertions intentionally deselected: 8
```

Các assertion bị loại khỏi regression sign-off chỉ thuộc các nhóm sau:

- Kiểm tra chính xác version của artifact lịch sử.
- Geometry cũ yêu cầu selection column 52px, trong khi dense contract hiện tại là 44px.
- Test cũ yêu cầu `academic.manage_assignment_scores`, trái với boundary Assignment score đã externalized.

Không sửa ngược contract hiện tại để làm xanh các assertion lịch sử này.

## Frontend production build

```text
Next.js: 14.2.35
Compiled successfully
Type validation successful
Static pages: 29/29
Finalizing page optimization: completed
Collecting build traces: completed
.next/standalone/server.js: present
```

Production bundle check:

```text
No Bootstrap or React-Bootstrap dependency
No "Kiểm tra GPT"
No "Tính lại học online"
No "UAT UX acceptance"
No theme-switch control
```

## Read-only source gates

```text
UX acceptance: READY — 24/24, 0 blocker, 0 warning
Security attack simulation: READY — 20/20 protected
Maintainability: READY_WITH_WARNINGS — 0 blocker, 6 inherited warnings
```

## Database

```text
No migration 0053
Latest migration: 0052_v25_9_16_7_2_27_learning_behavior_logic_calibration.py
```

Không reset database, không xóa volume và không sửa tay Alembic history trong quá trình phát triển/verification.

## Chưa tuyên bố

- Chưa tuyên bố browser visual UAT đã pass trên server thật.
- Chưa tuyên bố create/publish/rollback đã được chạy bằng credential production.
- Cần deploy UAT và kiểm tra bằng các role thực trước production sign-off.
