# v25.9.12.7 - Force Problem Single Chunk

## Mục tiêu
Sửa dứt điểm trường hợp một quiz/problem cũ bị nhân thành hàng trăm chunks dù XML thật chỉ có khoảng 15 câu.

## Nguyên nhân thường gặp
- DB còn chunk cũ sinh từ parser/chunker lỗi.
- Người dùng chỉ xóa một block_id nhưng block problem hiện tại khác id.
- Problem XML có nhiều câu trong một block nên cần parse thành nội dung canonical, không chunk word-level như học liệu dài.

## Cách sửa
- Khi force sync, xóa toàn bộ chunks của các block `problem` trong course rồi rebuild lại từ Studio XML hiện tại.
- Mọi block `problem` được giữ thành 1 chunk nguồn sau khi parser đã canonicalize câu hỏi/đáp án.
- Sync fingerprint nâng lên v25.9.12.7 để ép rebuild khi nâng version.

## Kết quả mong đợi
Quiz 7.1 / `Trắc nghiệm cuối bài` từ khoảng 184 chunks / 405k tokens về 1 chunk / khoảng 1.8k tokens.
