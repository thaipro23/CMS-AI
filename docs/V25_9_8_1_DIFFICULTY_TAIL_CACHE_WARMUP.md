# v25.9.8.1 - Difficulty-Preserved Tail + Cache-First Scheduling

## Lý do sửa

Bản v25.9.8 đã thêm controlled parallel GPT calls, nhưng tail batch đang có xu hướng gom các phần lẻ của nhiều difficulty vào một prompt mixed. Điều này lệch với kiến trúc project hiện tại: hệ thống dùng 3 prompt riêng theo difficulty.

Kiến trúc đúng:

```txt
Prompt EASY
Prompt MEDIUM
Prompt HARD
```

Vì vậy tail cũng phải giữ riêng theo difficulty.

## Hành vi mới

Ví dụ 50 câu, tỉ lệ 50/30/20, batch_size=12:

```txt
EASY   25 = 12 + 12 + tail EASY 1
MEDIUM 15 = 12      + tail MEDIUM 3
HARD   10 = 10
```

Nếu primary chạy xong:

```txt
EASY 12 tạo được 11  -> thiếu 1 EASY
MEDIUM 12 lỗi        -> thiếu 12 MEDIUM
HARD 10 OK           -> thiếu 0 HARD
```

Tail mới sẽ là:

```txt
EASY tail   = 1 lẻ ban đầu + 1 thiếu = 2 EASY
MEDIUM tail = 3 lẻ ban đầu + 12 thiếu = 15 MEDIUM
HARD tail   = 0
```

Tức là gọi:

```txt
Call prompt EASY:   2 câu
Call prompt MEDIUM: 15 câu
```

Không gọi 17 câu mixed.

## Cache-first scheduling

Để tăng cached input token, worker không bắn toàn bộ batch cùng một lúc ngay từ đầu. Với mỗi `prompt_cache_key`, worker sẽ:

1. Chọn một batch nhỏ nhất làm warm-up.
2. Gọi batch warm-up trước để OpenAI có cơ hội cache stable prefix.
3. Sau đó mới chạy các batch còn lại song song theo `OPENAI_MAX_PARALLEL_CALLS`.

Stable prefix gồm:

```txt
system/policy
schema/rules
course metadata
chapter/scope
selected chunks/content
source grounding rules
```

Dynamic suffix gồm:

```txt
difficulty
question_count
batch_index
avoid duplicate instruction
```

Như vậy EASY/MEDIUM/HARD vẫn là prompt riêng, nhưng có cùng prefix lớn nên có cơ hội ăn cache nhiều input nhất.

## Cấu hình mới

```env
OPENAI_PROMPT_CACHE_WARMUP_ENABLED=true
```

Giữ các cấu hình cũ:

```env
OPENAI_PARALLEL_ENABLED=true
OPENAI_MAX_PARALLEL_CALLS=3
OPENAI_RETRY_MAX_ATTEMPTS=3
OPENAI_RETRY_BASE_SECONDS=2
GENERATION_TAIL_BATCH_WAIT_ENABLED=true
```

## File chính sửa

```txt
backend/app/services/generation_planner.py
backend/app/worker.py
backend/app/core/config.py
backend/app/services/runtime_settings.py
backend/app/schemas/settings.py
backend/app/tests/test_v25_9_regression.py
.env
.env.example
```
