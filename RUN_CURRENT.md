# Chọn runbook triển khai hiện hành

Snapshot nguồn: [docs/CURRENT_STATE.md](docs/CURRENT_STATE.md), commit kiểm tra
`f961e76a6bb269e09d93c52ea52b96e7f5b028a5` ngày 15/10/2026.
`VERSION` .18 không đủ xác định các hotfix đã deploy.

- Quy trình build nền: [RUN .18](RUN_V25_9_16_7_2_64_16_5_7_2_18.md) là runbook
  phiên bản cũ; đối chiếu env/manifests/schema hiện tại trước dùng.
- Fix 15/10: [teacher đa hệ](docs/fixes/TEACHER_MULTIBRANCH_REPORT_2026-10-15.md),
  [AI quota](docs/fixes/GENERATION_IMPORT_QUOTA_2026-10-15.md),
  [Quiz context](docs/fixes/QUIZ_CONTEXT_DEFAULT_2026-10-15.md).
- Daily recovery: [runbook](docs/ACADEMIC_DAILY_CONTINUATION_RECOVERY.md),
  [unlock/delivery fix](docs/fixes/DAILY_COORDINATOR_DELIVERY_2026-10-14.md).
- [Jenkinsfile](Jenkinsfile) build/push image; không tự coi CI thành công là đã rollout cluster.
- Migration source tới 0073; kiểm tra Alembic graph và revision thực tế. Không sửa bảng
  version thủ công, không drop database/PVC, flush Redis hoặc purge queue để khắc phục.

Trước kết luận deploy: ghi Git SHA → image digest/tag → backend/worker/frontend
đang chạy → migration/runtime config → smoke đúng tác vụ. Tài liệu này không chạy
build, migrate, resume hoặc deploy. Đọc [docs/INDEX.md](docs/INDEX.md) theo triệu chứng.
