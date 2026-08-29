# Verification — v25.9.16.7.2.64.16.5

## Kết quả tự động

```text
Backend compileall: PASS
Frontend TypeScript: PASS
Shell syntax: PASS
Docker Compose YAML: PASS
```

### Release contract

```text
backend/app/tests/test_v25_9_16_7_2_64_16_5_production_ux_acceptance.py
7 passed
```

### Current-contract regression

```text
55 passed
8 historical assertions deselected
```

Tám assertion bị loại có chủ đích vì kiểm tra version cũ, selection width `52px` đã bị thay bằng compact contract, hoặc tên layout RBAC cũ đã được thay trong `.64.16.4`. Không sửa ngược UX hiện tại để làm xanh test lịch sử.

## Production build

```text
Next.js 14.2.35
Compiled successfully
Type validation successful
Static pages: 29/29
Finalizing page optimization: completed
Collecting build traces: completed
.next/standalone/server.js: present
```

## Source gates

```text
UX acceptance: READY — 24/24
Security attack simulation: READY — 20/20
Maintainability: READY_WITH_WARNINGS
Maintainability blocker: 0
Maintainability warning: 6 large-file warnings kế thừa
```

## Production UX source evidence

```text
scripts/production-ux-acceptance-report.sh: PASS
Static checks: 11/11
Status: READY_FOR_BROWSER_UAT
```

Script tạo browser matrix cho:

- Chrome desktop 1440×900 và 1366×768.
- Edge desktop 1366×768.
- Safari iPhone 390×844.
- Chrome Android 360×800.
- iPad/Safari 768×1024.
- Keyboard-only.
- Windows High Contrast/forced colors.
- Reduced motion.
- Từng role RBAC thật.

## Những gì đã kiểm chứng trong source

- Table responsive dựa theo chiều rộng container.
- Cột bị ẩn trên tablet/mobile không mất dữ liệu; mở qua Chi tiết dòng.
- Sticky offsets được tính theo cột đang hiển thị.
- Checkbox page selection có indeterminate.
- Table scroll và pagination có accessible semantics.
- Sidebar mobile có inert/tabIndex fallback.
- Safari matchMedia fallback tồn tại.
- Drawer khóa body scroll, Escape và focus return.
- Safe-area, forced colors, touch target và reduced motion có CSS contract.

## Giới hạn trung thực

Không có trình duyệt thật hoặc tài khoản Open edX/AP thật trong môi trường build này. Vì vậy chưa tuyên bố browser UAT hoặc production sign-off hoàn tất. Sau deploy phải chạy checklist từ:

```bash
./scripts/production-ux-acceptance-report.sh
```

và lưu evidence bằng ảnh/video/ticket.

## Database boundary

- Không có migration `0053`.
- Alembic head vẫn là `0052_v25_9_16_7_2_27_learning_behavior_logic_calibration.py`.
- Không reset database.
- Không xóa volume.
- Không sửa tay `alembic_version`.
