# v25.9.16.5.83 — Assignment Defense Workflow + Correct CMS Sync CTA

## Mục tiêu

Sửa lại đúng nghĩa nghiệp vụ ở màn chi tiết lớp và nâng popup nhập điểm Assignment thành workflow vận hành bảo vệ.

## Thay đổi chính

### 1. Correct CMS sync wording

- Nút chính giữ đúng nghiệp vụ: **Đồng bộ full CMS**.
- Đồng bộ full CMS vẫn chạy đủ luồng:
  - kiểm tra/tạo tài khoản CMS,
  - kiểm tra enroll Course CMS,
  - lấy Course completion và điểm số mới nhất.
- Nút phụ đổi thành **Cập nhật điểm**.
- **Cập nhật điểm** chỉ chạy `learning_sync`, không tạo tài khoản và không enroll.

### 2. Assignment Defense Workflow

Màn chi tiết lớp có nút **Workflow Assignment** cho người có quyền `manage_assignment_scores`.

Workflow hỗ trợ:

- trạng thái bảo vệ:
  - Chưa có điểm,
  - Đã nộp,
  - Chờ bảo vệ,
  - Đã chấm,
  - Vắng bảo vệ,
  - Cần chấm lại;
- summary nhanh theo trạng thái;
- lọc theo trạng thái;
- chuyển nhanh trạng thái cho danh sách đang lọc;
- nút row-level: Chờ BV / Đã chấm / Vắng;
- validate frontend: trạng thái **Đã chấm** bắt buộc có điểm `/10`;
- backend validate lại: không cho lưu `graded` nếu thiếu điểm;
- `absent` và `not_graded` tự xóa điểm để tránh hiểu nhầm là đã chấm;
- backend ghi audit và giữ history ngắn trong `metadata_json`.

### 3. RBAC giữ nguyên

Backend vẫn chặn thật:

- `SYSTEM_ADMIN` được lưu điểm Assignment.
- `CAMPUS_MANAGER` đúng cơ sở được lưu điểm Assignment.
- Các role bộ môn/người duyệt/giảng viên thường không tự động có quyền nhập điểm Assignment.

## File chính đã sửa

- `frontend/app/student-management/classes/[classId]/page.tsx`
- `frontend/app/teacher-management/classes/[classId]/page.tsx` dùng lại màn chi tiết lớp nên hưởng toàn bộ sửa đổi.
- `frontend/app/globals.css`
- `backend/app/api/routes/academic.py`
- `frontend/components/layout/AppShell.tsx`
- `frontend/package.json`
- `frontend/package-lock.json`

## Kiểm tra

```bash
npm --prefix frontend run typecheck
python3 -m compileall -q backend/app
DATABASE_URL=sqlite+pysqlite:///:memory: pytest -q backend/app/tests/test_training_policy_service.py backend/app/tests/test_v25_9_16_5_75_training_management_scale.py
```

Kết quả trong sandbox:

- frontend typecheck: pass
- backend compile: pass
- training policy/scale tests: 11 passed, 1 skipped
- Next production build: compiled successfully + type/lint pass, nhưng sandbox timeout ở bước generate static pages; kiểm tra lại bằng Docker build trên server thật.
