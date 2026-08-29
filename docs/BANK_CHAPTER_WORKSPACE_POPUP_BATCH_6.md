# Bank Chapter Workspace & Popup Redesign — Batch 6

## Phạm vi

Áp dụng cho route:

```text
/bank/chapters/{chapterId}
```

Tiếp tục trực tiếp từ Batch 5.

## Thay đổi giao diện

### 1. Đồng bộ cấu trúc trang Bài học với hierarchy Bank

- Thêm phần intro cùng pattern với:
  - `/bank/departments`
  - `/bank/departments/{id}/subjects`
  - `/bank/subjects/{id}/versions`
  - `/bank/subject-versions/{id}/chapters`
- Dùng cùng nền workspace, border, radius, shadow và nhịp spacing.
- Thanh hành động bài học chuyển sang `bank-hierarchy-panel`.
- Khu vực danh sách câu hỏi chuyển sang một panel thống nhất, không còn card/workspace lồng nhau.

### 2. Hành vi nút Duyệt câu hỏi

- Không chuyển tab hoặc route khác.
- Khi bấm:
  - ưu tiên lọc `Chờ duyệt` nếu còn câu chờ duyệt;
  - sắp xếp `Cần xử lý trước`;
  - đưa về trang 1;
  - cuộn mượt xuống khu vực danh sách câu hỏi;
  - giữ URL state hiện tại.

### 3. Popup Duyệt câu hỏi

- Thiết kế lại theo ảnh đã chốt.
- Header gọn, title và mô tả rõ.
- Badge trạng thái/độ khó/chất lượng nằm trong dải metadata riêng.
- Đáp án hiển thị 2 x 2 trên desktop, 1 cột trên mobile.
- Đáp án đúng dùng nền xanh nhạt và ký hiệu nổi bật.
- Giải thích, bằng chứng và metadata có hierarchy rõ.
- Footer tách navigation trái, action phải, keyboard shortcut ở giữa phía dưới.

### 4. Popup Tạo câu hỏi từ tài liệu

- Thiết kế lại thành 2 cột:
  - trái: kế hoạch, quota, nguồn tài liệu, số câu dự kiến, tỷ lệ độ khó;
  - phải: form cấu hình số câu và tỷ lệ.
- Thêm vòng tiến độ quota.
- Input phần trăm có suffix `%` tách riêng, không chồng khung.
- Validation tỷ lệ nằm trong notice rõ ràng.
- Footer cố định với `Đóng` và `Tính chi phí & tạo`.
- Responsive chuyển một cột trên tablet/mobile.

## File đã sửa

```text
frontend/app/bank/_components/pages/ChapterWorkspacePage.tsx
frontend/styles/bank-redesign-batch-one.css
```

## Nghiệp vụ giữ nguyên

- Không đổi route.
- Không đổi API contract.
- Không đổi RBAC.
- Không đổi generation/review/release semantics.
- Không đổi server-side pagination/filter/sort và URL state.

## Verification

Không chạy TypeScript check, lint, test, build hoặc browser smoke test theo yêu cầu của người dùng.
