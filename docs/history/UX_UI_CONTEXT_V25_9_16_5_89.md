# UX/UI + Sync Context v25.9.16.5.90

Bản v89 sửa tiếp lỗi completion fallback để khớp CMS/Course Home.

Nghiệp vụ đã chốt:
- CMS đang tính `duongddph69321 = 5/8 = 62.5% ≈ 63%`.
- AI Server phải ưu tiên Course Home official completion nếu lấy được.
- Nếu phải fallback StudentModule, không chia theo raw course tree `70`.
- Không đếm raw StudentModule rows.
- Fallback phải gom activity rows về nearest visible learning unit/subsection.

Sửa kỹ thuật:
- Connector `CONNECTOR_VERSION = 25.9.16.5.90`.
- Denominator ưu tiên count reachable `sequential` blocks.
- Numerator count distinct parent subsections có activity thật.
- Example đúng: 5 completed units / 8 total units = 62.5%.

Diagnostics quan trọng:
- `student_module_subsection_total`
- `student_module_leaf_eligible_total`
- `student_module_raw_activity_rows`
- `student_module_activity_blocks`
- `student_module_activity_unit_keys_sample`
- `student_module_completion_unit_keys_sample`
- `student_module_component_to_completion_unit_count`

Sau deploy bắt buộc restart LMS/CMS và check:
`CONNECTOR_VERSION=25.9.16.5.90`.
