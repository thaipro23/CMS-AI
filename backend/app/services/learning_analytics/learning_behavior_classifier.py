from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

DISPLAY_LABELS = {
    'LIKELY_REAL_LEARNING': 'Có dấu hiệu học thật',
    'POSSIBLE_IDLE': 'Có khả năng treo máy',
    'POSSIBLE_CHEATING': 'Dấu hiệu bất thường cần kiểm tra',
    'INSUFFICIENT_DATA': 'Chưa đủ dữ liệu',
    'NORMAL': 'Chưa thấy bất thường rõ',
}

RECOMMENDED_ACTIONS = {
    'LIKELY_REAL_LEARNING': 'NO_ACTION',
    'POSSIBLE_IDLE': 'REMIND_STUDENT',
    'POSSIBLE_CHEATING': 'TEACHER_REVIEW',
    'INSUFFICIENT_DATA': 'INSUFFICIENT_DATA_RECHECK_LATER',
    'NORMAL': 'NO_ACTION',
}


@dataclass(slots=True)
class BehaviorInput:
    total_events: int = 0
    total_sessions: int = 0
    sessions_started: int = 0
    sessions_completed_on_time: int = 0
    sessions_completed_late: int = 0
    crammed_session_count: int = 0
    quiz_before_video_count: int = 0
    video_before_quiz_count: int = 0
    total_videos_seen: int = 0
    total_videos_completed: int = 0
    avg_video_completion_percent: float | None = None
    total_estimated_watch_seconds: float = 0.0
    avg_estimated_watch_percent: float | None = None
    suspicious_video_count: int = 0
    long_passive_video_count: int = 0
    missing_duration_count: int = 0
    missing_session_mapping: bool = False
    missing_deadline_mapping: bool = False
    only_caption_events: bool = False
    last_activity_at: datetime | None = None
    extra_reasons: list[str] = field(default_factory=list)


@dataclass(slots=True)
class BehaviorResult:
    classification: str
    display_label: str
    confidence_score: float
    real_learning_score: float
    idle_score: float
    suspicious_score: float
    data_quality: str
    reason_codes: list[str]
    human_readable_summary: str
    recommended_action: str
    evidence: dict[str, Any]


def _clamp(value: float) -> float:
    return round(max(0.0, min(100.0, float(value))), 2)


def classify_learning_behavior(inp: BehaviorInput) -> BehaviorResult:
    reasons: list[str] = list(dict.fromkeys(inp.extra_reasons or []))
    if inp.only_caption_events:
        reasons.append('ONLY_CAPTION_EVENTS')
    if inp.total_events <= 0 or inp.total_videos_seen <= 0:
        reasons.append('NO_VIDEO_ACTIVITY')
    if inp.missing_session_mapping:
        reasons.append('MISSING_SESSION_MAPPING')
    if inp.missing_deadline_mapping:
        reasons.append('MISSING_DEADLINE_MAPPING')
    if inp.missing_duration_count:
        reasons.append('MISSING_VIDEO_DURATION')

    if inp.quiz_before_video_count:
        reasons.append('QUIZ_BEFORE_VIDEO')
    if inp.crammed_session_count:
        reasons.append('CRAMMED_SESSIONS')
    if inp.suspicious_video_count:
        reasons.append('HIGH_COMPLETION_LOW_WATCH_TIME')
    if inp.long_passive_video_count:
        reasons.append('LONG_PASSIVE_PLAYBACK')
    if inp.sessions_completed_late:
        reasons.append('COMPLETED_LATE')
    if inp.sessions_completed_on_time:
        reasons.append('DEADLINE_PATTERN_MATCHED')
    if inp.video_before_quiz_count:
        reasons.append('WATCH_THEN_ATTEMPT_PROBLEM')

    data_quality = 'GOOD'
    if inp.total_events <= 0 or inp.total_videos_seen <= 0:
        data_quality = 'MISSING'
    elif inp.missing_session_mapping or inp.missing_deadline_mapping or inp.missing_duration_count:
        data_quality = 'LOW'
    elif inp.total_events < 5 or inp.sessions_started <= 1:
        data_quality = 'PARTIAL'

    completion_component = float(inp.avg_video_completion_percent or 0) * 0.35
    watch_component = float(inp.avg_estimated_watch_percent or 0) * 0.35
    deadline_component = (inp.sessions_completed_on_time / max(1, inp.total_sessions)) * 100 * 0.2
    quiz_component = (inp.video_before_quiz_count / max(1, inp.sessions_started)) * 100 * 0.1
    real_score = _clamp(completion_component + watch_component + deadline_component + quiz_component)

    idle_score = _clamp((inp.long_passive_video_count * 22) + (max(0, inp.total_videos_completed - inp.video_before_quiz_count) * 5) + (10 if inp.total_estimated_watch_seconds > 3600 and inp.video_before_quiz_count == 0 else 0))
    suspicious_score = _clamp((inp.suspicious_video_count * 28) + (inp.quiz_before_video_count * 24) + (inp.crammed_session_count * 22))
    if inp.avg_video_completion_percent and inp.avg_estimated_watch_percent is not None and inp.avg_video_completion_percent >= 90 and inp.avg_estimated_watch_percent < 25:
        suspicious_score = _clamp(suspicious_score + 25)
    confidence = _clamp(30 + min(40, inp.total_events * 2) + min(20, inp.sessions_started * 5) - (30 if data_quality in {'LOW', 'MISSING'} else 0))

    severe = {'HIGH_COMPLETION_LOW_WATCH_TIME', 'LARGE_SEEK_JUMP', 'MANY_VIDEOS_COMPLETED_TOO_FAST', 'REPEATED_IDENTICAL_PATTERN', 'QUIZ_BEFORE_VIDEO', 'CRAMMED_SESSIONS'}
    severe_count = len(severe.intersection(set(reasons)))

    if data_quality in {'LOW', 'MISSING'} and inp.total_events < 5:
        classification = 'INSUFFICIENT_DATA'
    elif suspicious_score >= 70 and severe_count >= 2:
        classification = 'POSSIBLE_CHEATING'
    elif idle_score >= 65 and suspicious_score < 70:
        classification = 'POSSIBLE_IDLE'
    elif real_score >= 70 and suspicious_score < 40 and idle_score < 50 and data_quality in {'GOOD', 'PARTIAL'}:
        classification = 'LIKELY_REAL_LEARNING'
    elif data_quality in {'LOW', 'MISSING'}:
        classification = 'INSUFFICIENT_DATA'
    else:
        classification = 'NORMAL'

    if classification == 'INSUFFICIENT_DATA' and not reasons:
        reasons.append('INSUFFICIENT_EVENTS')

    summary_parts = []
    if classification == 'LIKELY_REAL_LEARNING':
        summary_parts.append('Có hoạt động xem video và làm bài theo Bài/Session tương đối hợp lý.')
    elif classification == 'POSSIBLE_IDLE':
        summary_parts.append('Có dấu hiệu video chạy dài hoặc nhiều video nhưng thiếu tương tác học tập tiếp theo.')
    elif classification == 'POSSIBLE_CHEATING':
        summary_parts.append('Có các dấu hiệu bất thường cần giáo viên/quản lý kiểm tra thêm.')
    elif classification == 'INSUFFICIENT_DATA':
        summary_parts.append('Chưa đủ log hoặc mapping để đánh giá đáng tin cậy.')
    else:
        summary_parts.append('Có hoạt động học, chưa thấy bất thường rõ.')

    return BehaviorResult(
        classification=classification,
        display_label=DISPLAY_LABELS[classification],
        confidence_score=confidence,
        real_learning_score=real_score,
        idle_score=idle_score,
        suspicious_score=suspicious_score,
        data_quality=data_quality,
        reason_codes=list(dict.fromkeys(reasons)),
        human_readable_summary=' '.join(summary_parts),
        recommended_action=RECOMMENDED_ACTIONS[classification],
        evidence={
            'total_events': inp.total_events,
            'total_sessions': inp.total_sessions,
            'sessions_started': inp.sessions_started,
            'total_videos_seen': inp.total_videos_seen,
            'total_videos_completed': inp.total_videos_completed,
            'avg_video_completion_percent': inp.avg_video_completion_percent,
            'avg_estimated_watch_percent': inp.avg_estimated_watch_percent,
            'disclaimer': 'Dữ liệu chỉ phản ánh dấu hiệu từ log hệ thống, không phải kết luận vi phạm.',
        },
    )
