# v25.9.16.7.2.37 — Analytics Class Result Doctor + Production Readiness Repair

## Mục tiêu

Bản .37 xử lý trực tiếp trạng thái production readiness chưa sẵn sàng và lỗi vận hành kiểu `0/15 SV có kết quả` trong `/analytics/learning`. Thay vì chỉ hiện số 0, UI/API giờ bóc tách rõ lớp đang thiếu ở tầng roster, mapping Course CMS, tracking event, progress, job recalculate hay behavior snapshot.

## Thay đổi chính

1. Thêm backend class result doctor cho `/analytics/classes/{class_id}/doctor`.
2. Thêm action an toàn `/analytics/classes/{class_id}/doctor/recalculate` để enqueue job tính lại lớp, không chạy trực tiếp trong request.
3. `behavior_summary` và `behavior_rows` trả kèm `diagnostics`.
4. Result page thêm panel **Trạng thái dữ liệu lớp**: Roster AP, Snapshot, thiếu snapshot, Course CMS, event đã ingest, user có event, video/session progress.
5. Enrich snapshot rows bằng `student_code/full_name` từ roster AP khi có.
6. Không migration mới; không tạo bảng mới.

## Production safety

- Không recalculate toàn kỳ.
- Không tạo job theo từng sinh viên.
- Không tự chọn mapping nếu ambiguous.
- Không đọc raw tracking.log từ dashboard.
- Chỉ dùng nhãn mềm, không kết luận vi phạm.
