# v25.9.15.6.23 - Quiz Create Export Parity + Document Balanced Generation + HTTP MFE Config

## Mục tiêu

Bản này xử lý 3 vấn đề người dùng báo trong UAT:

1. Tạo Quiz từ Bank Release đang tạo sai slot Problem Bank: slot đầu dồn nhiều câu, slot sau thiếu/rỗng.
2. Tạo câu hỏi trong Bank Version chưa chia đều theo tài liệu, dễ dồn vào một tài liệu/chunk.
3. Learning MFE HTTP đang gọi nhầm `https://cms-test.poly.edu.vn/login_refresh` do build chưa ăn đúng cấu hình runtime/env.

## Thay đổi backend tạo Quiz

`create_quiz_from_release` giờ dùng planner mới `bank_release_export_parity_difficulty_itembank_v2`.

Quy tắc:

```text
Section Open edX: Bài 1.1
  Subsection: Quiz 1.1
    Grade as: Quiz
    Unit: Quiz
      Problem Bank EASY    max_count = số câu EASY cần hiện
      Problem Bank MEDIUM  max_count = số câu MEDIUM cần hiện
      Problem Bank HARD    max_count = số câu HARD cần hiện
```

Ví dụ `total_questions=5`, tỷ lệ `60/20/20`:

```text
EASY   = 3
MEDIUM = 1
HARD   = 1
```

Payload slot gửi sang Open edX connector sẽ là 3 slot:

```json
[
  {"difficulty":"EASY", "pick_count":3, "max_count":3, "openedx_problem_ids":[...]},
  {"difficulty":"MEDIUM", "pick_count":1, "max_count":1, "openedx_problem_ids":[...]},
  {"difficulty":"HARD", "pick_count":1, "max_count":1, "openedx_problem_ids":[...]}
]
```

Không còn tạo slot theo family/variant dẫn tới UI Studio khó hiểu.

## Thay đổi connector Open edX

`insert_problem_banks` không còn ép `pick_count=1`. Connector dùng:

```python
max_count = slot.pick_count or slot.max_count or 1
```

Verify cũng kiểm tra `max_count` theo slot tương ứng.

## Thay đổi tạo câu hỏi theo tài liệu

Bank generation giờ chia đều số câu theo `LearningMaterialVersion` trước, sau đó chia EASY/MEDIUM/HARD trong từng tài liệu.

Ví dụ 30 câu / 3 tài liệu:

```text
Tài liệu 1: 10 câu
Tài liệu 2: 10 câu
Tài liệu 3: 10 câu
```

Nếu 31 câu / 3 tài liệu:

```text
Tài liệu 1: 11 câu
Tài liệu 2: 10 câu
Tài liệu 3: 10 câu
```

Trong từng tài liệu tiếp tục chia difficulty theo tỷ lệ người dùng nhập.

API preview/generate trả thêm `material_balancing` để frontend/ops kiểm tra phân bổ.

## Learning MFE HTTP config

Bản zip AI Server không thể tự thay đổi dist của `frontend-app-learning` đang chạy trên Tutor. Khi UAT chạy HTTP, cần build Learning MFE với env HTTP:

```env
BASE_URL=http://app.cms-test.poly.edu.vn/learning
LMS_BASE_URL=http://cms-test.poly.edu.vn
LOGIN_URL=http://cms-test.poly.edu.vn/login
LOGOUT_URL=http://cms-test.poly.edu.vn/logout
REFRESH_ACCESS_TOKEN_ENDPOINT=http://cms-test.poly.edu.vn/login_refresh
STUDIO_BASE_URL=http://scms-test.poly.edu.vn
```

Sau build cần grep dist để chắc chắn không còn `https://cms-test.poly.edu.vn`.
