# v25.9.16.7.2.64.16.5.7.2.7 — Batch 35.3

## Training Operations Platform Split

Batch 35.3 tách nhóm **Vận hành đào tạo** thành bốn module độc lập:

1. Quản lý sinh viên CMS.
2. Quản lý giảng viên CMS.
3. Quản lý sinh viên Udemy.
4. Quản lý giảng viên Udemy.

## Contract nghiệp vụ

- Chỉ `/subject-management` quản lý nền tảng theo **Hệ + Học kỳ + Môn học**, không yêu cầu chọn Block.
- Lớp, sinh viên, giảng viên, kế hoạch Udemy, import, dashboard, Course mapping và đồng bộ vẫn giữ identity theo Block.
- API vận hành nhận `learning_platform=cms|udemy` và backend enforce filter theo delivery thực tế.
- Route cũ `/student-management` và `/teacher-management` vẫn mở CMS để giữ tương thích bookmark.
- Không có migration mới; Alembic head giữ nguyên `0057`.

## UX

- CMS chỉ hiển thị Course, CMS identity, enrollment, learning analytics và điều kiện thi.
- Udemy chỉ hiển thị tỷ lệ đã import, tiến độ, mốc yêu cầu và cảnh báo chậm tiến độ.
- Drill-down giữ `platform` trong URL và vẫn có bộ lọc Block.
