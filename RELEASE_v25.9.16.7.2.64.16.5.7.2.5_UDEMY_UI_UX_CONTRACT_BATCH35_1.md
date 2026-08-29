# v25.9.16.7.2.64.16.5.7.2.5 — Batch 35.1 Udemy UI/UX Contract Closure

## Mục tiêu

Khép toàn bộ phát hiện trong audit UI/UX sau Batch 35, đưa các màn hình Subject Management/Udemy về cùng design contract enterprise của hệ thống mà không thay đổi nghiệp vụ CMS/Open edX hoặc chuyển dữ liệu ACMS cũ.

## Đã sửa

- Loại bỏ class màu riêng `udemy-action`; action chính dùng trực tiếp button token chung, đảm bảo tương phản và trạng thái hover/focus đồng nhất.
- Tab `Cảnh báo` luôn dùng phạm vi cảnh báo, không thể giữ filter `Đạt tiến độ` từ tab sinh viên.
- Tách `Tổng quan` thành overview vận hành thực sự, không lặp lại nguyên bảng tiến độ.
- Import và export dùng job notice persistent, polling đến trạng thái terminal, lưu job ID và tiếp tục sau F5.
- Chặn tạo job mới khi đang khôi phục job cũ; giữ khả năng thử lại đọc trạng thái và tải lại file export.
- Chuẩn hóa thông báo qua `InlineNotice`; loại bỏ notice Udemy viết riêng.
- Chuyển lịch sử import, lịch sử kế hoạch và kết quả import sang `EnterpriseDataTable`, có STT, caption, empty/error state và table viewport cuộn ngang.
- Hoàn thiện ARIA tab/tab-panel, keyboard navigation, progressbar semantics và label form.
- Chuẩn hóa wording thành `file tổng hợp tiến độ 7 cột`, không mô tả đây là chức năng chuyển dữ liệu ACMS.
- Bổ sung Playwright contract cho 1440/1366/1024/768/390 px, alert semantics, contrast, job recovery và mobile dialog.

## Phạm vi không thay đổi

- Không có migration mới; Alembic head vẫn là `0057_v25_9_16_7_2_64_35`.
- Không có ACMS importer/backfill/mapping tool.
- Không thay đổi API, database schema, Celery routing hoặc Open edX connector.
- Không reset database/volume và không sửa tay `alembic_version`.

## Dịch vụ cần deploy

Chỉ cần build/recreate `frontend`. Backend source runtime không thay đổi; file backend mới chỉ là regression test. Có thể recreate backend nếu quy trình release yêu cầu đồng bộ `/api/health/build`, nhưng không cần migration.
