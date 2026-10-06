# Điểm tổng và kiểm tra tiến độ PP03883

## Cách tính điểm tổng

Mỗi Quiz và Final test thực sự có trong course được quy về thang 10 rồi lấy
trung bình cộng. Bài chưa có điểm tính 0; không dùng trọng số grading của CMS.
Không có Final test thì không thêm Final vào mẫu số. Chưa nhận được danh sách
assessment từ CMS thì điểm tổng là N/A, không tự tạo bài hay suy đoán điểm.
Quiz trùng tên/số chỉ tính một lần; Assignment không tham gia điểm tổng này.

Ví dụ: Quiz 1 = 10/10, Quiz 2 = 6/15 (= 4/10), Final = 4/10 thì điểm tổng
là (10 + 4 + 4) / 3 = 6/10. Với 8 Quiz và Final đều tối đa, điểm tổng là 10/10.

Migration `0073_assessment_average_grade` tính lại điểm đã lưu từ payload CMS
để các bộ lọc SQL và báo cáo dùng cùng công thức. Payload gốc, tiến độ, số nội
dung hoàn thành/tổng và các thời điểm đồng bộ được giữ nguyên.

## Chênh lệch 98%–100%

Đã đối chiếu source: CMS-FPT `fpt-indigo-ui` tại `4a989e1` có connector v105,
nhận `skip_course_home_progress=true` từ CMS-AI và dùng StudentModule fallback.
CMS-AI đã có v106, hiểu `use_official_course_home_progress=true` và đọc trực tiếp
`lms.djangoapps.courseware.courses.get_course_blocks_completion_summary`.
Bản sửa CMS-FPT đưa luồng đọc trực tiếp này sang plugin thực sự được build,
giữ nguyên tối ưu cache và cách chọn primary/replica đang có.

Tiến độ chính thức dùng complete / (complete + incomplete + locked), khớp
CompletionDonutChart của Open edX. Không bỏ locked_count, không suy tiến độ từ
điểm Quiz, không ép giá trị thành 100%. Kết quả chính thức không bị mẫu số
StudentModule ghi đè.

Chưa có bằng chứng runtime của đúng lớp PP03883 để kết luận snapshot cũ hay
fallback là nguyên nhân cụ thể: phiên dashboard hiện yêu cầu đăng nhập.

## Lệnh chỉ đọc trên K8s

Lệnh này hoạt động cả trước khi deploy code mới. Nó liệt kê các snapshot
PP03883 và đọc lại primary cho các lớp có tiến độ làm tròn là 98%.
Không tạo user, enroll, ghi điểm hoặc sửa snapshot.

```bash
ACMS_POD=$(kubectl -n openedx get pods -o name | awk '/ai.*backend/ {print; exit}')
kubectl -n openedx exec -i "$ACMS_POD" -- python - <<'PY'
import json
from app.db.session import SessionLocal
from app.models.academic import AcademicStudent, AcademicClass, AcademicStudentLearningSnapshot
from app.services.academic_service import AcademicService
from app.services.openedx_student_insight import OpenEdXConnectorClient

with SessionLocal() as db:
    service = AcademicService(db)
    rows = db.query(AcademicStudentLearningSnapshot, AcademicClass).join(
        AcademicStudent, AcademicStudent.id == AcademicStudentLearningSnapshot.student_id
    ).join(
        AcademicClass, AcademicClass.id == AcademicStudentLearningSnapshot.class_id
    ).filter(AcademicStudent.student_code == "PP03883").all()
    for snap, cls in rows:
        payload = service._payload_from_snapshot(snap)
        record = {
            "class_id": cls.id, "class_code": cls.class_code,
            "course_id": snap.openedx_course_id,
            "cached_percent": snap.progress_percent,
            "progress_source": service._snapshot_progress_source(snap),
            "completed_blocks": snap.completed_blocks,
            "total_blocks": snap.total_blocks,
            "learning_synced_at": snap.learning_synced_at,
            "last_activity_at": snap.last_activity_at,
            "progress_payload": payload.get("progress"),
        }
        if snap.progress_percent is not None and round(snap.progress_percent) == 98:
            try:
                live = OpenEdXConnectorClient().class_analytics_payload(
                    course_id=snap.openedx_course_id,
                    students=[{"username": "PP03883", "student_code": "PP03883"}],
                    read_consistency="primary_after_enrollment",
                )
                record["live"] = {
                    "connector_version": live.get("connector_version"),
                    "read_consistency": live.get("read_consistency"),
                    "results": live.get("results"),
                }
            except Exception as exc:
                record["live_error"] = str(exc)
        print(json.dumps(record, ensure_ascii=False, default=str))
PY
```

Đối chiếu đúng class_id/course_id đang mở trên dashboard. Nếu cache là 98%
nhưng live chính thức là 100%, cần cập nhật snapshot. Nếu live còn là
StudentModule fallback hoặc connector v105, kiểm tra image LMS đã triển khai
plugin mới chưa. Nếu nguồn chính thức và primary vẫn khác màn hình CMS,
đối chiếu cùng course và cùng username trước khi sửa dữ liệu.

## Áp dụng

1. Build/deploy CMS-AI backend, worker và frontend; chạy migration lên 0073
   bằng image backend mới trước khi chuyển traffic sang bản mới.
2. Build/deploy image Open edX từ CMS-FPT có connector v106 để nhận API completion
   chính thức. Thay đổi plugin Python không yêu cầu build lại MFE.
3. Chạy Cập nhật điểm cho lớp sau khi cả hai bên được deploy, hoặc chờ pipeline
   hằng ngày. Chạy lại lệnh chỉ đọc để xác minh source, counts và thời điểm.

Lệnh migration khi pod backend đang dùng image mới:

```bash
kubectl -n openedx exec -i "$ACMS_POD" -- sh -c 'cd /app && alembic upgrade head'
```

Nếu pipeline deploy có migration Job riêng thì để Job đó chạy bằng image mới;
không cần chạy thêm lệnh migration thủ công.
