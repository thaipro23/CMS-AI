# v25.9.13.19 - Compact Open edX Problem Display Name

## Mục tiêu

LMS đang hiển thị mỗi problem một câu với tiêu đề dài và dòng `<description>` ngay dưới câu hỏi, làm UI bị rối.

## Thay đổi

- Exporter dùng `learning_objective` — trước đây được đưa vào `<description>` — làm `display_name` của Open edX problem.
- Nếu `learning_objective` trống thì fallback lần lượt sang `topic`, `source_node_title`, rồi `question_text`.
- Bỏ hẳn thẻ `<description>` khỏi OLX để learner view gọn hơn.
- Vẫn giữ `<demandhint>` để người học có gợi ý khi cần, nhưng không lộ đáp án.

## File chính

- `backend/app/services/openedx_exporter.py`
- `backend/app/tests/test_openedx_exporter.py`

## Lưu ý

Các problem đã publish trước đó sẽ không tự đổi display name. Cần publish lại câu mới, hoặc xóa component cũ rồi import lại.
