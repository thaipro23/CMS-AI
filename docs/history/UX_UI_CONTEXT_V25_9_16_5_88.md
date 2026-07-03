# UX/UI + Learning Sync Context v25.9.16.5.88

Bản v88 sửa lỗi StudentModule fallback denominator.

## Vấn đề phát hiện từ màn hình thật

AI Server hiển thị:

- `8.6%` = `6 / 70 * 100`
- `18.6%` = `13 / 70 * 100`
- `21.4%` = `15 / 70 * 100`

Trong khi một số sinh viên chưa vào học.

Nguyên nhân: các bản trước dùng `total_blocks=70` từ course tree/content summary cũ hoặc non-container block count. Số này không phải mẫu số đúng cho Course completion fallback. Studio có thể hiển thị nhiều block vì tính cả section/subsection/unit/container hoặc LMS connector còn thấy block cũ do publish/cache.

## Rule mới

StudentModule fallback chỉ được tính khi:

- Có activity rows thật.
- Không tính state rỗng/default.
- Không tính container rows.
- Mẫu số chỉ là reachable leaf learning components.

Không tính vào mẫu số:

- course
- chapter
- sequential
- vertical
- library_content

Connector trả diagnostics:

- `student_module_denominator_rule`
- `student_module_denominator_source`
- `student_module_denominator_breakdown`
- `student_module_content_tree_breakdown`
- `student_module_content_tree_raw_reachable_blocks`
- `student_module_content_tree_non_container_blocks`
- `student_module_content_tree_leaf_blocks`

## Version active bắt buộc

LMS connector phải trả:

```text
CONNECTOR_VERSION=25.9.16.5.88
```

Nếu không đúng version thì phải restart LMS/CMS hoặc kiểm tra plugin override.
