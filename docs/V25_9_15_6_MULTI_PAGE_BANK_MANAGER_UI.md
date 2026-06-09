# v25.9.15.6 - Multi-page Bank Manager UI + Exact Clone Flow

## Mục tiêu

Bản này bỏ hướng UI `/bank` một cục. Ngân hàng đề được tách thành nhiều trang quản trị rõ ràng, mỗi trang chỉ làm một việc chính.

Nguyên tắc UI:

- Giáo viên chỉ thấy: Bộ môn, Môn, Phiên bản môn, Bài, Tài liệu, Câu hỏi, Release, Quiz.
- Không ép người dùng hiểu `bank_version_id`, `library_key`, `itembank`, `upstream`, `mapping guard`.
- Tạo Quiz không nằm trong workspace của Chapter.
- Clone version môn là clone bản làm việc, không chạy diff, không publish Open edX, không clone Release.

## Route mới

```text
/bank/departments
/bank/departments/{departmentId}/subjects
/bank/subjects/{subjectId}/versions
/bank/subject-versions/{versionId}/chapters
/bank/chapters/{chapterId}
/bank/quiz
/bank/history
```

`/bank` cũ được redirect sang `/bank/departments`.

## Trang Bộ môn

URL:

```text
/bank/departments
```

Chỉ quản lý bộ môn:

- Danh sách bộ môn
- Tìm kiếm bộ môn
- Thêm bộ môn
- Click bộ môn để sang danh sách môn

## Trang Môn trong Bộ môn

URL:

```text
/bank/departments/{departmentId}/subjects
```

Chỉ quản lý môn trong một bộ môn:

- Danh sách môn
- Tìm kiếm môn
- Thêm môn
- Xem số version môn
- Click môn để sang trang version môn

## Trang Phiên bản môn

URL:

```text
/bank/subjects/{subjectId}/versions
```

Quản lý các kỳ/version của môn:

```text
WEB107_SP25
WEB107_SU25
WEB107_FA25
```

Form tạo version có 2 chế độ:

- Tạo mới trống
- Clone 100% từ version khác

Clone đúng nghiệp vụ:

```text
WEB107_SP25 → WEB107_SU25
```

Hệ thống clone bản làm việc:

- Bài
- Tài liệu
- Chunk
- Concept
- Family
- Câu hỏi approved/published dùng lại được

Không clone:

- Release
- Open edX Library
- Open edX component id

## Trang Chapter/Bài của một version môn

URL:

```text
/bank/subject-versions/{versionId}/chapters
```

Chỉ quản lý danh sách bài/chapter:

- Thêm bài
- Xem số bộ câu hỏi/release của từng bài
- Click bài để vào workspace

## Chapter Workspace

URL:

```text
/bank/chapters/{chapterId}
```

Đây là trang làm việc chính của giáo viên với một bài.

Bố cục:

1. Thống kê
2. Tài liệu
3. Tạo câu hỏi
4. Kiểm tra thay đổi tài liệu
5. Chốt Release / Publish Library
6. Danh sách câu hỏi / duyệt câu hỏi

Không có phần tạo Quiz trong workspace này.

Nếu bài chưa có bộ câu hỏi nội bộ, UI chỉ hiện nút:

```text
Bắt đầu làm câu hỏi cho bài này
```

Backend vẫn tạo `QuestionBankVersion`, nhưng UI không bắt giáo viên hiểu thuật ngữ đó.

## Trang tạo Quiz Open edX

URL:

```text
/bank/quiz
```

Giữ riêng để tạo Quiz khi Release đã sẵn sàng.

Điều kiện:

- Có Release
- Release đã publish sang Open edX Library
- Course Open edX đã map đúng
- Chapter Open edX đã map đúng
- Mapping guard pass
- Không trùng câu/component

## Trang lịch sử Quiz

URL:

```text
/bank/history
```

Hiển thị Quiz đã tạo trên Open edX và cho rollback nếu tạo nhầm.

## File chính đã sửa

```text
frontend/app/bank/page.tsx
frontend/app/bank/_components/BankPages.tsx
frontend/app/bank/departments/page.tsx
frontend/app/bank/departments/[departmentId]/subjects/page.tsx
frontend/app/bank/subjects/[subjectId]/versions/page.tsx
frontend/app/bank/subject-versions/[versionId]/chapters/page.tsx
frontend/app/bank/chapters/[chapterId]/page.tsx
frontend/app/bank/history/page.tsx
frontend/lib/api.ts
frontend/components/layout/AppShell.tsx
frontend/app/globals.css
```

## Migration

Không thêm migration mới.

## Test

Đã chạy:

```text
python3 -m compileall backend/app backend/alembic openedx-connector-plugin/openedx_ai_connector: PASS
npm ci --ignore-scripts: PASS
npm run typecheck: PASS
next build: compiled successfully, timeout ở bước cuối lint/type validation trong môi trường artifact
zip integrity: PASS
```

Chưa test UI thật trên server/UAT.
