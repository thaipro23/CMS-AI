# v25.2 - Difficulty Distribution & Randomized Difficulty Banks

## Mục tiêu

Bổ sung mức độ `hard`, cho giáo viên nhập tỷ lệ câu hỏi `easy / medium / hard`, mặc định `50% / 30% / 20%`, nhưng tất cả câu hỏi vẫn phải nằm trong phạm vi tài liệu đã chọn.

## Làm tròn số câu bằng Largest Remainder Method

Backend không lấy phần trăm rồi làm tròn tùy tiện. Thuật toán:

1. Tính `raw_count = total_questions * percent / 100`
2. Lấy phần nguyên trước bằng `floor(raw_count)`
3. Tính còn thiếu bao nhiêu câu so với tổng
4. Cộng phần thiếu cho nhóm có số dư lớn nhất

Ví dụ `20 câu` với `50/30/20`:

```txt
EASY   = 20 * 50% = 10
MEDIUM = 20 * 30% = 6
HARD   = 20 * 20% = 4
```

Ví dụ `7 câu` với `50/30/20`:

```txt
raw:   easy 3.5, medium 2.1, hard 1.4
floor: easy 3,   medium 2,   hard 1 = 6
thiếu 1 câu -> cộng cho easy vì số dư lớn nhất 0.5
kết quả: easy 4, medium 2, hard 1
```

Code chính: `backend/app/algorithms/largest_remainder.py`.

## UI

Frontend thêm input:

```txt
Easy %
Medium %
Hard %
```

Ở:

```txt
/workflow
/generate
```

Mặc định:

```txt
Easy 50
Medium 30
Hard 20
```

Backend sẽ normalize nếu tổng không đúng 100 để tránh lỗi do client.

## Tối ưu batch để giảm token

Bản v25.0 từng chia `20 câu = 6 + 6 + 6 + 2` để tránh JSON dài làm lỗi parser. Cách đó an toàn nhưng tốn token vì gửi lại full content nhiều lần.

v25.2 đổi sang batch theo difficulty. Với mặc định 20 câu:

```txt
20 câu = 10 EASY + 6 MEDIUM + 4 HARD
```

Tức là 3 model calls thay vì 4 calls. Chỉ khi một nhóm difficulty vượt `batch_size` thì mới split tiếp. Default `batch_size = 12`.

Ví dụ:

```txt
20 câu, 50/30/20 -> 10 + 6 + 4
50 câu, 50/30/20, batch_size 12 -> EASY 12+12+1, MEDIUM 12+3, HARD 10
```

## Tách bank theo Chapter + Difficulty

Không còn chỉ có:

```txt
DOM1051 - Chapter 1 - REST API
```

Mà tạo thành:

```txt
DOM1051 - Chapter 1 - REST API - EASY
DOM1051 - Chapter 1 - REST API - MEDIUM
DOM1051 - Chapter 1 - REST API - HARD
```

Database `ai_course_libraries` thêm field:

```txt
difficulty
```

Unique constraint mới:

```txt
(course_id, chapter_node_id, difficulty)
```

Question vẫn giữ metadata:

```txt
source_node_id
source_node_title
chapter_node_id
chapter_title
target_library_key
difficulty
```

Nhờ vậy Open edX Problem Bank trong Unit có thể random/filter theo cả:

```txt
source_node_id = node gốc
library = chapter + difficulty
```

## Publish/Open edX

Khi publish câu hỏi:

1. Resolve `source_node_id`
2. Tìm chapter cha
3. Lấy difficulty của câu hỏi
4. Ensure library theo `chapter + difficulty`
5. Import OLX vào đúng difficulty library

Metadata publish có thêm:

```txt
difficulty
```

## Lưu ý production

Hard question vẫn là Learning Check, không phải Exam. Prompt đã ghi rõ:

```txt
Hard = cần kết hợp hoặc áp dụng ý trong tài liệu, nhưng không hỏi ngoài tài liệu và không mẹo.
```
