# Batch 29 — AP Teacher Limited Staff Policy

## Mục tiêu

Khi Full CMS đồng bộ giảng viên từ AP vào Course Open edX, AI Server chỉ cấp vai trò `Limited Staff` ở cấp khóa học.

## Chính sách mới

- Giảng viên AP mới: cấp `CourseLimitedStaffRole` (`limited_staff`).
- Giảng viên AP đã có `Limited Staff`: giữ nguyên, không tạo bản ghi trùng.
- Giảng viên AP từng được các batch cũ cấp `CourseStaffRole` (`staff`): cấp `Limited Staff` trước, xác minh, sau đó gỡ đúng role `staff` ở Course đó.
- Không cấp `CourseInstructorRole`, không cấp global `is_staff`, không cấp `is_superuser`.
- Không tự động hạ quyền global hoặc quyền Course Admin được cấp thủ công ngoài luồng AP sync.

`Limited Staff` kế thừa các quyền vận hành Staff trên LMS nhưng không có quyền chỉnh sửa nội dung trong Studio.

## Trạng thái connector

- `course_limited_staff_added`
- `already_course_limited_staff`
- `course_limited_staff_migrated`
- `course_limited_staff_not_verified`
- `course_limited_staff_policy_not_verified`
- `course_limited_staff_failed`

Response thành công dùng:

```json
{
  "course_role": "limited_staff",
  "enrollment_status": "course_limited_staff",
  "verified_after_write": true,
  "removed_course_staff": true,
  "full_course_staff_remaining": false
}
```

## Idempotence và an toàn

Connector kiểm tra role chính xác bằng `users_with_role()` thay vì `CourseStaffRole.has_user()`. Lý do: `Limited Staff` kế thừa quyền Staff nên `CourseStaffRole.has_user()` có thể trả `true` cho người chỉ có `limited_staff`.

Thứ tự downgrade:

1. Cấp `limited_staff`.
2. Xác minh role chính xác.
3. Gỡ role `staff` cũ.
4. Xác minh `limited_staff=true` và `staff=false`.
5. Chỉ trả thành công khi `verified_after_write=true`.

## Thành phần triển khai

- `openedx-connector-plugin` trên LMS.
- AI Server `backend` và các worker dùng cùng image backend.

Không sửa frontend, Learning MFE, unit-reset plugin hoặc database schema.
