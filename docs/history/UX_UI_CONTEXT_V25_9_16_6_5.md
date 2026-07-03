# UX/UI Context v25.9.16.6.5

## Trọng tâm

Bản này bổ sung chi tiết học online theo Bài/Session và Deadline trong modal sinh viên, không làm UI lớn mới.

## Nguyên tắc hiển thị

- Deadline ưu tiên lấy từ Quiz deadline đã có.
- Không hiện “Cần chỉnh deadline tay” nếu Quiz đã có deadline.
- Deadline suy luận 6 tuần chỉ dùng khi thiếu deadline thật.
- Kết quả chỉ là tín hiệu hỗ trợ giáo viên/quản lý kiểm tra.
- Không kết luận vi phạm.

## Modal Chi tiết học online

Có thêm khu vực:

```text
Theo Bài / Deadline
```

Mỗi tuần hiển thị các Bài thuộc tuần đó. Mỗi Bài hiển thị:

- Video hoàn thành / tổng video
- Hoàn thành TB
- Thời gian xem
- Quiz cuối Bài
- Deadline
- Nguồn deadline
- Trạng thái mềm

## Nhãn mềm

```text
Có dấu hiệu học thật
Có khả năng treo máy
Dấu hiệu bất thường cần kiểm tra
Chưa đủ dữ liệu
Chưa thấy bất thường rõ
```

## Không dùng từ cấm trên UI

```text
gian lận
cheating
không học thật
treo máy chắc chắn
vi phạm chắc chắn
```

## Bước tiếp theo

v25.9.16.6.6 — Analytics Learning Dashboard + Export CSV + Audit polish.
