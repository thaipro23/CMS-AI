# v25.9.15.3.1 - Version Isolation Carry-over Hotfix

## Nguyên tắc sửa

Bank Version v1 và v2 là hai bản độc lập hoàn toàn. v2 không thay thế v1.

- Câu dùng lại được: clone từ v1 sang v2, giữ `previous_question_id` và `lineage_root_question_id`.
- Câu không còn phù hợp: không sửa/retire câu ở v1; tạo snapshot `retired` trong v2 để audit rằng câu đó bị loại khỏi v2.
- Release/course đang dùng v1 không bị thay đổi.
- Release v2 chỉ lấy câu thuộc `bank_version_id = v2` và `status in approved/published`, `is_retired=false`.

## Thay đổi chính

- `retire_questions(bank_version_id=target_version_id, question_ids=source_question_ids)` giờ mutate/chèn dữ liệu trong target version.
- UI nút “Retire câu không còn phù hợp” gọi endpoint với `to_bank_version_id`, không gọi `from_bank_version_id` nữa.
- Câu retired snapshot có `status='retired'`, `is_retired=true`, `previous_question_id=<v1_question_id>`.

## Lý do

Nếu retire trực tiếp trong v1 thì release/course cũ có thể bị hiểu sai là bị loại câu sau khi đã publish. Versioning đúng phải coi mỗi Bank Version là snapshot riêng.
