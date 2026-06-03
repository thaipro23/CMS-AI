# Mức 1: Open edX riêng, AI Server riêng container, cùng server/cùng Docker network

Mục tiêu của bản này: giữ Tutor/Open edX nguyên trạng, chạy AI Server bằng `docker-compose.prod.yml` riêng, cho AI Server join network Docker của Tutor và để Caddy/Nginx reverse proxy vào AI Server. Không nhét backend/frontend AI vào container CMS.

## 1. Kiểm tra network Tutor

Trên server đang chạy Tutor:

```bash
docker network ls | grep tutor
```

Thông thường network là:

```text
tutor_local_default
```

Nếu khác, đặt trong `.env.production`:

```env
OPENEDX_SHARED_NETWORK=<ten_network_tutor>
```

## 2. Tạo `.env.production`

```bash
cp .env.production.example .env.production
./scripts/generate-secrets.sh
nano .env.production
```

Các giá trị quan trọng cho mô hình này:

```env
OPENEDX_SHARED_NETWORK=tutor_local_default
NEXT_PUBLIC_API_BASE_URL=https://api-ai.cms-test.poly.edu.vn
NEXT_PUBLIC_OPENEDX_CMS_BASE_URL=https://scms-test.poly.edu.vn
CORS_ALLOWED_ORIGINS=https://ai.cms-test.poly.edu.vn,https://cms-test.poly.edu.vn,https://scms-test.poly.edu.vn,https://app.cms-test.poly.edu.vn,https://apps.cms-test.poly.edu.vn
USE_MOCK_OPENEDX=false
MOCK_LLM=false
AUTH_MODE=openedx_sso
ALLOW_DEMO_ROLE_HEADER=false
OPENEDX_CMS_BASE_URL=https://scms-test.poly.edu.vn
OPENEDX_LMS_BASE_URL=https://cms-test.poly.edu.vn
OPENEDX_OAUTH_BASE_URL=https://cms-test.poly.edu.vn
```

Không để sót placeholder:

```bash
grep -n "CHANGE_ME" .env.production
```

Lệnh trên không được in ra dòng nào.

## 3. Cấu hình CMS connector secret trong Tutor

Dùng cùng một secret cho AI backend và CMS plugin:

```env
OPENEDX_CONNECTOR_HMAC_SECRET=<secret_64_hex>
AI_CONNECTOR_HMAC_SECRET=<secret_64_hex>
```

Chạy script có sẵn:

```bash
./scripts/tutor-ai-connector-override.sh '<OPENEDX_CONNECTOR_HMAC_SECRET>' 'admin' 'scms-test.poly.edu.vn,cms-test.poly.edu.vn,app.cms-test.poly.edu.vn,apps.cms-test.poly.edu.vn'
tutor local restart cms cms-worker
```

Kiểm tra trong CMS container:

```bash
docker exec -it tutor_local-cms-1 bash -lc 'env | grep AI_CONNECTOR'
```

## 4. Chạy AI Server

```bash
docker compose -f docker-compose.prod.yml --env-file .env.production down --remove-orphans
docker compose -f docker-compose.prod.yml --env-file .env.production build --no-cache
docker compose -f docker-compose.prod.yml --env-file .env.production up -d
```

Lưu ý: `docker-compose.prod.yml` bản này dùng `expose`, không publish `8000:8000` hay `3000:3000` ra host. Bên ngoài chỉ đi qua reverse proxy.

Kiểm tra container:

```bash
docker ps --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"
```

Kỳ vọng thấy `ai-backend`, `ai-frontend`, `ai-worker`, `ai-postgres`, `ai-redis` đều `Up`. Port của `ai-backend` và `ai-frontend` không được public ra `0.0.0.0`.

## 5. Reverse proxy bằng Tutor Caddy

Cách khuyến nghị nếu Tutor Caddy đang giữ port 80/443.

Cài plugin Caddy proxy:

```bash
cp tutor-plugins/ai_server_reverse_proxy.py "$(tutor plugins printroot)/ai_server_reverse_proxy.py"
tutor plugins enable ai_server_reverse_proxy
tutor config save \
  --set AI_SERVER_FRONTEND_HOST=ai.cms-test.poly.edu.vn \
  --set AI_SERVER_API_HOST=api-ai.cms-test.poly.edu.vn \
  --set AI_SERVER_FRONTEND_UPSTREAM=ai-frontend:3000 \
  --set AI_SERVER_API_UPSTREAM=ai-backend:8000
tutor local restart caddy
```

Nếu Tutor bản của bạn không nhận patch `caddyfile`, dùng nội dung trong:

```text
infra/reverse-proxy/Caddyfile.ai-server
```

và gắn vào Caddyfile hiện tại theo cách bạn đang quản lý Caddy.

## 6. Reverse proxy bằng Nginx ngoài

Chỉ dùng khi Nginx là proxy chính giữ port 80/443. Không chạy Nginx chiếm port 80/443 nếu Tutor Caddy đang giữ port đó.

Mẫu config nằm ở:

```text
infra/reverse-proxy/nginx.ai-server.conf
```

Nginx container cũng phải join cùng network `tutor_local_default`, nếu không nó sẽ không resolve được `ai-frontend` và `ai-backend`.

## 7. Kiểm tra network và health

Chạy script:

```bash
./scripts/check-level1-network.sh
```

Hoặc test tay:

```bash
docker exec tutor_local-caddy-1 sh -lc 'wget -qO- http://ai-backend:8000/api/health'
docker exec tutor_local-caddy-1 sh -lc 'wget -qO- http://ai-frontend:3000 | head -c 200'
```

Test qua domain:

```bash
curl -i https://api-ai.cms-test.poly.edu.vn/api/health
curl -I https://ai.cms-test.poly.edu.vn
```

## 8. Điểm quan trọng

AI Server và Open edX vẫn là hai hệ thống riêng. AI backend gọi Open edX qua OAuth/HMAC connector. Frontend AI gọi API qua `https://api-ai.cms-test.poly.edu.vn`. Không để frontend gọi `http://localhost:8000` trên production.

Database AI (`ai-postgres`) tách riêng với MySQL/Mongo của Tutor. Redis AI (`ai-redis`) cũng tách riêng với Redis Tutor để lỗi worker AI không kéo sập LMS/CMS.
