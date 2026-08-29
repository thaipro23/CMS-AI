# UX/UI + Technical Context — v25.9.16.5.94

## Mục tiêu

Bản v94 không đổi nhiều UI. Trọng tâm là rà rule điều kiện quiz/deadline và giảm tính toán thừa ở màn chi tiết lớp.

## Rule nghiệp vụ đang khóa

### Course completion

Dựa theo dữ liệu thực tế đã debug:

- Course `course-v1:FPT+COM1071+SU26` có 8 sequential/subsection.
- `duongddph69321` có 5 StudentModule `sequential` có state position.
- Kết quả đúng: `5/8 = 62.5% ≈ 63%`.
- Sinh viên chỉ có row `itembank` phải là `0/8`, không được tính completion.

Rule:

```text
Course completion fallback = số StudentModule sequential có position / tổng reachable sequential
```

Không tính:

```text
itembank
problem
video
raw non-container block count
```

### Quiz eligibility

Rule:

```text
Quiz phải đạt 100%
Quiz phải làm/nộp không sau deadline
Deadline lấy từ /semesters khi có cấu hình tuần học
Không dùng ngưỡng 50/80
Final test chưa áp dụng rule chính thức
```

Điểm sửa ở v94:

```text
Quiz percent < 100 => Không được thi
```

Không yêu cầu phải có `submitted_at` để kết luận chưa đạt 100%, vì riêng điểm thấp đã đủ chặn.

Riêng:

```text
Quiz percent = 100 nhưng thiếu submitted_at => Chưa đủ dữ liệu
```

vì chưa thể biết có làm sau deadline không.

## Hiệu năng class detail

Trước v94, mỗi sinh viên có thể khiến backend tính lại deadline schedule từ component list.

v94 đổi thành:

```text
gom component scores của page hiện tại
build quiz schedule 1 lần
pass schedule vào từng student row
```

Điều này giảm CPU và DB/block lookup ở `/student-management/classes/{classId}`.

## UI hiện tại cần giữ

Trong cột `Tiến độ học`, chỉ hiển thị:

```text
Hoàn thành khóa học: ...
Điểm tổng: ...
Điểm thấp / Đang học / Chưa vào học / ...
```

Không hiện text kỹ thuật:

```text
source/fallback/connector/diagnostics
```

Chỉ dùng `?debug=1` cho thông tin kỹ thuật nếu cần.

## Version

- Frontend footer: `v25.9.16.5.94`
- Connector version: `CONNECTOR_VERSION = 25.9.16.5.94`
- Training policy version: `v25.9.16.5.94`
