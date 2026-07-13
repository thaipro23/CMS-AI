# v25.9.16.7.2.64.12 — Enterprise Navigation + DataTable UX Foundation

## Bank hierarchy chuẩn

```text
Bộ môn → Môn học → Phiên bản môn theo học kỳ → Bài/Chapter → Câu hỏi
```

- Mỗi môn chỉ có một phiên bản cuối trong một học kỳ.
- Release là snapshot/chốt bộ đề của Chapter.
- Quiz/Final test là workflow xuất bản sau Bank.
- Release và Quiz không phải node điều hướng trong cây Bank.

## Thay đổi

- Sidebar nhóm: Tổng quan, Ngân hàng câu hỏi, Đào tạo, Vận hành & quản trị.
- `Breadcrumbs` dùng chung và clickable.
- `EnterpriseDataTable` với density, sticky columns, column visibility, pagination và table states.
- `useUrlTableState` lưu search/filter/page/page_size/density vào URL.
- `/bank/departments` là màn đầu tiên áp dụng foundation.
- Backend chặn tạo hoặc đổi sang phiên bản môn trùng học kỳ trong cùng môn.

## Migration

Không có migration mới. Latest vẫn là `0052_v25_9_16_7_2_27_learning_behavior_logic_calibration.py`.
