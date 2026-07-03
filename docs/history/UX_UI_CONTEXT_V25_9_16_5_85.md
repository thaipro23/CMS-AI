# CONTEXT v25.9.16.5.85 — Course Progress / Grade Sync Hardening

Bản mới nhất nên dùng: `v25.9.16.5.85-course-progress-grade-sync-hardening`.

## Quy tắc nghiệp vụ đã chốt

### Đồng bộ full CMS

Nút **Đồng bộ full CMS** vẫn là full flow:

- check/tạo tài khoản CMS
- check/enroll Course CMS
- lấy Course completion
- lấy điểm tổng
- lấy điểm thành phần/detailed grades

### Cập nhật điểm

Nút **Cập nhật điểm** chỉ đọc dữ liệu học tập:

- không tạo tài khoản CMS
- không enroll
- không gán Course Staff
- chỉ gọi Open edX Connector để lấy progress/grade/component scores

Trong v84 có nguy cơ code vẫn auto-enroll theo setting `academic_auto_enroll_after_cms_sync`; v85 đã bỏ nhánh đó khỏi `sync_class_learning_insight()`.

## Course completion

Nguồn đúng cho completion là Open edX Course Home Progress, ưu tiên source:

```text
CourseHomeProgressRoute:completion_summary
```

Nếu connector không trả source official, AI Server phải hiển thị `N/A`, không tự suy luận completion từ:

- quiz score
- detailed grade
- điểm tổng
- số component có điểm

## Backend v85

Đã thêm/đổi:

- `OpenEdXConnectorClient.class_analytics_payload()` giữ lại envelope của connector gồm:
  - `learning_counts`
  - `diagnostics`
  - `results`
- `sync_class_learning_insight()` là read-only, không auto-enroll.
- Learning sync trả thêm:
  - `connector_counts`
  - `connector_diagnostics`
- Learning summary trả thêm:
  - `diagnostic_counts`
  - `source_counts`
  - `diagnostic_note`
- Student row trả thêm:
  - `learning_progress_source`
  - `learning_sync_note`
  - `learning_diagnostics`
- Snapshot lưu `learning_diagnostics` trong `raw_json`.

## Frontend v85

Màn chi tiết lớp có thêm box **Chẩn đoán điểm CMS**:

- Progress official
- Điểm tổng
- Điểm thành phần
- Source chính
- Note chẩn đoán

Từng dòng sinh viên trong cột tiến độ học hiển thị:

- Hoàn thành khóa học
- Điểm tổng
- Source progress
- Note chẩn đoán ngắn
- Trạng thái học tập

## Kiểm tra đã chạy

```bash
python3 -m compileall -q backend/app
DATABASE_URL=sqlite+pysqlite:///:memory: pytest -q backend/app/tests/test_training_policy_service.py backend/app/tests/test_v25_9_16_5_85_learning_sync_hardening.py backend/app/tests/test_v25_9_16_5_73_course_home_route_progress.py backend/app/tests/test_v25_9_16_5_75_training_management_scale.py
npm --prefix frontend run typecheck
npm --prefix frontend run build
```

Kết quả:

- Backend compile: pass
- Tests chọn lọc: 12 passed, 2 skipped
- Frontend typecheck: pass
- Next build: compiled successfully, sau đó sandbox timeout ở bước lint/page processing; cần xác nhận bằng Docker build trên server thật.

## Hướng tiếp theo

Sau v85, nên làm:

```text
v25.9.16.5.86 — Final Test Rule Placeholder + Exam Eligibility Audit
```

Mục tiêu: chuẩn hóa màn điều kiện thi/không được thi nhưng vẫn không hard-code Final test khi chưa có nghiệp vụ chính thức.
