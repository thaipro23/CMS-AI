# UX/UI Context v25.9.16.7.2.50

Bản `.43` tập trung vào UX vận hành cho Production Readiness trong `/analytics/learning`.

## Vấn đề cũ

Banner cũ chỉ nói:

```text
Production readiness · Chưa sẵn sàng production · Cần xử lý trước production: 1 blocker, 3 cảnh báo
```

Nhưng không cho người vận hành biết blocker cụ thể là gì.

## UX mới

Panel mới:

- Hiển thị trạng thái tổng: `Sẵn sàng production`, `Có thể pilot, còn cảnh báo`, `Chưa sẵn sàng production`.
- Hiển thị counters: `n blocker`, `n cảnh báo`.
- Nếu có blocker, hiển thị `Blocker chính` ngay trong panel.
- Hiển thị tối đa 5 issue quan trọng gồm: severity, category, code, message, action.
- Không làm page tràn ngang.
- Không dùng wording kết luận `gian lận`, `cheating`, `vi phạm chắc chắn`.

## CSS chính

```text
.analytics-production-readiness-panel
.analytics-readiness-head
.analytics-readiness-counters
.analytics-primary-blocker
.analytics-readiness-issue-list
.analytics-readiness-issue
```
