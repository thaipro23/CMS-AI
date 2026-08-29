# Frontend UI Audit v25.9.16.5.34

## Phạm vi đã kiểm

- `frontend/app/globals.css`
- `frontend/components/layout/AppShell.tsx`
- `frontend/app/bank/_components/pages/BankDashboardPage.tsx`
- Toàn bộ `frontend/app`, `frontend/components`, `frontend/context`, `frontend/lib`, `frontend/types` bằng grep loại trừ `node_modules` và `.next`.

## Kết quả kiểm chính

- Token canonical đã có đủ trong `globals.css`.
- Không còn hardcoded hex ngoài `globals.css` trong các thư mục frontend chính.
- Không còn `box-shadow` trong `frontend/app` và `frontend/components`.
- TypeScript typecheck pass.
- Python compile pass.
- Next dev server trả HTTP 200 cho `/bank`.

## Việc không khẳng định quá mức

- Chưa khẳng định `next build` pass trong sandbox vì bị timeout/EPIPE ở worker build stage.
- Cần xác nhận lại bằng Docker build trên UAT.
