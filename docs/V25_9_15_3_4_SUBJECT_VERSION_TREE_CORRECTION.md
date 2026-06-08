# v25.9.15.3.4 - Subject Version Tree Correction

## Chốt lại cây nghiệp vụ

`DOM123_SP25`, `DOM123_SU25`, `DOM123_FA25` là **các phiên bản của môn DOM123 theo kỳ học**. Chúng nằm trực tiếp dưới `Môn`, không có thêm một tầng container trung gian.

```text
Bộ môn
└── Môn: DOM123
    ├── DOM123_SP25     # version/kỳ Spring 2025 của DOM123
    │   ├── Bài 1
    │   ├── Bài 2
    │   └── Bài 3
    │       └── Bank Version / Release
    │
    ├── DOM123_SU25     # version/kỳ Summer 2025 của DOM123
    │   ├── Bài 1
    │   ├── Bài 2
    │   └── Bài 3
    │       └── Bank Version / Release
    │
    └── DOM123_FA25     # version/kỳ Fall 2025 của DOM123
        ├── Bài 1
        ├── Bài 2
        └── Bài 3
            └── Bank Version / Release
```

Trong database vẫn dùng bảng `ai_subject_offerings` để lưu các bản như `DOM123_SP25`, nhưng trong UI và docs gọi là **Phiên bản môn**.

## Quy tắc kỳ

FPT có 3 kỳ trong một năm:

- `SPyy` = Spring / Xuân, ví dụ `SP25` = Spring 2025
- `SUyy` = Summer / Hè, ví dụ `SU26` = Summer 2026
- `FAyy` = Fall / Fall/Đông, ví dụ `FA27` = Fall 2027

Backend tự chuẩn hóa `term` và tự sinh code:

```text
subject.code = DOM123
term = SU25
=> subject version code = DOM123_SU25
```

## Clone phiên bản môn

Có thể clone `DOM123_SP25` sang `DOM123_SU25` để không phải upload lại tài liệu, không phải tạo lại Bài 1/Bài 2/Bài 3 và không phải sinh lại các câu đã dùng lại được.

Clone luôn tạo **bản ghi mới** cho:

- Phiên bản môn đích
- Chapter/Bài
- Bank Version
- Material Version
- Material Chunk
- Concept Version
- Question Family
- Approved Questions dùng lại được

Không dùng chung ID giữa hai phiên bản môn.

## Câu hỏi khi clone

Câu dùng lại được:

```text
Q1 ở DOM123_SP25
→ clone thành Q1 mới ở DOM123_SU25
→ previous_question_id = Q1_SP25
→ status = approved
→ is_carry_over = true
```

Câu không còn dùng lại được:

```text
Không clone sang phiên bản môn mới
Không tạo retired snapshot
Không sửa câu hỏi ở phiên bản môn cũ
```

## Concept và Family

Concept và Question Family là metadata lõi gắn với câu hỏi để chống trùng gốc nội dung và lập Problem Bank. Chúng không phải tầng điều hướng chính trong UI.

UI chính chỉ nên cho người dùng nhìn theo cây:

```text
Bộ môn → Môn → DOM123_SP25/SU25/FA25 → Bài → Bank Version / Release
```

## API

Endpoint cũ vẫn giữ để tương thích:

```http
GET  /api/question-bank-v2/subject-offerings
POST /api/question-bank-v2/subject-offerings
```

Endpoint mới dễ hiểu hơn:

```http
GET  /api/question-bank-v2/subject-versions
POST /api/question-bank-v2/subject-versions
```

Cả hai endpoint đều thao tác cùng bảng `ai_subject_offerings`.
