# CMS Library Ensure + Tags khi publish OLX

## Mục tiêu

Khi publish câu hỏi sang CMS, AI Server không import thẳng một problem vào nơi không rõ ràng. Luồng chuẩn là:

1. Resolve câu hỏi về `source_node_id`.
2. Tìm chapter/module cha.
3. Xác định difficulty của câu hỏi.
4. Tạo `library_key` theo `course + chapter/module + difficulty`.
5. Gọi connector để **kiểm tra thư viện đã tồn tại chưa**.
6. Nếu thư viện chưa có thì connector tạo mới.
7. Nếu thư viện đã có thì dùng lại, không tạo trùng.
8. Import OLX problem vào đúng thư viện.
9. Gắn tag cho problem để giáo viên lọc trong CMS.

## Tag dùng để lọc trong CMS

Mỗi problem import vào thư viện được gửi kèm `tag_names` trong payload metadata. Bộ tag mặc định gồm:

```txt
AI Learning Check
course:<course-code>
chapter:<chapter-slug>-<hash>
chapter-title:<chapter-title>
difficulty:easy|medium|hard
source:<source-title-slug>-<hash>
source-type:html|transcript|file|problem
question:<short-id-hash>
topic:<ai/user tag nếu có>
```

Ví dụ:

```json
{
  "tag_names": [
    "AI Learning Check",
    "course:dom1051",
    "chapter:chuong-1-rest-api-co-ban-a1b2c3d4",
    "chapter-title:Chương 1: REST API cơ bản",
    "difficulty:hard",
    "source:unit-1-2-get-post-put-delete-e5f6a7b8",
    "source-type:transcript",
    "question:12345678"
  ]
}
```

Các tag này giúp CMS lọc câu hỏi theo difficulty, chương/bài, nguồn nội dung và loại nguồn khi giáo viên tạo Problem Bank/Randomized content.

## Vì sao không nhét tag/metadata vào OLX?

OLX problem XML chỉ nên chứa nội dung mà sinh viên sẽ làm: câu hỏi, đáp án, đáp án đúng và lời giải. Các dữ liệu như `source_node_id`, `chapter_node_id`, `target_library_key`, `difficulty`, `tag_names` được gửi riêng qua connector metadata. Cách này tránh lỗi XML import và giữ metadata vận hành ở tầng CMS/AI Server.

## Payload ensure library

```json
{
  "chapter_node_id": "course-v1:...+type@chapter+block@chapter-rest-api",
  "display_name": "DOM1051 - Chương 1: REST API cơ bản - HARD",
  "library_key": "DOM1051-chuong-1-rest-api-co-ban-hard",
  "tag_names": ["AI Learning Check", "difficulty:hard", "chapter:..."],
  "metadata": {
    "library_key": "DOM1051-chuong-1-rest-api-co-ban-hard",
    "chapter_node_id": "...",
    "chapter_title": "Chương 1: REST API cơ bản",
    "difficulty": "hard"
  }
}
```

Connector cần trả về:

```json
{
  "library_key": "DOM1051-chuong-1-rest-api-co-ban-hard",
  "openedx_library_id": "...",
  "created": false,
  "status": "library_exists"
}
```

Nếu chưa có thư viện, `created=true` và `status=library_created`.

## Payload import problem

```json
{
  "course_id": "course-v1:Business-Administration+DOM1051+FPS2026_SPRING2026",
  "library_key": "DOM1051-chuong-1-rest-api-co-ban-hard",
  "display_name": "REST API - abc12345",
  "olx": "<problem>...</problem>",
  "tag_names": ["AI Learning Check", "difficulty:hard", "source:unit-..."],
  "metadata": {
    "source_node_id": "...",
    "chapter_node_id": "...",
    "difficulty": "hard",
    "question_id": "..."
  }
}
```

Connector production phải apply `tag_names` vào item trong CMS để UI Tags filter dùng được.
