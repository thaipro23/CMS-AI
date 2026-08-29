# AI Server / Open edX — Handoff Batch 35

## Canonical

- Version: `v25.9.16.7.2.64.16.5.7.2.4`
- Scope: Udemy production hardening.
- Previous baseline: Batch 34 `v25.9.16.7.2.64.16.5.7.2.3`.
- Alembic head: `0057_v25_9_16_7_2_64_35`.

## Quyết định phạm vi

Theo yêu cầu mới nhất, Batch 35 **không chuyển dữ liệu ACMS cũ**. Mọi đề xuất legacy migration trong roadmap cũ được loại khỏi source release này.

## Thành phần thay đổi

- Backend config và Redis operation rate limiter.
- Udemy workbook validation, retention và export bounds.
- API import hardening và export job/download.
- Celery import/export retry, cleanup Beat và worker healthcheck.
- Frontend export nền có recovery sau F5.
- Migration 0057 index-only.
- Test, environment example và tài liệu deploy/UAT.

## Contract tiếp tục giữ nguyên

- Không fake dữ liệu.
- Không tạo sinh viên từ file Udemy.
- Udemy không gọi Open edX mapping/enrollment/analytics.
- Teacher/campus scope do backend enforce.
- Job nặng persistent và chạy Celery.
- Không reset DB/volume; không sửa tay `alembic_version`.

## Việc cần làm trên UAT

Deploy theo `RUN_V25_9_16_7_2_64_16_5_7_2_4.md`, hoàn tất acceptance checklist, lưu evidence build/migration/worker/browser/RBAC/backup-restore rồi mới đánh dấu production accepted.
