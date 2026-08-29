# v25.9.16.5.84 — Teacher Report Cache + Background Excel Export

## Mục tiêu

Biến Teacher Management từ báo cáo tính động theo request thành báo cáo có cache summary và export Excel chạy nền.

## Thay đổi chính

- Thêm bảng `academic_teacher_report_summaries` để materialize từng dòng giảng viên theo scope `term_id + branch + campus`.
- Thêm bảng `academic_teacher_report_jobs` để theo dõi job `rebuild_cache` và `export_excel`.
- API `/api/academic/training/teachers` ưu tiên đọc cache nếu scope đã được tính lại. Nếu chưa có cache, vẫn fallback tính động để không gãy màn hình.
- Thêm API tạo job tính lại báo cáo và export Excel nền.
- Worker xử lý cache rebuild/export, lưu file Excel vào `/app/.runtime/teacher-reports`.
- UI `/teacher-management` có trạng thái cache, nút `Tính lại báo cáo`, `Xuất Excel nền`, `Tải Excel`, và `Xuất trực tiếp` dự phòng.

## Lưu ý nghiệp vụ

- `Đồng bộ full CMS` vẫn là full flow: check/tạo tài khoản CMS, check enroll, lấy course completion và điểm số.
- `Cập nhật điểm` chỉ chạy `learning_sync`, tức cập nhật điểm/progress từ CMS/Open edX.

## Deploy

Chạy Alembic trước khi recreate backend/worker/frontend.
