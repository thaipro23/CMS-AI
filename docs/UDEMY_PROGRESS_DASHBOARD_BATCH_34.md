# Batch 34 — Dashboard, cảnh báo, export và tích hợp vận hành Udemy

## 1. Mục tiêu

Batch 34 tiếp nối Batch 31–33 và hoàn thiện lớp khai thác dữ liệu Udemy cho người dùng nghiệp vụ:

- Mở một workspace riêng cho từng môn Udemy.
- Theo dõi tổng quan, tiến độ sinh viên, cảnh báo, kế hoạch và lịch sử import.
- Xuất Excel đúng theo bộ lọc và đúng phạm vi phân quyền.
- Tích hợp số liệu Udemy vào trang chi tiết lớp và Quản lý giảng viên.
- Không để lớp Udemy bị hiểu nhầm là lớp CMS thiếu Course, chưa enroll hoặc chưa đồng bộ Open edX.

Batch này không thay đổi cấu trúc cơ sở dữ liệu và không có Alembic migration.

## 2. Route người dùng

### 2.1. Dashboard môn Udemy

```text
/subject-management/{subjectDeliveryId}/udemy
```

Từ `/subject-management`, môn đã chọn nền tảng Udemy có nút **Xem tiến độ**.

Workspace gồm các tab:

1. **Tổng quan** — KPI và danh sách tiến độ hiện tại.
2. **Sinh viên** — tìm kiếm, lọc lớp và lọc trạng thái.
3. **Cảnh báo** — chậm tiến độ, chưa có mốc đến hạn, chưa khớp AP, mơ hồ hoặc ngoài roster.
4. **Lịch sử import** — 10 batch gần nhất; chỉ hiện cho phạm vi quản trị không bị giới hạn theo lớp.
5. **Kế hoạch** — mốc kế hoạch Udemy đang áp dụng.

Người có quyền `manage_settings` có thể mở import điểm và quản lý kế hoạch. Người chỉ có quyền xem đào tạo vẫn xem được dữ liệu trong đúng phạm vi lớp/cơ sở/môn được phân quyền.

### 2.2. Tích hợp trang chi tiết lớp

Trang:

```text
/student-management/classes/{classId}
```

Khi lớp thuộc môn Udemy:

- Hiển thị KPI số sinh viên đã có tiến độ, số sinh viên chậm, tiến độ trung bình và lần import gần nhất.
- Nút chính chuyển thành **Xem tiến độ Udemy**.
- Ẩn các thao tác Full CMS, Enrollment và cập nhật điểm Open edX.
- Ẩn khu vực Course mapping và dữ liệu học tập CMS/Open edX để tránh chạy sai nền tảng.

Lớp CMS giữ nguyên hành vi cũ.

### 2.3. Tích hợp Quản lý giảng viên

Trang:

```text
/teacher-management
```

Bổ sung:

- Số lớp CMS và số lớp Udemy.
- Số lượt sinh viên CMS và Udemy.
- Số sinh viên Udemy đã import.
- Tiến độ Udemy trung bình.
- Số sinh viên Udemy chậm tiến độ.
- Bộ lọc **Có SV Udemy chậm tiến độ**.
- Nút **Làm mới số liệu** để tạo job rebuild teacher-report cache sau khi import dữ liệu mới hoặc sau khi triển khai Batch 34.

Đối với lớp Udemy, báo cáo giảng viên không tăng các chỉ số:

- lớp chưa map Course CMS;
- sinh viên chưa đồng bộ CMS;
- sinh viên chưa enroll;
- sinh viên chưa có dữ liệu Open edX.

## 3. API mới

```http
GET /api/academic/subject-deliveries/{delivery_id}/udemy-progress/dashboard
GET /api/academic/subject-deliveries/{delivery_id}/udemy-progress/students
GET /api/academic/subject-deliveries/{delivery_id}/udemy-progress/export.xlsx
```

Endpoint summary của Batch 33 cũng được chuyển sang dùng cùng dashboard service và cùng access scope:

```http
GET /api/academic/subject-deliveries/{delivery_id}/udemy-progress/summary
```

### Bộ lọc danh sách sinh viên

```text
q
class_id
status = all | late | on_track | no_plan | unmatched | ambiguous | outside_roster | alerts
page
page_size
sort_by
sort_dir
```

## 4. Quy tắc tính trạng thái tiến độ

Batch 34 không sử dụng mù giá trị `is_late` được lưu tại thời điểm import.

Mỗi lần mở dashboard, lọc hoặc export, hệ thống:

1. Lấy kế hoạch Udemy active.
2. Chọn mốc gần nhất có `deadline_date <= ngày hiện tại tại Việt Nam`.
3. So sánh tiến độ snapshot mới nhất với `required_progress_percent` của mốc đó.
4. Tính lại trạng thái:
   - `late`: đã khớp roster và tiến độ thấp hơn mốc hiện tại;
   - `on_track`: đã khớp roster và đạt mốc;
   - `no_plan`: đã khớp roster nhưng chưa có mốc nào đến hạn;
   - `unmatched`, `ambiguous`, `outside_roster`: giữ theo kết quả đối chiếu AP.

Nhờ đó, cảnh báo tự thay đổi khi sang mốc kế hoạch mới mà không cần import lại chỉ để cập nhật cờ `is_late`.

## 5. Phân quyền

`_udemy_delivery_access_scope` áp dụng Business RBAC hiện tại:

- System admin / phạm vi không giới hạn: xem toàn bộ môn, các dòng chưa khớp và lịch sử import.
- Giảng viên: chỉ xem lớp AP đã phân công.
- Người quản lý cơ sở: chỉ xem lớp thuộc cơ sở được cấp.
- Người được cấp theo môn: xem các lớp của môn trong delivery tương ứng.
- Không có lớp phù hợp: HTTP 403.
- Chọn `class_id` ngoài phạm vi: HTTP 403.
- Export sử dụng cùng scope với dữ liệu màn hình.

Các dòng chưa xác định được lớp không được đưa cho tài khoản bị giới hạn theo lớp, vì chưa thể chứng minh dòng đó thuộc phạm vi của họ.

## 6. Excel

### 6.1. Export từ dashboard môn Udemy

File gồm:

```text
TongQuan
TienDoSinhVien
CanhBao
LichSuImport
HuongDan
```

Export giữ nguyên từ khóa, lớp và trạng thái đang lọc.

### 6.2. Export Quản lý giảng viên

Bổ sung vào `TongQuanGV`:

- lớp CMS / Udemy;
- sinh viên CMS / Udemy;
- sinh viên Udemy đã import;
- tiến độ Udemy trung bình;
- sinh viên Udemy chậm;
- lần import Udemy gần nhất.

Bổ sung vào `ChiTietLop`:

- nền tảng;
- subject delivery ID;
- số liệu tiến độ Udemy;
- mốc, tuần và deadline Udemy hiện tại.

Thêm sheet:

```text
UdemyChamTienDo
```

Sheet này liệt kê các lớp Udemy còn sinh viên chậm và đường dẫn đến dashboard môn. Danh sách sinh viên chi tiết được xuất trực tiếp từ dashboard Udemy để bảo đảm đúng scope và bộ lọc.

## 7. File thay đổi

Xem `CHANGED_FILES_UDEMY_PROGRESS_DASHBOARD_BATCH_34.txt`.

## 8. Triển khai

Batch 34 cần build/recreate:

```text
backend
frontend
worker-heavy
```

`worker-heavy` cần thiết vì nút **Làm mới số liệu** và export giảng viên nền dùng task:

```text
academic_teacher_report_job_task
queue: exports
```

Không cần:

- Alembic migration;
- build Open edX connector;
- build Unit Reset plugin;
- build Learning MFE.

Sau deploy, mở `/teacher-management`, chọn đúng học kỳ/hệ/cơ sở và bấm **Làm mới số liệu** một lần. Việc này thay cache cũ vốn chưa có các trường Udemy.

## 9. UAT bắt buộc

### Dashboard môn

1. Mở một delivery Udemy từ `/subject-management`.
2. KPI phải khớp snapshot mới nhất.
3. Lọc `Chậm tiến độ`, `Đạt tiến độ`, `Chưa có mốc`, `Chưa khớp AP`.
4. Lọc theo lớp.
5. Export và đối chiếu số dòng với màn hình.
6. Đăng nhập bằng giảng viên và xác nhận chỉ thấy lớp được AP phân công.

### Trang lớp

1. Mở một lớp Udemy.
2. Không được thấy nút Full CMS/Enrollment/Cập nhật điểm Open edX.
3. Nút **Xem tiến độ Udemy** mở đúng delivery.
4. Mở một lớp CMS và xác nhận toàn bộ hành vi cũ vẫn còn.

### Quản lý giảng viên

1. Bấm **Làm mới số liệu**.
2. Xác nhận số lớp CMS/Udemy và số sinh viên Udemy.
3. Lọc **Có SV Udemy chậm tiến độ**.
4. Lớp Udemy không xuất hiện trong chỉ số “chưa ghép Course CMS”.
5. Xuất Excel và kiểm tra sheet `UdemyChamTienDo`.

## 10. Kết quả kiểm tra trước đóng gói

Đã thực hiện:

- Python `py_compile` cho các file backend thay đổi.
- Regression Batch 31–34: 15 test đạt.
- Kiểm tra cú pháp TS/TSX cho toàn bộ file frontend thay đổi.
- Kiểm tra workbook bằng openpyxl, gồm header và sheet Udemy.
- Kiểm tra ZIP và quét file nhạy cảm trước khi phát hành.

Chưa thực hiện trong môi trường này:

- Docker production build trên UAT;
- migration PostgreSQL — Batch 34 không có migration;
- chạy Celery/Redis thật;
- browser E2E trên `cms-test.poly.edu.vn`;
- UAT bằng tài khoản giảng viên/cơ sở thật.
