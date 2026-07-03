# Context v25.9.16.5.90 — Sequential-only StudentModule Completion Fix

Bản v90 sửa gốc lỗi Course completion sai do StudentModule fallback lấy thừa dữ liệu.

## Dữ liệu thực tế

Course `course-v1:FPT+COM1071+SU26` có:

- `sequential = 8`
- `vertical = 8`
- `video = 5`
- `problem = 50`
- `itembank = 15`
- `non_container_blocks = 70`

CMS tính `duongddph69321 = 5/8 = 62.5% ≈ 63%`.

StudentModule:

- `duongddph69321`: `sequential=5`, `problem=10`, `video=1`, `itembank=15`.
- `tienpdph69628`: chỉ `itembank=15`, chưa có activity thật.

## Rule v90

Course completion fallback chỉ tính:

```text
completed_blocks = count(StudentModule module_type='sequential' có state.position > 0)
total_blocks = count(reachable sequential/subsection trong LMS course tree)
progress_percent = completed_blocks / total_blocks * 100
```

Không dùng:

- `itembank`
- `problem`
- `video`
- `non_container_blocks=70`
- raw StudentModule row count

## Lý do hiệu năng

Khi course có sequential/subsection, connector chỉ query `StudentModule(module_type='sequential')`, không đọc state của toàn bộ problem/itembank. Điều này giảm lag khi lớp đông và course có nhiều bank/problem.

## Kỳ vọng

- Học viên có 5 sequential rows → `5/8 = 62.5%`.
- Học viên chỉ có 15 itembank rows → `0/8 = 0%`.
- Không còn baseline `21.4% = 15/70`.
