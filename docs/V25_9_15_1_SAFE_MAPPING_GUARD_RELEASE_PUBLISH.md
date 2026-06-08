# v25.9.15.1 - Safe Mapping Guard + Bank Release Publish Wiring

## Mục tiêu

Bản này hoàn thiện hai mảnh bắt buộc trước khi dùng kiến trúc Question Bank-first trong test/prod:

1. **Safe Mapping Guard**: không cho dán nhầm ngân hàng đề vào khóa học Open edX sai môn/chapter/release.
2. **Bank Release Publish Wiring**: Bank Release chỉ được coi là `published` sau khi các câu hỏi approved được import thật vào đúng Open edX Content Library của release.

Nguyên tắc không đổi: **1 Bank Release = 1 Open edX Library**.

## API mới

### Validate course mapping

```http
POST /api/question-bank-v2/course-mappings/validate
```

Payload:

```json
{
  "openedx_course_id": "course-v1:FPT+DOM123+SU26",
  "subject_id": "...",
  "department_id": "...",
  "term": "SU26",
  "openedx_course_title": "Thiết kế nhận diện thương hiệu"
}
```

Checks chính:

- `course_id_format`: Course ID phải đúng `course-v1:ORG+COURSE+RUN`.
- `course_code_match`: mã course phải khớp mã môn.
- `term_match`: cảnh báo nếu kỳ nhập khác run.
- `existing_mapping`: không ghi đè mapping cũ.
- `course_title_similarity`: cảnh báo nếu tên course khác tên môn.

### Validate chapter mapping

```http
POST /api/question-bank-v2/course-chapter-mappings/validate
```

Checks chính:

- Course mapping tồn tại.
- Chapter thuộc đúng subject.
- Bank Release thuộc đúng subject/chapter.
- Bank Release phải là `published`.
- Release phải có `openedx_library_key`.
- Node Open edX phải là `block-v1` và thuộc đúng course.
- Nếu node title có số bài khác chapter, hệ thống chặn.

### Publish Bank Release to Open edX

```http
POST /api/question-bank-v2/releases/{release_id}/publish-openedx
```

Payload:

```json
{
  "openedx_course_id_for_org": "course-v1:FPT+DOM123+BANK",
  "force_reimport": false
}
```

Luồng:

1. Lấy câu hỏi `approved/published` thuộc Bank Version.
2. Ensure Open edX Library riêng cho release.
3. Import từng câu hỏi OLX vào Library đó.
4. Verify từng component nếu connector hỗ trợ.
5. Lưu `openedx_library_problem_id` vào `ai_bank_release_questions`.
6. Đánh dấu Release là `published` chỉ khi toàn bộ import không lỗi.

Nếu lỗi giữa chừng, hệ thống chuyển release sang `publish_failed` và rollback best-effort các component vừa import trong request hiện tại.

## Migration

```text
0010_v25_9_15_1
```

Thêm metadata validate vào:

- `ai_edx_course_mappings`
- `ai_edx_course_chapter_mappings`

## UI

Trang `/bank` được bổ sung:

- Nút **Publish Library** trên từng Bank Release.
- Bước **Kiểm tra mapping** trước khi lưu course mapping.
- Bước **Kiểm tra chapter** trước khi lưu chapter mapping.
- Hiển thị `PASS/WARN/FAIL` để người dùng không phải đọc ID kỹ thuật.

## Giới hạn còn lại

Bản này chưa làm upload/generate câu hỏi trực tiếp từ Bank Version. Phần đó thuộc nhánh sau:

```text
v25.9.15.2 - Bank Material Upload + Generate from Bank Version
```
