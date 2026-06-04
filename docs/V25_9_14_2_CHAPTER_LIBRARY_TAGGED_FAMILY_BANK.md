# v25.9.14.2 - Chapter Library + Tagged Family Bank Export

## Mục tiêu

- Không tạo Library theo EASY/MEDIUM/HARD nữa.
- Mỗi chapter/bài chỉ có một Open edX Library, ví dụ `MUL211 - Bài 2`.
- Component được quản lý bằng tag chuẩn: `course:MUL211`, `chapter:Bài 2`, `family:<tên dễ đọc>`, `difficulty:EASY/MEDIUM/HARD`, `ai-learning-check`, `generated`.
- AI Server tạo kế hoạch Family Slot Problem Bank để giáo viên sửa rồi publish.

## Soft mode

Nếu family ít hơn số slot cần tạo, AI Server vẫn tạo đủ slot bằng cách lặp family mạnh nhất nhưng gắn cảnh báo.

Nếu family nhiều hơn số slot cần tạo, AI Server có thể gộp tối đa 2 family vào cùng một Problem Bank slot. Slot đó vẫn random 1 component, nhưng có nhiều lựa chọn hơn và giảm số block giáo viên phải quản lý.

## Endpoint mới

```http
POST /api/publish/courses/{course_id}/family-bank-plan/preview
POST /api/publish/courses/{course_id}/family-bank-plan/publish
```

## Ghi chú

Bản này publish các variants trong kế hoạch vào Chapter Library. Bước tự tạo node quiz/Problem Bank block trong Studio sẽ là bản sau, vì cần xác nhận block type/API của Open edX Ulmo/Verawood.
