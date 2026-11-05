# AI Server worker crash vì Kombu / redis-py lệch phiên bản

## Bằng chứng và nguyên nhân

Log production ngày 05/11/2026, namespace `openedx`, cả bốn deployment worker
interactive/sync-fast, heavy, bulk và analytics đều CrashLoopBackOff sau cập
nhật image `25.9.16.7.2.64.16.5.7.2.18-110-f617ba2d`. Exception kết thúc:

```text
VersionMismatch: Redis transport requires redis-py versions 6.1.0 or later. You have 5.2.1
```

`redis-py` là package Python trong AI Server, không phải Redis server dùng
chung với Open edX. Chưa có bằng chứng Redis server hỏng hoặc mất dữ liệu.
Container tên `worker` là đúng; lỗi kubectl exec trước đó là do container crash.

Runtime requirements đã pin Celery 5.4.0 / redis-py 5.2.1 nhưng để Kombu theo
range transitive của Celery (`>=5.3.4,<6.0`). Cài mới có thể chọn Kombu 5.7.0
với version gate không nhận redis-py 5.2.1. Đã tái hiện chính xác exception
trong môi trường local bằng bộ phiên bản đó. Log production chưa in số phiên
bản Kombu; không suy diễn phiên bản production như một số đo đã xác nhận.

## Sửa source chính thức

- `backend/requirements-runtime.txt`: pin thêm `kombu==5.4.2`, giữ Celery
  5.4.0 và redis-py 5.2.1. CI và Dockerfile production cùng đọc file này.
- `backend/app/tests/test_celery_redis_client_compatibility.py`: gọi version
  gate thật `Channel._get_client`, không mock, không kết nối Redis, không tạo/
  consume/publish task. Thất bại trước sửa và pass sau cài dependency đã pin.
- `scripts/ci-backend-tests.sh`: luôn chạy regression trên trong CI hiện hành.
- `backend/Dockerfile.prod`: sau cài wheel, chạy `pip check` và version gate
  Redis transport thật. Không cho image có dependency lỗi vượt qua build.
- Jenkins gọi `scripts/build-k8s-images.sh`, dùng `backend/Dockerfile.prod`;
  gate áp dụng lên dependency cài thực sự trong production image.

Không sửa Redis server, credentials, DB index, key prefix, TTL, queue hoặc
manifest CMS/Open edX. Không overlay package/PVC/PYTHONPATH hay cài nóng package
trong pod. Các phương án vận hành tạm chưa được thực hiện trên production và
không thuộc bản sửa được người dùng chọn.

## Kiểm chứng và triển khai

- Regression: trước sửa 1 failed với exception giống production; sau sửa pass.
- 20 test compatibility/queue routing/repair pass; `pip check` của venv ứng dụng
  sạch và lệnh gate trong Dockerfile pass.
- Tạo venv mới hoàn toàn, resolver cài Celery 5.4.0 / Kombu 5.4.2 / redis-py
  5.2.1 cùng dependencies; `pip check` và Redis client gate pass. Đây là kiểm
  tra compatibility local, không phải đo kết nối Redis production.
- Full suite: 312 failed/1.391 passed/16 skipped, cùng 312 tên lỗi so với
  baseline 1.390 passed. CI subset 490 passed; release contract 6 passed/
  1 deselected. Hai integration smoke PostgreSQL/Redis vẫn fail (14 skipped)
  vì local dùng SQLite không có alembic_version và thiếu REDIS_URL. Không coi
  toàn bộ CI tích hợp là pass. Ruff/diff và 12 repo-index tests đạt; review
  độc lập không phát hiện blocker về compatibility/build scope.
- Workspace không có Docker daemon/CLI để build image hoặc K8s access. Chưa
  có production rollout, chưa xác nhận worker phục hồi hay 8 Library đã cập nhật.
- Người vận hành build image backend từ nhánh nghiệp vụ sau commit này. Triển
  khai cùng image lên backend, beat và cả 4 worker, giữ nguyên cấu hình Redis.
  Xác minh worker Ready, không còn VersionMismatch và nhận task trên queue đúng.
- Sau khi worker phục hồi, chạy publish lại 8 Release WEB3023 bằng CLI đã có
  trong image mới hoặc luồng publish phù hợp. Cập nhật course copy từ Library
  riêng; không reset Quiz/điểm hoặc sửa job status để che lỗi.

Baseline source: `6bede597dc917d9b3d35dd3a5c35500281fcb1d6`. Đây là bản sửa
source chờ người vận hành build/deploy, không phải xác nhận runtime production.
