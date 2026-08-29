# UX/UI Context v25.9.16.7.2.11

Bản này không đổi UI lớn. Thay đổi nằm ở cấu hình AP subject discovery:

- Người vận hành hiện chỉ cần để env:
  - `ACADEMIC_AP_CMS_GET_SUBJECT_ENDPOINT=/api/cms/get-subject-cms?campus_code=ph&term_name=`
- Backend tự điền kỳ vào `term_name`.
- Không dùng campus đang chọn ở UI để thay query `campus_code`; `campus_code=ph` là yêu cầu tạm thời của AP và được kiểm soát bằng env.
- Khi AP bỏ yêu cầu này, sửa env thành `/api/cms/get-subject-cms?term_name=` mà không cần sửa code.

Cache danh sách môn đã được tách theo endpoint template để tránh dùng nhầm cache cũ theo campus `ph` sau khi đổi env.
