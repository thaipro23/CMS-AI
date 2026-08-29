# UX/UI Context v25.9.16.7.1

## Màn Học online

Thêm khối `Production acceptance` ở `/analytics/learning` để quản trị biết module Học online đã đủ điều kiện production production hay chưa.

Trạng thái hiển thị:

- `Production đạt`
- `Production đạt có cảnh báo`
- `Production chưa đạt`

## Bảng production

Hiển thị tối đa 3 lớp production:

- Lớp production
- Trạng thái
- Sinh viên
- Snapshot
- Session
- Video
- Việc cần làm

## Nguyên tắc nội dung

Không dùng từ kết luận vi phạm. Mọi nội dung vẫn theo hướng:

- dấu hiệu
- cần kiểm tra
- giáo viên/quản lý xác minh
- chưa đủ dữ liệu

## Không thay đổi layout chính

- Không đổi bảng sinh viên.
- Không đổi drawer chi tiết học online.
- Không đổi màu trạng thái hiện tại.
- Không đổi Course completion.

---

# v25.9.16.7.1 UX/UI — Rollout + Monitoring

Màn `/analytics/learning` có thêm 2 trạng thái vận hành:

- `Rollout`: Đang tắt / Mở production / Mở production, số lớp trong phạm vi rollout.
- `Monitoring`: Ổn định / Có cảnh báo / Có blocker, số job treo và snapshot cũ.

UI vẫn giữ nguyên nguyên tắc an toàn:

- Không dùng từ “gian lận”, “cheating”, “vi phạm chắc chắn”.
- Chỉ hiển thị nhãn mềm như “Dấu hiệu bất thường cần kiểm tra”.
- Các cảnh báo rollout/monitoring là cảnh báo vận hành, không phải nhận định về sinh viên.
