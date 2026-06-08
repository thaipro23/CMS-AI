# v25.9.15.0 - Versioned Question Bank First Architecture

## Mục tiêu

Bản này chuyển trục dữ liệu từ `course_id first` sang `question bank first`:

```text
Bộ môn → Môn → Chapter/Bài → Bank Version → Bank Release → Open edX Course Mapping
```

Ngân hàng đề có thể được chuẩn bị, generate và duyệt trước khi khóa học Open edX được tạo. Khi khóa học Open edX đã có, giáo viên map course vào môn/chapter và dùng Bank Release đã publish để tạo Quiz/Problem Bank.

## Nguyên tắc production

1. Không sửa đè câu hỏi đã duyệt/published.
2. Tài liệu đổi thì tạo `Material Version` và `Bank Version` mới.
3. `1 Bank Release = 1 Open edX Library`.
4. Course cũ giữ release cũ. Course mới có thể dùng release mới.
5. Open edX chỉ là nơi tiêu thụ bank release, không còn là chủ sở hữu duy nhất của câu hỏi.

## Bảng mới

- `ai_departments`
- `ai_subjects`
- `ai_subject_chapters`
- `ai_question_bank_versions`
- `ai_learning_material_versions`
- `ai_concept_versions`
- `ai_bank_question_families`
- `ai_question_bank_releases`
- `ai_bank_release_questions`
- `ai_edx_course_mappings`
- `ai_edx_course_chapter_mappings`
- `ai_quiz_blueprints`
- `ai_course_quiz_instances`

`ai_questions` được bổ sung các cột nullable để gắn câu hỏi cũ vào mô hình bank-first mà không phá luồng cũ.

## Workflow chuẩn

### 1. Chuẩn bị ngân hàng đề

```text
Tạo Bộ môn
→ Tạo Môn
→ Tạo Chapter
→ Tạo Bank Version
→ Upload tài liệu vào Bank Version
→ AI parse/chunk/concept/generate
→ Duyệt câu hỏi
→ Tạo Bank Release
→ Publish sang Open edX Library riêng của release
```

### 2. Khi có course Open edX

```text
Sync/nhập course Open edX
→ Map course vào Subject
→ Map Open edX chapter/node vào Subject Chapter + Bank Release
→ Chọn Quiz Blueprint
→ Tạo Quiz + native ItemBank Problem Bank
```

## API mới

Prefix: `/api/question-bank-v2`

- `GET /summary`
- `GET|POST /departments`
- `GET|POST /subjects`
- `GET|POST /chapters`
- `GET|POST /bank-versions`
- `GET|POST /material-versions`
- `GET|POST /releases`
- `GET|POST /course-mappings`
- `GET|POST /course-chapter-mappings`
- `GET|POST /quiz-blueprints`

## UI mới

Trang `/bank` gom workflow để người dùng không phải hiểu chi tiết DB:

1. Khai báo Bộ môn/Môn/Chapter
2. Tạo Bank Version
3. Tạo Release và Library key
4. Map course Open edX vào môn

## Giới hạn của bản này

Bản này tạo nền dữ liệu và UI quản trị bank-first. Nó chưa tự động migrate toàn bộ câu hỏi cũ sang bank version nếu người dùng chưa chọn subject/chapter/version. Luồng publish thật sang Open edX Library vẫn dùng service publish hiện tại và sẽ được nối vào release trong các bản tiếp theo.
