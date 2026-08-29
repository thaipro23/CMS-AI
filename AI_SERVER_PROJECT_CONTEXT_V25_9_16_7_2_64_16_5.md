# AI SERVER / OPEN edX CMS — CONTEXT v25.9.16.7.2.64.16.5

## Baseline bắt buộc

```text
v25.9.16.7.2.64.16.5 — Cross-browser, Responsive, Accessibility & Production UX Acceptance
zip: ai-server-openedx-v25.9.16.7.2.64.16.5-production-ux-acceptance.zip
root: ai_server_openedx_v25_9_16_7_2_64_16_5
```

Tiếp tục trực tiếp từ `.64.16.5`; không quay lại baseline cũ.

## UI contract hiện tại

- Sidebar tối cố định; topbar/content sáng; không có theme switcher.
- `EnterpriseDataTable` tự đo chiều rộng container.
- Tablet ẩn optional, mobile chỉ giữ required.
- Cột responsive bị ẩn được hiển thị qua hàng Chi tiết, không mất dữ liệu.
- Sticky offset tính theo đúng cột thực tế đang hiển thị.
- Drawer/sidebar có focus trap, Escape, focus return và fallback Safari.
- Pagination và table scroll có semantic accessibility.
- Safe-area, coarse pointer, forced-colors và reduced-motion đã có contract.

## Verification source

- Backend compileall PASS.
- Frontend TypeScript PASS.
- `.64.16.5` tests: 7 passed.
- Current-contract regression: 55 passed; 8 historical assertions deselected có chủ đích.
- Next.js production build: 29/29 pages, standalone được tạo.
- UX source gate: READY 24/24.
- Security static gate: READY.
- Maintainability: 0 blocker, 6 cảnh báo large-file kế thừa.

## Chưa được phép khẳng định

Static gate/build không thay thế browser UAT. Trước production sign-off phải chạy checklist tạo bởi:

```bash
./scripts/production-ux-acceptance-report.sh
```

với dữ liệu thật và từng role thật.

## Database và nghiệp vụ

- Không có migration `0053`; latest vẫn là `0052_v25_9_16_7_2_27_learning_behavior_logic_calibration.py`.
- Không reset DB/xóa volume/sửa tay Alembic.
- Không thay backend RBAC.
- Không thay Bank hierarchy hoặc Release/Quiz semantics.
- Assignment score write vẫn externalized.
- Không thêm Bootstrap.

## Hướng tiếp theo

Nếu browser UAT phát hiện regression: `.64.16.5.1 — Production UX Browser Hotfix`.
Nếu browser UAT sạch: chuyển sang `.65 — Production Rollout & Operational Closure`.
