# v25.9.16.7.2.64.16.5.7.2.4 — Batch 35 Udemy Production Hardening

## Mục tiêu

Harden chức năng Udemy từ Batch 31–34 để vận hành production, không chuyển dữ liệu ACMS cũ.

## Hoàn thành

- Upload `.xlsx` có giới hạn cấu hình, xác thực Content-Type/OpenXML, chống path traversal và zip bomb.
- Redis rate limit cho import, retry và export.
- Import/export worker có late acknowledgement, worker-loss protection và retry lỗi hạ tầng tạm thời.
- Export Udemy nền persistent, tiếp tục sau F5, reuse job trùng và tải file có RBAC recheck.
- Retention cleanup định kỳ, không xóa file nguồn của import active.
- Celery healthcheck dùng node hostname xác định.
- Migration 0057 thêm ba composite index cho dashboard/filter/export ở quy mô lớn.
- Bổ sung biến môi trường, test Batch 35, tài liệu deploy và UAT.

## Không thực hiện

- Không có ACMS importer, mapping tool, data migration hoặc data backfill.
- Không reset DB/volume.
- Không sửa tay `alembic_version`.
- Không thay đổi semantic CMS/Open edX.

## Database

Alembic head mới:

```text
0057_v25_9_16_7_2_64_35
```

Migration chỉ tạo index, không biến đổi dữ liệu.
