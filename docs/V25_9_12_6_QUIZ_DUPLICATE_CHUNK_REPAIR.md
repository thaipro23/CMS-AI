# v25.9.12.6 - Quiz Duplicate Chunk Repair

## Mục tiêu
Sửa trường hợp quiz/problem node hiển thị một nội dung bị nhân nhiều lần, dẫn đến chunk count và token count tăng bất thường (ví dụ 184 chunks cho một quiz cũ).

## Nguyên nhân
Một số dữ liệu chunk cũ được lưu từ phiên bản parser/chunker trước đó. Khi mã parser/chunker đã đổi nhưng raw content từ Open edX không đổi, sync cũ chỉ dựa trên `content_hash(item.content)` có thể không tự rebuild lại chunk như mong muốn.

## Cách sửa
- Bổ sung `sync fingerprint` có version + chunk policy để thay đổi code parser/chunker cũng làm invalid state sync.
- Nếu problem node hiện tại theo parser mới chỉ nên có 1 chunk nhưng DB vẫn còn nhiều chunk, sync sẽ tự xóa và rebuild ở lần đồng bộ kế tiếp.

## Kết quả mong đợi
Quiz như `Quiz 7.1` sẽ trở về đúng khoảng 1 chunk / ~1.8k tokens thay vì hàng trăm chunks/tokens bị nhân bản.
