# v25.9.16.5.82 — Teacher Flow Split + CMS Score Update CTA

## Mục tiêu

Tách Teacher Management thành 3 trang vận hành rõ ràng:

1. `/teacher-management`: danh sách giáo viên.
2. `/teacher-management/teachers/[teacherId]/classes`: danh sách lớp của giáo viên.
3. `/teacher-management/classes/[classId]`: chi tiết lớp, dùng lại màn chi tiết lớp hiện có và giữ breadcrumb quay lại luồng giáo viên.

## Thay đổi chính

- Bỏ expand lớp inline trong trang giáo viên để tránh render bảng nặng trong cùng một page.
- Nút `Xem lớp` trên từng giáo viên chuyển sang route riêng.
- Thêm API filter `teacher_id` cho `/api/academic/training/teachers` và export.
- Thêm trang lớp của giáo viên với KPI, bảng lớp, cột Detailed grades động, deadline quiz, điều kiện thi và link `Chi tiết lớp`.
- Route chi tiết lớp trong teacher-management re-export màn chi tiết lớp hiện có để tránh duplicate logic.
- Màn chi tiết lớp đổi CTA nghiệp vụ từ `Đồng bộ full CMS` sang `Cập nhật điểm CMS` / `Cập nhật điểm`.
- Nút refresh dữ liệu phụ đổi thành `Tải lại dữ liệu`, không gọi là `Làm mới` cạnh tác vụ điểm nữa.

## Lưu ý

Bản này chưa tạo materialized cache/database summary mới. Nó hoàn thiện luồng điều hướng 3 trang trước để v83/v84 có thể gắn cache và background Excel job sạch hơn.
