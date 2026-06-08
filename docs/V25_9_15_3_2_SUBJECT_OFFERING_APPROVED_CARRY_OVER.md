# v25.9.15.3.2 — Subject Offering Version Isolation + Approved Carry-over

## Chốt thiết kế mới

Cấu trúc nghiệp vụ:

```text
Bộ môn
└── Môn
    └── Môn_su / kỳ triển khai / version
        └── Bài 1, Bài 2, Bài 3
            └── Bank Version / Release
```

`môn_su/kỳ triển khai` là lớp version của môn. `Concept` và `Family` không phải tầng điều hướng UI; chúng là metadata lõi thuộc câu hỏi để chống trùng gốc nội dung và lập Problem Bank.

## Quy tắc version isolation

- v1 và v2 là hai snapshot riêng biệt.
- Không sửa đè câu hỏi của v1.
- Câu dùng lại được từ v1 sang v2 được clone thành câu mới trong v2.
- Câu clone carry-over được `approved` luôn.
- Câu không còn dùng được thì không clone vào v2.
- Không tạo retired snapshot ở v2 cho câu không dùng lại.
- Nếu câu đã tồn tại trong chính v2 và bị loại, chỉ khi đó mới mark retired trong v2.

## Database/API

Thêm bảng:

```text
ai_subject_offerings
```

Thêm nullable `subject_offering_id` vào các bảng chính như chapter, bank version, material, concept, family, release, course mapping, blueprint, quiz instance.

API mới:

```http
GET  /api/question-bank-v2/subject-offerings?subject_id=...
POST /api/question-bank-v2/subject-offerings
```

## Carry-over mới

Endpoint giữ nguyên:

```http
POST /api/question-bank-v2/bank-versions/{target_version_id}/carry-over
```

Nhưng `require_review` bị bỏ qua. Câu clone sang version đích có:

```text
status = approved
previous_question_id = source question id
lineage_root_question_id = root source question id
is_carry_over = true
```

## Exclusion / không clone

Endpoint cũ `questions/retire` giờ dùng để ghi nhận exclusion khi question_id thuộc version nguồn:

```text
excluded_source_question_ids trong metadata của target version
```

Không tạo question row mới trong target version.
Không mutate source question.

## Migration

```text
0013_v25_9_15_3_2_subject_offering_version_isolation.py
```

## Test notes

- `python -m compileall` pass trong môi trường tạo artifact.
- Pytest cần chạy trong backend container vì môi trường artifact thiếu SQLAlchemy.
