# v25.9.15.6.13 - Custom Timed Practice Quiz

Bản này thêm cấu hình thời gian cho Quiz tự luyện, không dùng native Timed Exam của Open edX.

## Luồng

```text
/bank/quiz
→ dán Course ID
→ tự map version/chapter/release
→ chọn số câu và thời gian
→ tạo Quiz bình thường trong Open edX
→ lưu timer config theo Unit trong plugin openedx_unit_reset
```

## Nguyên tắc

- Không bật `Set as special exam = Timed`.
- Timer lưu server-side trong plugin `openedx_unit_reset`.
- Hết giờ: MFE/LMS runtime JS tự nộp câu đã chọn rồi khóa input.
- Backend guard chặn `problem_check` sau khi session hết giờ.
- Làm lại bài dùng reset Unit hiện có + tạo session timer mới.

## API plugin mới

```http
GET  /api/unit-reset/v1/quiz-session/status
POST /api/unit-reset/v1/quiz-session/start
POST /api/unit-reset/v1/quiz-session/timeout
POST /api/unit-reset/v1/quiz-session/lock
POST /api/unit-reset/v1/quiz-session/reset
GET  /api/unit-reset/v1/quiz-session/runtime.js
```

## Models plugin mới

- `UnitQuizTimerConfig`: config thời gian theo Unit.
- `UnitQuizSession`: session làm bài theo user + Unit + attempt.

## AI Server

`POST /api/question-bank-v2/releases/{release_id}/quiz/create` nhận thêm:

```json
{
  "custom_timer_enabled": true,
  "time_limit_minutes": 15,
  "retake_cooldown_minutes": 5,
  "auto_submit_on_timeout": true,
  "lock_after_timeout": true,
  "native_timed_exam": false
}
```

AI Server pass config sang `openedx-connector-plugin`. Connector best-effort lưu vào `openedx_unit_reset` nếu plugin được cài trong CMS image.

## Cần làm tiếp ở frontend-app-learning

MFE Learning cần gọi các API quiz-session để hiển thị đồng hồ và khi hết giờ gửi message:

```js
window.postMessage({ type: 'AI_QUIZ_TIMEOUT_AUTO_SUBMIT' }, '*')
```

Hoặc load runtime JS từ LMS:

```html
<script src="/api/unit-reset/v1/quiz-session/runtime.js"></script>
```

