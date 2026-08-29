# v25.9.16.7.2.64.16.5.7.2.12 - Knowledge Hint + Misconception Feedback

## Mục tiêu

Hint là **mẩu kiến thức sinh viên dùng để trả lời câu hỏi**, không phải hướng dẫn làm bài. Mỗi câu chỉ có **1 Hint** trước khi trả lời; feedback theo misconception hiển thị sau khi submit.

## Thiết kế

- Không yêu cầu AI sinh `pedagogy.clue` hay `pedagogy.example` cho generation mới.
- `source_evidence` vốn đã có trong contract grounding được yêu cầu viết thành một mẩu kiến thức ngắn (ưu tiên <= 24 từ) và được dùng trực tiếp làm Hint.
- Backend **không** nối thêm các câu kiểu “hãy so sánh”, “hãy loại trừ”, “hãy nhớ lại”.
- Hint được chặn nếu chứa chỉ dẫn lộ nhãn đáp án như “đáp án đúng là A” / “chọn phương án B”, nhưng được phép chứa chính kiến thức cần thiết để suy ra đáp án.
- Nếu câu cũ không có `source_evidence`, backend fallback `source_excerpt`, sau đó mới fallback `pedagogy.clue` cũ để tương thích. Nếu không có kiến thức hữu ích thì không render Hint thay vì render hướng dẫn vô nghĩa.
- Misconception vẫn được remap theo nội dung option sau khi backend shuffle A/B/C/D.
- Open edX dùng native `<demandhint><hint>...</hint></demandhint>` và `<choicehint>`; không sửa core Open edX.

## Tối ưu token

Hint không thêm field output AI mới: nó tái sử dụng `source_evidence` đã cần cho source grounding. Contract mới bỏ `pedagogy.clue`; `pedagogy` chỉ còn các misconception ngắn cho distractor. Vì vậy chi phí output cho Hint gần như bằng 0 so với contract đã có `source_evidence`.

## Compatibility

- `questions.pedagogy_json` vẫn nullable.
- `clue` vẫn được parser/backend chấp nhận cho dữ liệu UAT cũ nhưng model mới không sinh field này.
- Không có migration mới ngoài migration `0058` đã thêm cột `pedagogy_json` trong patch pedagogy.

## Verification

- `python -m compileall`: PASS.
- Targeted tests (`test_openedx_exporter.py`, `test_compact_pedagogy.py`) với SQLite test URL: **14 passed**.
- Native OLX exporter emits exactly one knowledge `<hint>` when source knowledge exists and per-choice `<choicehint>`.
- Khi không có source knowledge hữu ích, exporter không tạo empty/useless `<demandhint>`.
