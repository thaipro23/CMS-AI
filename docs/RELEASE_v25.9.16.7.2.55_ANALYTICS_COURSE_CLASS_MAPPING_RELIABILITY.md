# v25.9.16.7.2.64.12 — Analytics Course/Class Mapping Reliability

Bản này tiếp tục từ `.54` và tập trung vào độ tin cậy mapping `course_id` Open edX → lớp AP trước khi mở rộng analytics/pilot.

## Thay đổi chính

1. Thêm endpoint read-only:

```text
GET /api/analytics/ops/course-class-mapping
```

2. Báo cáo phân loại từng lớp:

```text
READY
NO_ROSTER
NO_COURSE_MAPPING
AMBIGUOUS_MAPPING
MAPPED_NO_EVENTS
MAPPED_HAS_ACTIVITY_NO_SNAPSHOT
PARTIAL_SNAPSHOT
```

3. Báo cáo course có tracking event nhưng chưa resolve được class:

```text
courses_with_events_without_class_mapping
```

4. `/analytics/learning` có panel mới:

```text
Độ tin cậy mapping Course/Lớp
```

5. Thêm script xuất báo cáo:

```text
scripts/analytics-course-class-mapping-report.sh
```

## Chính sách an toàn

- Không tạo/sửa/xóa mapping.
- Không enqueue job.
- Không recalculate trong request.
- Không đọc raw tracking.log.
- Không kết luận hành vi cá nhân.

## Migration

Không có migration mới. Latest vẫn là:

```text
0052_v25_9_16_7_2_27_learning_behavior_logic_calibration.py
```
