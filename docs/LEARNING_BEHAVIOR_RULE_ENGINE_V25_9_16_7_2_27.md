# Learning Behavior Rule Engine v25.9.16.7.2.27

## Event taxonomy

Feature engine dùng allowlist:

```text
VIDEO_EVENTS:
play_video, pause_video, stop_video, seek_video,
edx.video.played, edx.video.paused, edx.video.stopped,
edx.video.position.changed

QUIZ_SESSION_EVENTS:
/api/unit-reset/v1/quiz-session/start
/api/unit-reset/v1/quiz-session/status
/api/unit-reset/v1/quiz-session/reset

QUIZ_SERVER_EVENTS:
edx.grades.problem.submitted
server problem_check fallback

ITEMBANK_EVENTS:
edx.itembankblock.content.assigned

ANSWER_REVEAL_EVENTS:
problem_show, showanswer
```

Noise như favicon, theming asset, notifications, mfe_config, csrf, user_tours không tạo learning feature.

## Video formula

```python
completion = clamp(max_position_seconds / duration_seconds, 0.0, 1.0)
watch = clamp(estimated_watch_seconds / duration_seconds, 0.0, 1.0)
consistency = 1.0 - abs(completion - watch)
video_quality = min(completion, watch) * consistency
```

## Scores

```python
real_learning_score = 100 * clamp(
    0.70 * avg_video_quality
  + 0.20 * on_time_session_completion_rate
  + 0.10 * video_before_quiz_rate,
  0.0, 1.0
)

suspicious_score = 100 * clamp(
    0.45 * suspicious_video_rate
  + 0.25 * quiz_before_video_rate
  + 0.15 * crammed_low_watch_rate
  + 0.15 * suspicious_quiz_speed_rate,
  0.0, 1.0
)

idle_score = 100 * clamp(
    0.35 * long_passive_video_rate
  + 0.25 * watch_without_quiz_rate
  + 0.20 * watch_without_navigation_rate
  + 0.20 * passive_watch_share,
  0.0, 1.0
)
```

## Labels

New writes use:

```text
LIKELY_REAL_LEARNING
POSSIBLE_IDLE
POSSIBLE_ANOMALY
INSUFFICIENT_DATA
NORMAL
```

Old `POSSIBLE_CHEATING` remains readable for backward compatibility, but migration updates existing rows to `POSSIBLE_ANOMALY`.

## Safety policy

This is a learning-behavior signal system. It does not conclude violation or cheating. Teacher/manager review is required before any operational action.
