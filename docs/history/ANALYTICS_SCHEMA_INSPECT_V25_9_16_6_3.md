# v25.9.16.6.3 — Learning Behavior Analytics / Aspects-lite Schema Inspect

## Kết luận Phase 0

Đã rà codebase hiện tại và chọn hướng **tái sử dụng tối đa schema đang có**. Không tạo hệ thống bảng song song cho class/student/course/job/audit/RBAC.

## Bảng/model dùng lại

| Nhóm | Bảng/model dùng lại | Mục đích |
|---|---|---|
| Lớp / sinh viên | `academic_classes`, `academic_class_students`, `academic_students` | mapping lớp → sinh viên |
| Giáo viên | `academic_teachers`, `academic_teacher_assignments` | teacher → class |
| Course mapping | `academic_class_course_mappings`, `academic_course_mappings` | class/subject/term → Open edX course_id |
| Học kỳ / deadline | `academic_terms`, `academic_blocks`, `academic_quiz_deadline_overrides` | source deadline từ `/semesters` và override thủ công |
| Progress CMS | `academic_student_learning_snapshots` | Course completion/grade hiện có, không thay thế |
| Job | `academic_class_sync_jobs`, `academic_sync_runs` | giữ pattern job hiện có, không tạo job table chung mới |
| Audit | `ai_audit_logs` | ghi audit các hành động nhạy cảm ở phase UI/export |
| RBAC | `BusinessRBACService`, `require_permission` | tái sử dụng phân quyền hiện có |

## Bảng mới tối thiểu

Chỉ bổ sung các bảng thật sự thiếu để analytics không phải đọc raw log mỗi request:

| Bảng mới | Lý do |
|---|---|
| `analytics_ingest_checkpoints` | lưu offset/inode/status để ingest incremental, không scan full `tracking.log` |
| `analytics_tracking_events` | lưu event đã normalize, chống trùng bằng `raw_line_hash` |
| `analytics_course_sessions` | snapshot Course → Bài/Session → Video/Quiz/Deadline |
| `analytics_student_video_progress` | snapshot video progress để dashboard đọc nhanh |
| `analytics_student_session_progress` | snapshot tiến độ theo Bài/Session |
| `analytics_learning_behavior_snapshots` | snapshot nhận định mềm theo sinh viên/lớp/course |

Không drop/rename bảng cũ. Migration backward-compatible, chỉ create table + index.

## Mapping nghiệp vụ

- `class_id → course_id`: ưu tiên `academic_class_course_mappings`, sau đó `academic_course_mappings` theo subject/term/block/campus.
- `student → class`: `academic_class_students` + `academic_students`.
- `teacher → class`: `academic_teacher_assignments`.
- `course → subject/version/semester/campus`: `academic_classes`, `academic_subjects`, `academic_terms`, `academic_blocks`, `academic_course_mappings`.
- `course → Bài/Session → video/quiz`: adapter `build_session_mappings_from_blocks(...)`, dùng course blocks đã sync hoặc payload rebuild.
- `deadline`: manual `/semesters`/override trước, nếu thiếu thì infer 6 tuần theo thứ tự session.

## Nhãn an toàn

Backend vẫn giữ enum kỹ thuật `POSSIBLE_CHEATING` cho scoring, nhưng API/UI phải render thành:

```text
Dấu hiệu bất thường cần kiểm tra
```

Không được render: `cheating`, `gian lận`, `không học thật`, `vi phạm chắc chắn`, `treo máy chắc chắn`.
