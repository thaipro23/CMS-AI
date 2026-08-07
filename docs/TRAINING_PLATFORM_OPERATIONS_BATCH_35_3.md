# Batch 35.3 — Tách Vận hành đào tạo theo nền tảng

## Menu

- Quản lý sinh viên CMS
- Quản lý giảng viên CMS
- Quản lý sinh viên Udemy
- Quản lý giảng viên Udemy

## Backend scope

`learning_platform=cms|udemy` được truyền xuyên suốt frontend → API → service → cache/export worker. Backend lọc theo `academic_subject_deliveries` khớp `subject_id + term_id + block_id + branch`.

## Tương thích

- `/student-management` → CMS.
- `/teacher-management` → CMS.
- Không đổi schema database.
- Không di chuyển hoặc nhân bản dữ liệu.
