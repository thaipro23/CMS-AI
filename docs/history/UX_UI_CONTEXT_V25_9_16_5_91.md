# Context v25.9.16.5.91 — Class Detail Cleanup + Fast Learning Sync

## Nền trước đó

v90 đã sửa đúng Course completion fallback:

```text
completed_blocks = số StudentModule sequential có state.position > 0
total_blocks = số reachable sequential/subsection
```

Case đã xác minh:

```text
duongddph69321 = 5/8 = 62.5% ≈ 63%
tienpdph69628 chỉ có itembank rows => 0/8 = 0%
```

## v91 thay đổi chính

### Hiệu năng

AI Server gọi connector `class-analytics` với:

```json
{
  "compact": true,
  "include_diagnostics": false,
  "skip_course_home_progress": true
}
```

Connector không còn gọi Course Home Progress route theo từng sinh viên trong hot path cập nhật điểm. Connector chỉ dùng đường nhanh:

```python
StudentModule.objects.filter(
    course_id=course_key,
    student_id__in=user_ids,
    module_type='sequential',
).values('student_id', 'module_state_key', 'state', 'modified')
```

Không query BlockCompletion cho fallback. Không dùng `itembank/problem/video` để tính Course completion.

### Payload gọn hơn

Connector compact progress chỉ trả các field cần lưu:

```text
percent
source
completed_blocks
total_blocks
last_activity_at
has_student_module_fallback
student_module_completed_blocks
student_module_activity_blocks
student_module_raw_rows
student_module_ignored_rows
student_module_subsection_total
student_module_fallback_mode
student_module_fallback_rule
student_module_denominator_rule
fallback_reason
```

Không trả breakdown/sample cây course trong response mặc định.

### UI chi tiết lớp

Đã bỏ:

```text
Luồng: Môn → Lớp → Chi tiết lớp
Luồng: Giáo viên → Lớp → Chi tiết lớp
Chạy đủ luồng: kiểm tra/tạo tài khoản CMS...
Chẩn đoán điểm CMS
Nguồn: StudentModule fallback / Course Home official
learning_sync_note dài trong từng dòng sinh viên
hint kéo ngang dài phía trên bảng
```

Giữ lại các thông tin vận hành cần thiết:

```text
Đồng bộ full CMS
Cập nhật điểm
Tổng SV AP
Đã đồng bộ CMS
Đã enroll
Đã vào học
Course completion TB
Điểm tổng TB
Danh sách sinh viên
Các đầu điểm CMS
```

## Lưu ý vận hành

Sau khi deploy connector phải restart:

```bash
tutor local restart lms cms lms-worker cms-worker
```

Connector version cần là:

```text
25.9.16.5.91
```
