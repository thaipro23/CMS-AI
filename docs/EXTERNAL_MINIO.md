# AI Server dùng MinIO chung ngoài Kubernetes

## Kiến trúc đã chốt

Production không chạy MinIO trong Kubernetes. AI Server kết nối qua S3 API tới
MinIO trên VM riêng `FPL-S3-SRV` (`10.205.194.48`) bằng endpoint có TLS:

```text
AI backend/worker pods -> https://s3.fpl.edu.vn -> MinIO VM 10.205.194.48
```

AI Server dùng bucket private riêng `ai-server`. Không ghi vào các bucket
`openedx*` của CMS và không dùng root credential của MinIO.

## 1. Tạo bucket và service account trên VM MinIO

Thực hiện bằng tài khoản quản trị MinIO. Không lưu credential thật vào Git:

```bash
mc alias set fpl-s3 https://s3.fpl.edu.vn "$MINIO_ADMIN_ACCESS_KEY" "$MINIO_ADMIN_SECRET_KEY"
mc mb --ignore-existing fpl-s3/ai-server
mc anonymous set none fpl-s3/ai-server
```

Policy tối thiểu cho AI Server (`ai-server-policy.json`):

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": ["s3:GetBucketLocation", "s3:ListBucket"],
      "Resource": ["arn:aws:s3:::ai-server"]
    },
    {
      "Effect": "Allow",
      "Action": ["s3:GetObject", "s3:PutObject", "s3:DeleteObject"],
      "Resource": ["arn:aws:s3:::ai-server/*"]
    }
  ]
}
```

```bash
mc admin policy create fpl-s3 ai-server-policy ai-server-policy.json
mc admin user add fpl-s3 ai-server-svc "$AI_SERVER_MINIO_SECRET_KEY"
mc admin policy attach fpl-s3 ai-server-policy --user ai-server-svc
```

## 2. Tạo Kubernetes Secret trước khi rollout

Chỉ backend và worker-heavy (các queue `generation,exports`) đọc secret riêng
`ai-server-minio`; worker sync/analytics/frontend không nhận credential MinIO.
Lệnh dưới đây không thay đổi secret `ai-server-env` hiện tại:

```bash
kubectl -n openedx create secret generic ai-server-minio \
  --from-literal=STORAGE_PROVIDER=minio \
  --from-literal=MINIO_ENDPOINT=https://s3.fpl.edu.vn \
  --from-literal=MINIO_BUCKET=ai-server \
  --from-literal=MINIO_ACCESS_KEY=ai-server-svc \
  --from-literal=MINIO_SECRET_KEY="$AI_SERVER_MINIO_SECRET_KEY" \
  --from-literal=MINIO_SECURE=true \
  --from-literal=MINIO_CERT_CHECK=true \
  --from-literal=MINIO_AUTO_CREATE_BUCKET=false \
  --dry-run=client -o yaml | kubectl apply -f -
```

Không đặt `MINIO_SECRET_KEY` trực tiếp trong manifest hoặc Jenkinsfile.

## 3. Kiểm tra DNS/TLS/S3 từ pod

Sau khi rollout image mới:

```bash
kubectl -n openedx exec deploy/ai-server-backend -- \
  python -c "import socket; print(socket.gethostbyname_ex('s3.fpl.edu.vn'))"

kubectl -n openedx exec deploy/ai-server-backend -- \
  python -c "from app.services.object_storage import get_object_storage; print(get_object_storage().health(write_test=True))"
```

Kết quả health phải có `status: ok`, `secure: true`, `bucket: ai-server` và
`write_test: true`. Lệnh smoke tạo một object tạm, đọc đối chiếu rồi xóa ngay;
không in access key hoặc secret.

Nếu DNS nội bộ chưa phân giải `s3.fpl.edu.vn`, sửa DNS nội bộ trỏ domain này về
đường vào MinIO VM có certificate hợp lệ. Không tắt `MINIO_CERT_CHECK` và không
hard-code IP vào source.

## 4. Rollout và xác minh

```bash
kubectl -n openedx apply -k deploy/k8s/base
kubectl -n openedx rollout status deploy/ai-server-backend --timeout=5m
kubectl -n openedx rollout status deploy/ai-server-worker-heavy --timeout=5m

kubectl -n openedx logs deploy/ai-server-backend --since=10m | grep -Ei 'storage|minio|error|exception' || true
kubectl -n openedx logs deploy/ai-server-worker-heavy --since=10m | grep -Ei 'storage|minio|error|exception' || true
```

UAT tối thiểu:

1. Upload một tài liệu Question Bank và chạy worker extract.
2. Xóa một tài liệu chưa được dùng, xác minh object bị xóa.
3. Import Udemy, tải file lỗi nếu có và chạy retry.
4. Export báo cáo Udemy và báo cáo giáo viên rồi tải lại qua API có RBAC.
5. Gọi `GET /api/health/storage`, sau đó `POST /api/health/storage/smoke` bằng
   tài khoản có quyền `manage_settings`.

## 5. Tương thích và rollback

- File mới lưu dưới URI `minio://ai-server/...`.
- Đường dẫn local cũ dưới `/app/.runtime` vẫn đọc và xóa được.
- Chưa migrate dữ liệu Batch 35/ACMS cũ.
- Giữ PVC `ai-server-runtime` trong giai đoạn đầu cho cache, file tạm,
  `runtime-settings.json` và khả năng rollback.
- Muốn tạm chuyển write mới về local, đổi `STORAGE_PROVIDER=local` trong secret
  rồi rollout lại. Các URI MinIO đã ghi vẫn đọc được khi credential còn tồn tại.

Chỉ xem xét bỏ PVC RWX sau khi UAT đầy đủ và có kế hoạch riêng cho các file
runtime không thuộc object storage.
