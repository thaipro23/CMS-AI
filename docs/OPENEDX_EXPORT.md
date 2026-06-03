# CMS OLX Export Notes

## Internal JSON vs CMS OLX

AI Server lưu câu hỏi trong model nội bộ vì cần nhiều metadata phục vụ vận hành:

- `source_node_id`, `source_chunk_id`, trang/timestamp, source excerpt
- `chapter_node_id`, `target_library_key`, difficulty
- quality score, quality flags, draft_error_reason
- review status, versioning, publish status
- model provider/model name, token usage, cost/job traceability
- `tag_names` để lọc trong CMS Library

Các metadata này **không nhét trực tiếp vào OLX**. Khi publish sang CMS, hệ thống gửi OLX và metadata theo 2 phần riêng:

1. `olx`: nội dung câu hỏi cho sinh viên làm.
2. `metadata/tag_names`: dữ liệu để connector gắn tag, truy vết nguồn và lọc trong CMS.

## Supported MVP export

MVP exporter hỗ trợ `single_choice` và convert thành:

```xml
<problem display_name="Topic - question-id">
  <multiplechoiceresponse>
    <label>Question text</label>
    <description>Learning objective</description>
    <choicegroup type="MultipleChoice">
      <choice correct="true">Correct answer</choice>
      <choice correct="false">Wrong answer</choice>
    </choicegroup>
    <solution>
      <div class="detailed-solution">
        <p>Explanation</p>
      </div>
    </solution>
  </multiplechoiceresponse>
</problem>
```

## Library ensure trước khi import

Khi publish một câu hỏi, AI Server luôn xử lý theo thứ tự:

1. Resolve câu hỏi về source node gốc.
2. Tìm chapter/module cha.
3. Xác định difficulty.
4. Ensure local library theo `course + chapter + difficulty`.
5. Gọi CMS connector để kiểm tra thư viện đó đã tồn tại chưa.
6. Nếu chưa có thì connector tạo thư viện mới.
7. Nếu có rồi thì dùng lại thư viện hiện tại, không tạo trùng.
8. Import OLX problem vào thư viện.
9. Gắn tags vào problem để lọc trong CMS.

## Tag để lọc trong CMS

Connector nhận `tag_names` trong cả ensure library và import problem payload. Ví dụ:

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

Giáo viên có thể dùng CMS Tags filter để lọc câu hỏi theo:

- AI Learning Check
- course
- chapter/module
- difficulty
- source node/unit
- source type
- topic tag

## API preview/export

Preview one question:

```http
GET /api/question-bank/{question_id}/openedx-olx
```

Preview approved questions in a course:

```http
GET /api/question-bank/export/openedx-olx?course_id={course_id}&status=approved
```

Download XML preview fragment:

```http
GET /api/question-bank/export/openedx-olx.xml?course_id={course_id}&status=approved
```

Lưu ý: endpoint download nhiều câu đang trả về **OLX fragment** gồm nhiều `<problem>` độc lập, không phải full OLX package. Production publish nên dùng connector import từng problem vào thư viện hoặc đóng zip OLX theo chuẩn riêng.

## Production note

Phần bắt buộc khi chuyển production:

1. CMS connector phải lookup thư viện theo `library_key` trước khi tạo.
2. Connector phải apply `tag_names` vào Library item/problem để UI filter dùng được.
3. Connector nên chống import trùng theo `question_id` hoặc external id.
4. AI Server không publish lại câu đã `published` nếu chưa có workflow revision/force republish.
