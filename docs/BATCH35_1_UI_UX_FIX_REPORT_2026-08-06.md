# Báo cáo khép audit UI/UX — Batch 35.1

**Phiên bản:** `v25.9.16.7.2.64.16.5.7.2.5`  
**Ngày:** 06/08/2026  
**Baseline:** Batch 35 `.2.4`

## Kết luận

Các lỗi chặn release đã được sửa ở mức source. Giao diện Udemy hiện dùng cùng AppShell, action hierarchy, notice, tab, table, modal và responsive contract với hệ thống enterprise. Runtime acceptance vẫn cần production build và browser UAT thật.

## Đối chiếu phát hiện và cách sửa

| Phát hiện audit | Trạng thái | Cách sửa |
|---|---|---|
| Nút Udemy sai tương phản | Đã sửa | Xóa `udemy-action`; dùng `.btn` design token chung; CSS route chuyển sang token có fallback. |
| Tab Cảnh báo giữ `on_track` | Đã sửa | `effectiveStatus` ép về `alerts`; option `Đạt tiến độ` bị loại khỏi tab; reset state khi chuyển tab. |
| Import đóng modal và reload một lần | Đã sửa | Modal giữ mở sau queue; job ID lưu localStorage; polling persistent; F5 resume; dashboard reload khi terminal. |
| Chưa có browser contract Udemy | Đã bổ sung | Playwright cover contrast, ARIA tab, alert semantics, job resume, mobile dialog và 5 viewport bắt buộc. |
| Notice không đồng nhất | Đã sửa | Dùng `InlineNotice` và `PersistentJobNotice`; loại bỏ notice custom. |
| Bảng phụ là raw table | Đã sửa phần hiển thị | Lịch sử import, lịch sử kế hoạch, preview/error/result dùng `EnterpriseDataTable`. Bảng soạn milestone vẫn là editable grid có caption, STT, label và table viewport. |
| Tab thiếu panel semantics | Đã sửa | `id`, `aria-controls`, `aria-labelledby`, `role=tabpanel`, keyboard Arrow/Home/End. |
| Progress thiếu semantics | Đã sửa | `role=progressbar`, min/max/now; job dùng native `<progress>`. |
| Tổng quan trùng bảng sinh viên | Đã sửa | Overview riêng về roster coverage, cảnh báo, plan và dữ liệu mới nhất. |
| Export polling có thể tạo job trùng | Đã sửa | Disable action trong active/recovery state; retry đọc đúng job ID; validate job type/delivery. |
| Download lỗi làm mất đường retry | Đã sửa | Giữ completed job và localStorage; hiển thị `Tải lại file`. |
| Wording ACMS gây hiểu nhầm | Đã sửa | Dùng `file tổng hợp tiến độ 7 cột`; không có chức năng chuyển dữ liệu ACMS. |
| CSS route dùng màu trực tiếp | Đã giảm thiểu | Chuyển màu của stylesheet Subject/Udemy sang design token có fallback; không override `.btn`. |

## Kiểm tra

- Regression Batch 31–35.1: **32 passed**.
- TS/TSX syntax: **9 file PASS**.
- Cross-file TypeScript check bằng external-module stubs: PASS.
- CSS/JSON/YAML/version/schema contracts: PASS.
- Next production build và Playwright runtime: chờ UAT vì npm gateway môi trường đóng gói thiếu package.

## Gate nghiệm thu

Source acceptance: **PASS**.  
Production browser acceptance: **PENDING UAT EVIDENCE**.
