# v25.9.13.50 - CMS Callback Suspense Fix

Sửa lỗi Next.js production build ở `/auth/cms-callback`: `useSearchParams()` phải nằm trong Suspense boundary.

Thay đổi chính:
- Tách callback page thành `CmsCallbackContent`.
- Bọc bằng `<Suspense fallback={...}>`.
- Giữ nguyên luồng auto CMS session login của v25.9.13.49.
