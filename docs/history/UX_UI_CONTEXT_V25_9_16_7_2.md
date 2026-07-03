# UX/UI Context v25.9.16.7.2 — Full Test Rollout Default

## Trạng thái

Học online analytics mặc định chạy chế độ `production` cho môi trường test ít dữ liệu. Điều này chỉ mở phạm vi hiển thị/job cho toàn bộ lớp user có quyền xem; không đổi chính sách nhận định mềm.

## UI chính

- `/analytics/learning`: dashboard tổng hợp Học online.
- `/student-management/classes/{classId}`: card/cột Học online trong chi tiết lớp.
- `/jobs`: nhóm job Học online.
- `/audit`: audit export/xem danh sách cần kiểm tra.

## Rollout

Hiển thị mode:

```text
PRODUCTION
```

Nếu scope campus/class/course để rỗng thì hiểu là bật cho toàn bộ lớp trong phạm vi RBAC.

## Text an toàn bắt buộc

Không dùng từ kết luận vi phạm. Nhãn frontend phải là:

- Có dấu hiệu học thật
- Có khả năng treo máy
- Dấu hiệu bất thường cần kiểm tra
- Chưa đủ dữ liệu
- Chưa thấy bất thường rõ

Disclaimer giữ nguyên:

```text
Đây là nhận định dựa trên log hệ thống, không phải kết luận vi phạm. Cần giáo viên/quản lý xác minh trước khi xử lý.
```

## Production guard vẫn giữ

- Chặn job trùng.
- Giới hạn backfill mỗi lần.
- Giới hạn job active.
- Giới hạn export CSV.
- Monitoring job treo/snapshot stale.
- Dashboard không đọc raw tracking.log trực tiếp.


## Pilot acceptance

Mặc dù rollout mặc định là full trên môi trường test, màn vẫn giữ khối Pilot acceptance để kiểm tra nhanh 1–3 lớp mẫu trước khi tin dữ liệu toàn hệ.
