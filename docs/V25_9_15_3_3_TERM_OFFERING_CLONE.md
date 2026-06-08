> Lưu ý: bản v25.9.15.3.4 đã sửa wording: DOM123_SP25/SU25/FA25 là các phiên bản trực tiếp của môn DOM123, không có tầng container trung gian. Xem `V25_9_15_3_4_SUBJECT_VERSION_TREE_CORRECTION.md`.

# v25.9.15.3.3 - Term Offering Codes + Clone Subject Term (superseded by v25.9.15.3.4 wording)

## Chốt nghiệp vụ

`phiên bản môn` là version triển khai của một môn trong một kỳ học. FPT có 3 kỳ chuẩn mỗi năm:

- `SPyy` = Spring / Xuân, ví dụ `SP25` = Spring 2025
- `SUyy` = Summer / Hè, ví dụ `SU26` = Summer 2026
- `FAyy` = Fall / Fall/Đông, ví dụ `FA27` = Fall 2027

Cấu trúc UI/chức năng chính:

```text
Bộ môn
└── Môn
    └── Phiên bản môn: DOM123_SP25 / DOM123_SU26 / DOM123_FA27
        └── Bài 1, Bài 2, Bài 3
            └── Bank Version / Release
```

Concept và Family vẫn là metadata lõi của câu hỏi; chúng không phải tầng điều hướng chính.

## Clone phiên bản môn

Có thể tạo phiên bản môn mới bằng cách clone từ phiên bản môn khác để không phải upload lại tài liệu và không phải tạo lại các bài.

Ví dụ:

```text
DOM123_SP25
├── Bài 1
├── Bài 2
└── Bài 3

Clone sang DOM123_SU25
├── Bài 1   (bản ghi mới)
├── Bài 2   (bản ghi mới)
└── Bài 3   (bản ghi mới)
```

Clone tạo bản ghi mới cho:

- Subject Version / phiên bản môn
- Chapter / bài
- Bank Version
- Material Version
- Material Chunk
- Concept Version
- Question Family
- Approved Questions dùng lại được

Không clone Open edX Library/component ID. Release mới của phiên bản môn mới vẫn phải publish sang Library riêng theo nguyên tắc:

```text
1 Bank Release = 1 Open edX Library
```

## Carry-over câu hỏi khi clone kỳ

Câu approved/published dùng lại được sẽ được clone sang phiên bản môn mới và giữ trạng thái:

```text
status = approved
previous_question_id = câu nguồn
is_carry_over = true
openedx_library_problem_id = null
```

Câu không được clone thì không xuất hiện trong version mới. Không sửa câu hỏi ở kỳ cũ.

## API

`POST /api/question-bank-v2/subject-offerings`

Payload tạo kỳ trống:

```json
{
  "subject_id": "...",
  "term": "SP25"
}
```

Payload clone kỳ:

```json
{
  "subject_id": "...",
  "term": "SU25",
  "clone_from_offering_id": "...",
  "clone_chapters": true,
  "clone_materials": true,
  "clone_questions": true
}
```

Backend tự sinh `code`, ví dụ `DOM123_SU25`.

## Test

Đã thêm test kiểm tra:

- Normalize `SP25/SU26/FA27`
- Clone phiên bản môn tạo bản ghi mới cho chapter/material/chunk/question
- Question clone được approved luôn
- Question clone không giữ Open edX Library component cũ
