# Gửi mail nhắc sinh viên chậm tiến độ

Tính năng này dành cho giảng viên ở màn **Chi tiết lớp CMS**. AI Server xác định sinh viên còn trễ mốc Quiz, cho giảng viên chọn người nhận và sửa nội dung, sau đó gửi qua **Mail Send API**.

AI Server **không kết nối SMTP trực tiếp** và giảng viên không cần nhập tài khoản mail. Quản trị viên chỉ cấu hình một `ProxyKey` ở backend và `worker-heavy`.

## Luồng nghiệp vụ

1. Giảng viên bấm **Gửi nhắc tiến độ**.
2. Giao diện chỉ hiển thị email đã che và mặc định chọn người đang trễ Quiz, chưa đạt 100%.
3. Khi xác nhận gửi, job cập nhật tiến độ CMS của cả lớp một lần nữa.
4. Sinh viên vừa bắt kịp, thiếu email, inactive, trùng email hoặc chưa có dữ liệu CMS mới sẽ tự bị loại.
5. Worker tạo Mail Send session và lưu `sessionId` ngay, sau đó theo dõi đến trạng thái cuối.
6. Chỉ khi Mail Send trả `COMPLETED`, AI Server mới hiển thị hoàn tất và số lượng đã gửi/lỗi.

Deadline Quiz trong luồng này chỉ là **mốc nhắc tiến độ**, không phải kết luận cấm thi. Việc xét điều kiện thi vẫn theo ngày học cuối chính thức.

## Hợp đồng Mail Send

- Tạo session: `POST https://mailsend.poly.edu.vn/api/proxy/bulk-sessions/with-files`
- Xác thực: header `X-API-Key: <ProxyKey>`
- Nội dung: `multipart/form-data`
- Trường: `subject`, `bodyTemplate`, và một hoặc nhiều `sourceTo.inlineEmails`
- Kết quả tạo: HTTP `202`, JSON có `sessionId`
- Xem trạng thái: `GET https://mailsend.poly.edu.vn/api/proxy/bulk-sessions/{sessionId}`
- Trạng thái cuối: `COMPLETED`, `FAILED`, `CANCELLED`
- Giới hạn mặc định: 1.000 người/session

Template mặc định dùng `{{maHs}}` để Mail Send cá nhân hóa mã sinh viên. AI Server không ghi `ProxyKey` hoặc địa chỉ email thật vào audit/job result.

## Biến môi trường

```dotenv
MAILSEND_ENABLED=true
MAILSEND_PROXY_BASE_URL=https://mailsend.poly.edu.vn
MAILSEND_PROXY_CREATE_PATH=/api/proxy/bulk-sessions/with-files
MAILSEND_PROXY_STATUS_PATH=/api/proxy/bulk-sessions/{session_id}
MAILSEND_PROXY_API_KEY=REPLACE_WITH_PROXY_KEY
MAILSEND_REQUEST_TIMEOUT_SECONDS=30
MAILSEND_POLL_INTERVAL_SECONDS=3
MAILSEND_POLL_TIMEOUT_SECONDS=600
MAILSEND_MAX_RECIPIENTS=1000
ACADEMIC_PROGRESS_EMAIL_RATE_LIMIT_PER_MINUTE=3
```

Chỉ `MAILSEND_ENABLED` và `MAILSEND_PROXY_API_KEY` là bắt buộc nếu dùng endpoint mặc định. Không commit `ProxyKey` vào Git.

## Cài trên Kubernetes

Các deployment hiện đọc Secret `ai-server-env`. Lệnh dưới đây cập nhật đúng các khóa Mail Send mà không thay thế các khóa đang có. Máy chạy lệnh cần `jq` và `kubectl`.

```bash
export AI_SERVER_NAMESPACE=openedx

kubectl -n "$AI_SERVER_NAMESPACE" get secret ai-server-env >/dev/null

read -rsp 'Nhập Mail Send ProxyKey: ' MAILSEND_PROXY_KEY
echo
export MAILSEND_PROXY_KEY

jq -n --arg key "$MAILSEND_PROXY_KEY" '{
  stringData: {
    MAILSEND_ENABLED: "true",
    MAILSEND_PROXY_BASE_URL: "https://mailsend.poly.edu.vn",
    MAILSEND_PROXY_CREATE_PATH: "/api/proxy/bulk-sessions/with-files",
    MAILSEND_PROXY_STATUS_PATH: "/api/proxy/bulk-sessions/{session_id}",
    MAILSEND_PROXY_API_KEY: $key,
    MAILSEND_REQUEST_TIMEOUT_SECONDS: "30",
    MAILSEND_POLL_INTERVAL_SECONDS: "3",
    MAILSEND_POLL_TIMEOUT_SECONDS: "600",
    MAILSEND_MAX_RECIPIENTS: "1000",
    ACADEMIC_PROGRESS_EMAIL_RATE_LIMIT_PER_MINUTE: "3"
  }
}' | kubectl -n "$AI_SERVER_NAMESPACE" patch secret ai-server-env --type merge --patch-file /dev/stdin

unset MAILSEND_PROXY_KEY

kubectl -n "$AI_SERVER_NAMESPACE" rollout restart deployment/ai-server-backend deployment/ai-server-worker-heavy
kubectl -n "$AI_SERVER_NAMESPACE" rollout status deployment/ai-server-backend --timeout=180s
kubectl -n "$AI_SERVER_NAMESPACE" rollout status deployment/ai-server-worker-heavy --timeout=180s
```

Nếu namespace thực tế không phải `openedx`, chỉ thay dòng `AI_SERVER_NAMESPACE`.

Kiểm tra worker đang nghe queue `exports`:

```bash
kubectl -n "$AI_SERVER_NAMESPACE" logs deployment/ai-server-worker-heavy --tail=200 | grep -E 'generation,exports|ready'
```

## Cài bằng Docker Compose

Điền các biến ở trên vào `.env.production`, rồi chạy:

```bash
docker compose -f docker-compose.prod.yml up -d --force-recreate backend worker-heavy
docker compose -f docker-compose.prod.yml ps backend worker-heavy
docker compose -f docker-compose.prod.yml logs --tail=100 backend worker-heavy
```

## Kiểm thử nghiệm thu an toàn

1. Dùng một lớp UAT chỉ có tài khoản/email thử nghiệm.
2. Mở chi tiết lớp và bấm **Gửi nhắc tiến độ**.
3. Kiểm tra email trên UI đã được che; chọn đúng một tài khoản thử nghiệm.
4. Gửi và theo dõi thanh trạng thái tới `Hoàn tất`.
5. Đối chiếu `sentCount`, `failedCount` và email nhận được.
6. Cho sinh viên hoàn thành Quiz rồi gửi lại preview; sinh viên đó không còn trong nhóm cần nhắc.

Không thử lần đầu bằng toàn bộ sinh viên thật. Nếu UI báo `MAILSEND_NOT_CONFIGURED`, kiểm tra Secret và restart cả `backend` lẫn `worker-heavy`. Nếu job dừng ở trạng thái Mail Send, kiểm tra kết nối từ pod tới `mailsend.poly.edu.vn` và tình trạng dịch vụ Mail Send.

## Endpoint AI Server

- `GET /api/academic/classes/{class_id}/progress-email/preview`
- `POST /api/academic/classes/{class_id}/progress-email/jobs`
- `GET /api/academic/bulk-operation-jobs/{job_id}`

Giảng viên chỉ truy cập được lớp thuộc phạm vi phân công/RBAC của mình. Gửi chạy nền, có chống bấm lặp, rate limit và audit theo người tạo job.
