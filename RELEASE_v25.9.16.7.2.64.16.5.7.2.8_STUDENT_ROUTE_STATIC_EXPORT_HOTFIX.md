# v25.9.16.7.2.64.16.5.7.2.8 — Batch 35.3.1

## Mục tiêu

Khắc phục lỗi Next.js static export tại:

- `/student-management/cms`
- `/student-management/udemy`

## Nguyên nhân

Batch 35.3 đã tách component dùng chung sang:

`frontend/app/student-management/StudentManagementPlatformPage.tsx`

nhưng hai route mới vẫn import named export từ `../page`. File `student-management/page.tsx` không export named component đó, vì vậy giá trị render là `undefined` trong lúc prerender và `next build` kết thúc với `Export encountered errors`.

## Sửa lỗi

Hai route import trực tiếp từ `../StudentManagementPlatformPage` và có Suspense fallback riêng.

## Phạm vi

- Chỉ frontend route wrapper và regression test.
- Không đổi API, database, worker hoặc nghiệp vụ CMS/Udemy.
- Không có migration mới; Alembic head vẫn là `0057`.
