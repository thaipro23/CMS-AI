# v24.7 - Token Estimate / Work Item Fix

## Lỗi đã sửa

Ở bản cũ, khi giáo viên chọn nhiều chunks/nodes, UI có thể hiển thị tổng content chỉ khoảng 1.552 tokens nhưng Estimate trả về input rất lớn, ví dụ 127.173 tokens.

Nguyên nhân: backend tạo nhiều `work_items` cho node coverage nhưng mỗi work item lại gửi toàn bộ `plan.content` vào prompt. Nếu chọn 29 chunks/nodes thì prompt full content bị tính/lặp 29 lần.

## Logic mới

- Nếu giáo viên chọn `chunk_ids` trực tiếp, backend không chia một model call cho từng chunk. Backend dùng batch bình thường trên đúng các chunks đã chọn.
- Nếu giáo viên chọn `node_ids`, backend mới dùng Node Coverage.
- Khi dùng Node Coverage, mỗi model call chỉ nhận content của node đó và các chunk con của node đó, không nhận toàn bộ selected content.
- Estimate và Worker dùng cùng `work_items`, nên số token estimate gần với số token thực tế hơn.

## Token source debug

`token_source` không còn chỉ ghi chung chung `local_tiktoken_fallback`, mà ghi rõ lý do:

- `responses/input_tokens`: đã dùng OpenAI `/v1/responses/input_tokens` thật.
- `local_tiktoken_fallback_mock_llm_enabled`: đang bật mock LLM.
- `local_tiktoken_fallback_missing_api_key`: thiếu API key trong runtime settings.
- `local_tiktoken_fallback_api_mode_chat_legacy`: đang để chat legacy, không dùng Responses API.
- `local_tiktoken_fallback_after_input_tokens_XXX`: đã gọi endpoint đếm token nhưng OpenAI trả lỗi HTTP XXX.

## Ghi chú

Content token trong UI là token của nội dung học liệu. Estimate input token luôn cao hơn vì có thêm system instruction, question policy, JSON schema, metadata, source grounding instruction và output projection. Nhưng với bản v24.7, nó không còn bị nhân sai do lặp full content cho từng chunk/node.
