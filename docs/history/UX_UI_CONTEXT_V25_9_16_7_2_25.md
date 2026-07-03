# UX/UI Context — v25.9.16.7.2.25

## `/analytics/learning`

Luồng mới:

```text
Môn → Lớp → Xem kết quả
```

Mục tiêu: giáo viên không phải nhìn quá nhiều lớp/kết quả cùng lúc. Mỗi màn chỉ có một nhiệm vụ.

### Màn 1: Môn

- Bộ lọc: Hệ, Học kỳ, Cơ sở, Kết quả.
- Có `Tất cả cơ sở`.
- Bảng môn chỉ hiển thị môn trong phân quyền.
- Bấm `Xem lớp` để sang màn lớp.

### Màn 2: Lớp

- Chỉ hiển thị lớp của môn đã chọn.
- Có summary theo lớp/sinh viên/tín hiệu.
- Bấm `Xem kết quả` để sang màn sinh viên.

### Màn 3: Xem kết quả

- Chỉ hiển thị kết quả sinh viên của lớp đã chọn.
- `STT` + `Sinh viên` vẫn sticky khi cuộn ngang.
- Bấm pill kết quả mới mở drawer lý do.

## RBAC

UI không tự tin vào việc ẩn nút. Backend vẫn là nguồn kiểm soát quyền:

- Subject list dùng API học vụ đã scope.
- Class overview nhận `allowed_class_ids` từ backend.
- Student behavior detail luôn gọi `assert_can_access_class`.
- API trả `permission_scope` để UI nói rõ dữ liệu đã được lọc theo quyền.
