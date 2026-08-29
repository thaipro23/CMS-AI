# v25.9.16.5.87 — StudentModule Activity-Only Progress Fix

Sửa lỗi Course completion false positive sau v86.

## Root cause

v86 đã dùng StudentModule fallback như sau:

```text
progress_percent = Count(StudentModule rows for learner in course) / total_blocks * 100
```

Với course có `total_blocks=70`, các số trên UI được sinh ra như sau:

```text
6 / 70 * 100 = 8.57%  -> 8.6%
13 / 70 * 100 = 18.57% -> 18.6%
15 / 70 * 100 = 21.43% -> 21.4%
```

Sai ở chỗ `StudentModule row` không đồng nghĩa `completed block`.

## Fix

StudentModule fallback chỉ đếm learner activity rows:

- Exclude container rows: `course`, `chapter`, `sequential`, `vertical`, `library_content`.
- Exclude empty state rows.
- Count rows with learner activity only: answers, submissions, correct_map, attempt state, grade, watched/video position, etc.

## Verify

See `RUN_V25_9_16_5_87.md`.
