# UX/UI Context v25.9.16.7.2.14

## Vấn đề

Người dùng thấy `/student-management` và `/teacher-management` lệch số rất lớn.

Thực tế query DB cho thấy dữ liệu cùng scope đang khớp:

- Student unique classes: 606
- Student class-student rows: 20119
- Teacher class assignment rows: 606
- Teacher student workload rows: 20119

Lệch là do UX cũ: `/student-management` KPI chỉ cộng các môn trong trang hiện tại, còn `/teacher-management` sau rebuild cache đọc tổng toàn bộ bộ lọc.

## Nguyên tắc mới

- KPI trên card phải là tổng theo bộ lọc, không phải theo page, trừ khi label ghi rõ.
- Dữ liệu phân trang chỉ dùng cho bảng.
- Header phải nói rõ ngữ cảnh:
  - Student: theo môn/lớp/sinh viên trong bộ lọc.
  - Teacher: theo phân công giảng viên.

## Label mới

### `/student-management`

- `Môn theo bộ lọc`
- `Lớp theo bộ lọc`
- `Sinh viên theo bộ lọc`
- `Course CMS đã map`
- `Cảnh báo theo bộ lọc`

### `/teacher-management`

- `Báo cáo giảng viên theo phân công`
- `GV theo bộ lọc`
- `Lượt lớp phân công`
- `Lượt SV theo phân công`

## Backend contract

`GET /api/academic/teacher/subjects` trả thêm:

```json
{
  "summary": {
    "subject_count": 109,
    "class_count": 606,
    "student_count": 20119,
    "course_mapped_count": 0,
    "alert_subject_count": 50,
    "scope_label": "Toàn bộ bộ lọc"
  }
}
```
