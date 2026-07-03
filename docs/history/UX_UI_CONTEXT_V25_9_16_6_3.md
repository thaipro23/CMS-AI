# UX/UI Context v25.9.16.6.3

Bản này ưu tiên backend core Phase 0–4, chưa polish UI lớn.

## Chính sách hiển thị bắt buộc

Không hiển thị các từ:

```text
cheating
gian lận
không học thật
treo máy chắc chắn
vi phạm chắc chắn
```

Mapping nhãn:

```text
LIKELY_REAL_LEARNING → Có dấu hiệu học thật
POSSIBLE_IDLE → Có khả năng treo máy
POSSIBLE_CHEATING → Dấu hiệu bất thường cần kiểm tra
INSUFFICIENT_DATA → Chưa đủ dữ liệu
NORMAL → Chưa thấy bất thường rõ
```

Disclaimer bắt buộc ở mọi UI/detail/export:

```text
Đây là nhận định dựa trên log hệ thống, không phải kết luận vi phạm. Cần giáo viên/quản lý xác minh trước khi xử lý.
```

## Version sau

v25.9.16.6.4 mới bắt đầu gắn UI tối thiểu vào `/student-management/classes/{classId}`:

- Card/tab `Học online`
- Summary số lượng từng nhóm
- Cột `Nhận định học online`
- Drawer chi tiết theo Bài/Deadline
