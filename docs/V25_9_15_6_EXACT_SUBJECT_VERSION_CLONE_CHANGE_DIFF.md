# v25.9.15.6 - Exact Subject Version Clone + Document Change Diff

## Mục tiêu nghiệp vụ

Bản này chốt lại đúng cách hiểu người dùng về clone version môn:

```text
DOM123_SP25
→ clone sang DOM123_SU25
```

Clone version môn là copy **bản làm việc** sang kỳ mới, không phải chốt/publish bộ đề.

## Luồng đúng

```text
1. Giáo viên clone DOM123_SP25 sang DOM123_SU25
2. Hệ thống copy bài, tài liệu, bank version, concept, family, câu hỏi approved sang ID mới
3. Hệ thống KHÔNG clone Release
4. Hệ thống KHÔNG publish Open edX Library khi clone
5. Hệ thống KHÔNG chạy diff khi clone
6. Nếu giáo viên upload/sửa tài liệu trong SU25, hệ thống đánh dấu cần kiểm tra khác biệt
7. Giáo viên bấm kiểm tra khác biệt/diff nếu có thay đổi tài liệu
8. Giáo viên chỉnh câu hỏi, tạo thêm câu nếu cần
9. Giáo viên bấm Chốt Release thủ công
10. Release mới publish sang Open edX Library mới
```

## Clone 100% bản làm việc gồm gì

Khi clone subject offering, backend tạo bản ghi mới cho:

```text
SubjectChapter
QuestionBankVersion
LearningMaterialVersion
MaterialChunk
ConceptVersion
BankQuestionFamily
Question đã approved/published
```

Câu hỏi clone sang kỳ mới:

```text
status = approved
is_carry_over = true
previous_question_id = câu nguồn
bank_release_id = null
openedx_library_problem_id = null
```

## Không clone Release

Release là hành động chốt tay sau khi giáo viên đã kiểm tra nội dung kỳ mới. Vì vậy clone không tạo `QuestionBankRelease` mới và không reuse `openedx_library_key` cũ.

Metadata clone có:

```text
clone_policy = exact_working_copy_new_records_no_shared_ids
release_policy = release_not_cloned_create_manually_after_editing
release_cloned = false
diff_policy = only_when_material_changes_after_clone
document_change_state = unchanged_after_clone
diff_required = false
diff_base_bank_version_id = <bank version nguồn>
```

## Khi nào bật diff

Diff không chạy khi clone. Diff chỉ được bật khi upload tài liệu mới vào Bank Version đã clone.

Khi upload tài liệu mới vào version clone, backend set:

```text
document_change_state = changed_after_clone
diff_required = true
diff_base_bank_version_id = <bank version nguồn>
diff_trigger = material_uploaded_after_clone
```

UI `/bank` sẽ hiện cảnh báo và nút:

```text
Kiểm tra khác biệt
```

## API bị ảnh hưởng

Không thêm migration mới.

API clone vẫn là:

```http
POST /api/question-bank-v2/subject-versions
```

Payload clone tối giản từ UI:

```json
{
  "subject_id": "...",
  "term": "SU25",
  "clone_from_offering_id": "..."
}
```

Các field `clone_chapters`, `clone_materials`, `clone_questions` vẫn còn để tương thích API cũ nhưng backend không dùng để clone nửa vời nữa. Khi có `clone_from_offering_id`, backend luôn clone đủ bản làm việc.

API upload tài liệu trả thêm:

```json
{
  "diff_required": true,
  "diff_base_bank_version_id": "...",
  "document_change_state": "changed_after_clone"
}
```

API diff đã cho phép so sánh Bank Version thuộc hai kỳ khác nhau nếu có quan hệ clone lineage:

```http
POST /api/question-bank-v2/bank-versions/{bank_version_id}/diff/preview
```

## File đã sửa

```text
backend/app/services/question_bank_service.py
backend/app/schemas/question_bank.py
backend/app/api/routes/question_bank_v2.py
frontend/app/bank/page.tsx
```

## Cách build

```bash
docker compose -f docker-compose.prod.yml --env-file .env.production build --no-cache backend worker frontend
docker compose -f docker-compose.prod.yml --env-file .env.production run --rm backend alembic upgrade head
docker compose -f docker-compose.prod.yml --env-file .env.production up -d --force-recreate backend worker frontend
```

## Cách test nghiệp vụ

1. Vào `/bank`.
2. Chọn Bộ môn → Môn.
3. Tạo/chuẩn bị version nguồn `DOM123_SP25` có bài, tài liệu, câu hỏi approved.
4. Chọn tạo version mới `SU25`, chọn clone từ `DOM123_SP25`.
5. Kiểm tra SU25 có bài/tài liệu/câu hỏi mới, ID mới.
6. Kiểm tra SU25 chưa có Release mới.
7. Upload tài liệu mới vào một Bank Version của SU25.
8. UI phải hiện cảnh báo cần kiểm tra khác biệt.
9. Bấm `Kiểm tra khác biệt`.
10. Sau khi giáo viên sửa xong mới bấm `Tạo Release` và `Publish Library`.
