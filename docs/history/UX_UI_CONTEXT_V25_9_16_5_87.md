# CONTEXT v25.9.16.5.87 — StudentModule Activity-Only Progress Fix

Bản mới nhất nên dùng: `v25.9.16.5.87-studentmodule-activity-progress-fix`.

## Lỗi đã debug

Sau v86, Course completion có thể hiện 8.6%, 18.6%, 21.4% cho sinh viên chưa học.

Nguyên nhân:

```text
v86 dùng Count(StudentModule rows) / total_blocks * 100
```

Với `total_blocks=70`:

- 6 row -> 8.6%
- 13 row -> 18.6%
- 15 row -> 21.4%

Nhưng StudentModule row không đồng nghĩa hoàn thành học. Open edX có thể sinh row container/state rỗng khi render courseware, enroll, sync, hoặc interaction kỹ thuật.

## Rule v87

StudentModule fallback chỉ tính activity row thật:

- Loại container: `course`, `chapter`, `sequential`, `vertical`, `library_content`.
- Loại state rỗng: `{}`, `[]`, `null`, empty.
- Chỉ tính khi có activity: answer/submission/correct_map/attempt/grade/video position/watched...

Connector diagnostics có:

- `connector_version=25.9.16.5.87`
- `student_module_progress_rule=activity_rows_only_excluding_empty_container_rows`
- `student_module_raw_rows`
- `student_module_activity_blocks`
- `student_module_ignored_rows`

## Việc cần làm sau deploy

1. Restart LMS/CMS để tránh cache connector cũ.
2. Verify import `CONNECTOR_VERSION=25.9.16.5.87`.
3. Chạy **Cập nhật điểm** ở chi tiết lớp.
4. Kiểm tra sinh viên chưa học không còn baseline 21.4%.

## Nghiệp vụ vẫn giữ

- **Đồng bộ full CMS**: user + enroll + progress/grade.
- **Cập nhật điểm**: chỉ progress/grade, không tạo user, không enroll.
