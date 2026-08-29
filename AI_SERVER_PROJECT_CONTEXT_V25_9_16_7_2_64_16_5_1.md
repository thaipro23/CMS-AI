# AI SERVER / OPEN edX CMS — CONTEXT v25.9.16.7.2.64.16.5.1

## Baseline bắt buộc

```text
v25.9.16.7.2.64.16.5.1 — Production Browser Hotfix
zip: ai-server-openedx-v25.9.16.7.2.64.16.5.1-production-browser-hotfix.zip
root: ai_server_openedx_v25_9_16_7_2_64_16_5_1
```

Tiếp tục trực tiếp từ `.64.16.5`; không dùng baseline cũ khi source này có mặt.

## Thay đổi canonical

- Quiz auto-map import đúng model `Department`; endpoint preview không còn lỗi NameError/502.
- Sidebar tối chỉ hiển thị icon + nhãn; bỏ description nhỏ và footer session/CMS.
- Topbar không lặp username/id; user detail nằm trong popover.
- Breadcrumb Bank được rút gọn theo scope cha; page title chỉ nêu màn hiện tại.
- EnterpriseDataTable không tự động giấu cột theo viewport.
- Mọi cột hiển thị mặc định; width tự nhiên theo loại và nội dung được wrap.
- Cột số/index/status/action compact; text chính dùng phần không gian còn lại.
- Horizontal scroll chỉ nằm trong table container khi nội dung thực sự không thể vừa.
- Manual column visibility, URL state, server-side operation, sticky columns và accessibility vẫn giữ.

## Boundary

- Không Bootstrap/jQuery/Metronic.
- Không thay API contract, backend RBAC, Bank workflow, Celery hoặc Open edX semantics.
- Không khôi phục Assignment score write.
- Không có migration mới; latest migration vẫn là `0052_v25_9_16_7_2_27_learning_behavior_logic_calibration.py`.
- Không reset DB/xóa volume/sửa tay Alembic history.

## Verification

```text
Backend compileall PASS
TypeScript PASS
Hotfix tests 6 passed
Current-contract regression 28 passed
Next production build 29/29 + standalone PASS
UX 24/24
Security 20/20
Production browser source contract 12/12
Maintainability 0 blocker / 6 inherited warnings
```

Browser UAT thật vẫn bắt buộc trước production sign-off.
