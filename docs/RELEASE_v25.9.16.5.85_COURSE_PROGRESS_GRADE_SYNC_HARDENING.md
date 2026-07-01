# v25.9.16.5.85 — Course Progress / Grade Sync Hardening

## Mục tiêu

Làm chắc luồng **Cập nhật điểm CMS** và phần hiển thị Course completion/grade để tránh hiểu sai dữ liệu Open edX:

- `Đồng bộ full CMS` vẫn chạy đủ: check/tạo user CMS → enroll Course CMS → lấy Course completion/grade/detailed grades.
- `Cập nhật điểm` chỉ đọc dữ liệu học tập từ Open edX Connector; không tạo user, không enroll.
- Course completion chỉ lấy từ source official như Course Home Progress/completion_summary. Nếu connector không trả source official thì giữ N/A, không đoán từ quiz/grade.
- UI hiển thị chẩn đoán vì sao progress/grade/detailed grades N/A.

## Thay đổi backend

- `sync_class_learning_insight()` không còn auto gọi `sync_class_course_enrollment()`.
- `OpenEdXConnectorClient.class_analytics_payload()` giữ lại `learning_counts` và `diagnostics` từ plugin thay vì chỉ trả list rows.
- Learning sync trả thêm `connector_counts` và `connector_diagnostics`.
- Learning summary trả thêm:
  - `diagnostic_counts`
  - `source_counts`
  - `diagnostic_note`
- Student row trả thêm:
  - `learning_progress_source`
  - `learning_sync_note`
  - `learning_diagnostics`
- Snapshot lưu `learning_diagnostics` trong `raw_json` để debug sau đồng bộ.

## Thay đổi frontend

- Màn chi tiết lớp hiển thị box **Chẩn đoán điểm CMS**:
  - số SV có progress official
  - số SV có điểm tổng
  - số SV có điểm thành phần
  - source progress chính
- Mỗi dòng SV hiển thị source progress và note chẩn đoán ngắn.
- Message sau **Cập nhật điểm** ghi rõ progress/grade/component/missing result và khẳng định không tạo user/enroll.

## Kiểm tra

```bash
python3 -m compileall -q backend/app
DATABASE_URL=sqlite+pysqlite:///:memory: pytest -q backend/app/tests/test_training_policy_service.py backend/app/tests/test_v25_9_16_5_73_course_home_route_progress.py backend/app/tests/test_v25_9_16_5_75_training_management_scale.py
npm --prefix frontend run typecheck
```
