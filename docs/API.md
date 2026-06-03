# API

## Health

`GET /api/health`

## Course sync

`POST /api/courses/sync`

```json
{
  "course_id": "course-v1:FPT+PRN232+2026",
  "force": false
}
```

## Cost estimate

`POST /api/cost/estimate`

```json
{
  "course_id": "course-v1:FPT+PRN232+2026",
  "question_count": 50,
  "content_tokens": 30000
}
```

## Generate questions

`POST /api/questions/generate`

```json
{
  "course_id": "course-v1:FPT+PRN232+2026",
  "question_count": 20,
  "batch_size": 20,
  "topic": "HTTP Methods",
  "content": "...optional demo content..."
}
```

## Question bank

### List

`GET /api/question-bank?course_id=...&status=pending_review`

### Get one

`GET /api/question-bank/{id}`

### Edit in Teacher Review Queue

`PATCH /api/question-bank/{id}`

```json
{
  "actor": "teacher",
  "note": "Sửa câu hỏi cho rõ nghĩa hơn",
  "topic": "HTTP Methods",
  "difficulty": "easy",
  "cognitive_level": "remember",
  "learning_objective": "Sinh viên nhận biết GET dùng để lấy dữ liệu.",
  "question_text": "Phương thức HTTP nào thường được dùng để lấy dữ liệu từ server?",
  "option_a": "GET",
  "option_b": "POST",
  "option_c": "DELETE",
  "option_d": "PATCH",
  "correct_answer": "A",
  "explanation": "GET thường được dùng để yêu cầu server trả về dữ liệu.",
  "source_ref": "mock:block:http-methods",
  "source_type": "transcript",
  "source_timestamp_start": "00:01:20",
  "source_timestamp_end": "00:01:45",
  "source_chunk_id": "mock-chunk-http-methods",
  "source_excerpt": "GET dùng để lấy dữ liệu.",
  "tags": ["REST API", "HTTP Methods"]
}
```

Khi edit, hệ thống snapshot version cũ vào `ai_question_versions`, tăng `version`, chạy lại Quality Checker và đưa câu hỏi về `pending_review` nếu hợp lệ. Câu hỏi `published` không được sửa trực tiếp; bản production nên tạo version mới để tránh thay đổi nội dung đã được sinh viên làm.

### Review actions

- `POST /api/question-bank/{id}/approve`
- `POST /api/question-bank/{id}/reject`
- `POST /api/question-bank/{id}/publish`

Body:

```json
{
  "actor": "teacher",
  "note": "approved"
}
```

## Jobs

`GET /api/jobs?course_id=...`

## Question Bank / Open edX Export Additions

### Filter, search, sort questions

```http
GET /api/question-bank?course_id={course_id}&status=approved&difficulty=easy&topic=REST&search=GET&sort_by=updated_at&sort_dir=desc
```

### Question bank stats

```http
GET /api/question-bank/stats?course_id={course_id}
```

### Bulk approve

```http
POST /api/question-bank/bulk/approve
```

Approve selected:

```json
{
  "actor": "teacher",
  "note": "Approve selected",
  "question_ids": ["id-1", "id-2"]
}
```

Approve all pending in a course:

```json
{
  "actor": "teacher",
  "course_id": "course-v1:FPT+PRN232+2026",
  "approve_all_pending": true
}
```

### Correct wrong approve/reject click

```http
POST /api/question-bank/{question_id}/status
```

```json
{
  "actor": "teacher",
  "note": "Undo approve",
  "target_status": "pending_review"
}
```

### Export to Open edX OLX XML

```http
GET /api/question-bank/{question_id}/openedx-olx
GET /api/question-bank/export/openedx-olx?course_id={course_id}&status=approved
GET /api/question-bank/export/openedx-olx.xml?course_id={course_id}&status=approved
```

## Course Chunks API - v6 UX update

Used by the frontend `Generate` step when the teacher selects **Dùng course chunks đã sync** instead of manual input.

```http
GET /api/courses/{course_id}/chunks?source_type=all&search=keyword&limit=200
```

Returns synced content chunks from Open edX course content. The frontend lets the teacher search/filter chunks and select one or many chunks before generating Learning Check questions.

Example response item:

```json
{
  "id": "chunk-id",
  "course_id": "course-v1:FPT+PRN232+2026",
  "block_id": "course-v1:FPT+PRN232+2026:video:http-methods",
  "content": "Transcript: GET dùng để lấy dữ liệu...",
  "token_count": 24,
  "source_type": "video",
  "source_ref": "course-v1:FPT+PRN232+2026:video:http-methods"
}
```

Frontend generation modes:

- Manual mode: teacher pastes text into textarea. Useful for demo/testing.
- Course chunks mode: teacher selects synced chunks. This is the production-oriented flow.

In both modes the backend still uses the same generate endpoint:

```http
POST /api/questions/generate
```

## v7 RBAC & Analytics Dashboard

### Demo RBAC headers

The starter project now enforces a lightweight RBAC layer through request headers. This is for MVP/demo only. In production, these values should be derived from Open edX SSO/staff roles.

```http
X-User-Id: demo-teacher
X-User-Role: teacher
```

Supported roles:

| Role | Permissions |
|---|---|
| `admin` | full access, budget/admin actions |
| `teacher` | sync course, estimate cost, generate, edit, review, publish, export |
| `reviewer` | estimate, edit/review questions, export, dashboard |
| `viewer` | read-only dashboard/question/job view |

### Current user

```http
GET /api/auth/me
GET /api/auth/roles
```

### Analytics overview

```http
GET /api/analytics/overview?course_id={course_id}
```

Returns question statistics, review approve rate, job status counts, cost usage, sync/chunk metrics and governance/quota metrics.

### Permission-protected routes

Write actions such as sync, generate, edit, approve/reject, publish, export and cost estimate now require the appropriate RBAC permission. Unauthorized roles receive `403 Forbidden` before the action is executed.
