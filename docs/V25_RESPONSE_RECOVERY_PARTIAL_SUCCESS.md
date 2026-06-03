# v25.0 - Response Recovery & Partial Success

## Lý do sửa

Bản v24.9 đã lưu estimate và actual usage, nhưng nếu OpenAI Responses API trả kết quả thành công rồi backend lỗi ở bước parse JSON hoặc lưu DB, job vẫn bị đánh `failed` và `actual_cost_usd = 0`. Thực tế OpenAI đã xử lý request nên vẫn trừ tiền.

Người dùng cũng ghi nhận 6 câu chạy được nhưng 20 câu lỗi. Nguyên nhân thường gặp là output JSON dài hơn, dễ lỗi parse/validation hoặc response bị chia đoạn.

## Thay đổi chính

1. Mỗi model call bị giới hạn tối đa 6 câu.
   - 20 câu được chia thành `6 + 6 + 6 + 2`.
   - Estimate cũng tính theo các batch này, không còn estimate một prompt 20 câu rồi worker chạy khác.

2. Worker lưu actual usage ngay sau khi OpenAI trả về.
   - Nếu parse lỗi sau đó, job không mất usage/cost.
   - `actual_cost_usd` không nhân safety factor.

3. Thêm trạng thái partial.
   - `completed`: tạo đủ câu.
   - `partial_completed`: không lỗi model nhưng số câu tạo được ít hơn yêu cầu.
   - `model_parse_failed`: OpenAI đã trả response nhưng parser lỗi, chưa tạo được câu nào.
   - `partial_failed`: đã có câu hoặc token usage nhưng lỗi ở batch sau / parse / DB.

4. Lưu thông tin debug.
   - `openai_response_ids`
   - `raw_model_output_text`
   - `raw_model_usage_json`
   - `model_parse_error`
   - `completed_question_count`

## Quy tắc production

OpenAI success không đồng nghĩa job success. Vì vậy pipeline được tách thành:

```txt
model_completed -> parse_completed -> db_completed -> review/publish
```

Nếu `model_completed` thành công thì phải reconcile usage/cost dù các bước sau lỗi.
