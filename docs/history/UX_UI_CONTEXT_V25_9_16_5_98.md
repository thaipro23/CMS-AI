# UX/UI Context v25.9.16.5.98

Bản này không thêm UI lớn. Trọng tâm là ổn định production, contract dữ liệu và cache.

## Người dùng cuối

- Không thêm text kỹ thuật lên màn chi tiết lớp.
- Không bật diagnostics mặc định.
- `/jobs` và `/audit` giữ nguyên hướng v95: job là việc đang chạy; audit là đối soát thao tác.

## Vận hành admin

- Thêm script build/smoke để admin chạy sau deploy.
- Thêm health endpoint an toàn:
  - `/api/health/build`
  - `/api/health/openedx-connector/config`

## Completion rule cần giữ

```text
Course completion = StudentModule sequential có state.position / tổng reachable sequential
```

Không tính:

```text
itembank
problem
video
vertical
chapter
course
```

## Cache rule

Sau sync hoặc đổi mapping, Teacher Report Cache phải bị invalidate để màn Teacher Management không dùng cache cũ.
