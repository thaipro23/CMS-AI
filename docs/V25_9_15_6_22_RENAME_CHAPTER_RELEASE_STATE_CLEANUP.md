# v25.9.15.6.22 - Rename Chapter Release State Cleanup Hotfix

Bản này xử lý case Chapter được đặt nhầm tên, publish lỗi vì trùng Library, rồi giáo viên đổi tên Chapter và publish lại.

## Problem

Release chưa publish thành công vẫn giữ `openedx_library_key` và component id lỗi từ lần publish trước. Khi Chapter đổi tên, key đúng phải đổi theo tên Chapter mới, nhưng backend vẫn dùng key cũ.

## Fix

- Cleanup stale release key when Chapter basic info changes.
- Cleanup stale release key again at publish time.
- Reset release-question component ids if library key changes before publish.
- Retry import once when Open edX raises LearningPackage missing.
- Connector normalizes `lib:ORG:Slug` to Open edX slug format before get/create/import.
- Add delete endpoint for failed/unpublished releases.
