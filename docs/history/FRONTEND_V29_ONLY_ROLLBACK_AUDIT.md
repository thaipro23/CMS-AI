# Frontend v29 Only Rollback Audit

## Kết luận

Bản v37 được dựng bằng cách lấy baseline v36 rồi thay duy nhất thư mục `frontend/` bằng frontend của v29.

## Kiểm chứng đã chạy trong sandbox

### 1. Frontend v37 giống nguyên frontend v29

```bash
diff -qr /mnt/data/src_v29/ai-server-openedx-v25.9.16.5.29-local-operation-feedback-ux/frontend \
         /mnt/data/build_v37/ai-server-openedx-v25.9.16.5.37-ai-frontend-v29-only-rollback/frontend
```

Kết quả: không có output, nghĩa là `frontend/` v37 giống `frontend/` v29.

### 2. Các thư mục không phải frontend giữ nguyên baseline v36

Đã so sánh các thư mục:

```text
backend
docs
frontend-app-learning-patch
infra
openedx-connector-plugin
openedx-unit-reset-plugin
scripts
tutor-plugins
```

Kết quả: tất cả giống baseline v36.

### 3. Python compile

```bash
python3 -m compileall -q backend/app backend/alembic/versions openedx-connector-plugin/openedx_ai_connector openedx-unit-reset-plugin/openedx_unit_reset
```

Kết quả: OK.

### 4. Frontend typecheck

```bash
cd frontend
npm ci --ignore-scripts --no-audit --no-fund
npm run --silent typecheck
```

Kết quả: OK.

## Ghi chú trung thực

- Chưa claim `next build` pass trong sandbox.
- Bản này không sửa lại UI mới, chỉ phục hồi frontend AI Server về đúng v29 theo yêu cầu.
- Không đổi backend, worker, plugin, MFE patch, infra, scripts.
