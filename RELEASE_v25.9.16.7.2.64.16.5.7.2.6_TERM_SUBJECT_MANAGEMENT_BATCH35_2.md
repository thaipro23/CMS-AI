# v25.9.16.7.2.64.16.5.7.2.6 — Batch 35.2

## Mục tiêu

Khắc phục lỗi PostgreSQL tại `/api/academic/subject-deliveries` và sửa đúng nghiệp vụ Quản lý môn học:

- Màn **Quản lý môn học** chỉ lọc theo **Hệ + Học kỳ**.
- Một môn chỉ chọn `CMS`, `Udemy` hoặc `Chưa chọn` một lần trong học kỳ.
- Lựa chọn đó được ghi đồng thời vào mọi `academic_subject_deliveries` theo Block của môn.
- Lớp, kế hoạch Udemy, tiến độ, import và CMS/Open edX vẫn giữ nguyên phạm vi Block.

## Lỗi runtime đã sửa

PostgreSQL báo:

```text
psycopg.errors.GroupingError:
column "academic_classes.branch" must appear in the GROUP BY clause
```

Nguyên nhân là hai lần tạo `lower(coalesce(academic_classes.branch, ''))` sinh hai bind parameter khác nhau. Batch 35.2 dùng một biểu thức `class_branch_key` duy nhất với SQL literal an toàn cho cả `SELECT` và `GROUP BY`.

## Kế thừa sang kỳ mới

Khi refresh danh mục cho kỳ mới:

1. Tìm kỳ gần nhất trước kỳ đang chọn trong cùng Hệ.
2. Với từng môn, nếu mọi Block của kỳ trước cùng là CMS hoặc cùng là Udemy, kế thừa lựa chọn đó.
3. Nếu kỳ trước chưa chọn hoặc khác nhau giữa các Block, kỳ mới để `Chưa chọn`.
4. Chỉ kế thừa loại nền tảng; không sao chép kế hoạch, tiến độ, lớp, mapping hoặc lịch sử nghiệp vụ.
5. Refresh lại kỳ hiện tại không ghi đè lựa chọn đã sửa thủ công.

## Schema

- Không có migration mới.
- Alembic head giữ nguyên `0057_v25_9_16_7_2_64_35_udemy_hardening_indexes.py`.
- Identity dữ liệu vẫn là `subject_id + term_id + block_id + branch`.
