# v25.9.15.6.3 - Bank UI Delete + Popup + 100 Question Limit Hotfix

## Nội dung sửa

- Sửa lỗi xóa tài liệu: backend thiếu `_require_mutable_bank_version`, gây lỗi `VersionedQuestionBankService object has no attribute _require_mutable_bank_version`.
- Popup/modal của các màn hình Bank được làm lại ổn định hơn, z-index cao hơn, có padding/scroll rõ ràng.
- Mặc định mỗi Chapter/Bài tối đa 100 câu hỏi.
- Backend chặn tạo câu hỏi vượt 100 câu/chapter.
- UI bỏ ô nhập chỉ tiêu câu hỏi; hệ thống tự dùng 100 câu/bài.
- Bỏ 2 khối riêng "3. Kiểm tra thay đổi" và "4. Chốt Release" khỏi workspace.
- Đưa 2 nút chính lên bên trên: "Kiểm tra thay đổi" và "Chốt bộ đề/Publish Library".

## File chính đã sửa

- backend/app/services/question_bank_service.py
- backend/app/schemas/question_bank.py
- frontend/app/bank/_components/BankPages.tsx
- frontend/app/globals.css

## Test

- Python compileall: PASS
- npm ci --ignore-scripts: PASS
- npm run typecheck: PASS
- npm run build: compiled successfully, timeout ở bước cuối lint/type validation trong môi trường artifact.
