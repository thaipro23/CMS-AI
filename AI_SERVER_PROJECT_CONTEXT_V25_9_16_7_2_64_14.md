# AI Server / Open edX CMS — Context v25.9.16.7.2.64.14

Baseline bắt buộc mới: `v25.9.16.7.2.64.14 — Training/Ops UX Completion + UAT UX Acceptance Gate`.

Zip: `ai-server-openedx-v25.9.16.7.2.64.14-training-ops-ux-uat-gate.zip`  
Root: `ai_server_openedx_v25_9_16_7_2_64_14`

Bản này tiếp tục trực tiếp từ `.64.13` và không có migration mới; latest vẫn là `0052_v25_9_16_7_2_27_learning_behavior_logic_calibration.py`.

Thay đổi chính:

- Teacher management và Student management index dùng EnterpriseDataTable + URL state.
- Jobs dùng EnterpriseDataTable + URL filter/group/pagination/density.
- Audit tìm kiếm server-side, EnterpriseDataTable và CSV export theo filter/RBAC.
- StatusBadge có icon + text + color.
- Endpoint read-only `GET /api/health/uat-ux-acceptance` và panel trong `/ops/readiness`.
- Bank hierarchy giữ nguyên: Bộ môn → Môn → một Phiên bản môn cuối theo học kỳ → Bài/Chapter → Câu hỏi.
- Release và Quiz là workflow đầu ra, không phải node trong Bank hierarchy.
- Không thay đổi Assignment write hoặc Open edX enrollment/publish semantics.

Quy tắc tiếp tục giữ nguyên: không fake dữ liệu, không reset DB/xóa volume/sửa tay alembic_version, backend enforce RBAC, tác vụ nặng qua Celery.
