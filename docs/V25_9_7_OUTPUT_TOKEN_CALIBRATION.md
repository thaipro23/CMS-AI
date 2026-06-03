# v25.9.7 - Output Token Calibration

## Vấn đề

Các bản trước có lúc dùng số cứng như `320 output tokens/câu`. Với JSON Learning Check đầy đủ, thực tế có thể cao hơn nhiều vì mỗi câu có câu hỏi, 4 đáp án, đáp án đúng, giải thích, source grounding, metadata và quality fields.

Ví dụ thực tế:

```txt
Actual Out = 14.868 tokens / 20 câu ≈ 743 tokens/câu
```

Nếu estimate vẫn dùng `320 tokens/câu`, cost sẽ bị thấp hơn thực tế.

## Cách sửa

Bản này thêm bảng:

```txt
ai_token_calibration
```

Bảng này lưu rolling average output tokens/câu theo:

```txt
model_name
course_id
difficulty
question_type
prompt_version
```

Estimate input vẫn dùng:

```txt
POST /v1/responses/input_tokens
```

Estimate output đổi sang:

```txt
estimated_output_tokens =
  easy_count   * avg_output_tokens_easy
+ medium_count * avg_output_tokens_medium
+ hard_count   * avg_output_tokens_hard
```

Nếu chưa có lịch sử, dùng default an toàn:

```txt
easy   = 650 tokens/câu
medium = 750 tokens/câu
hard   = 900 tokens/câu
mixed  = 750 tokens/câu
```

Sau mỗi job có actual usage, worker cập nhật calibration từ:

```txt
actual_output_tokens / completed_question_count
```

## UI/Analytics

Job Monitor hiển thị thêm:

```txt
Output/câu dự kiến
Output/câu thật
Output accuracy
Output delta tokens
```

Dashboard hiển thị thêm:

```txt
Output accuracy
Estimated output/question
Actual output/question
```

## Lưu ý

`Safe cost` vẫn nhân `safety_factor` để hard stop. `Actual cost` không nhân safety factor.
