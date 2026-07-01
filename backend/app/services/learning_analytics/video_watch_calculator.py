from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

VIDEO_EVENTS = {'play_video', 'pause_video', 'stop_video', 'seek_video', 'edx.video.position.changed'}


@dataclass(slots=True)
class VideoEventInput:
    event_type: str
    event_time: datetime | None
    current_time_seconds: float | None = None
    duration_seconds: float | None = None
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class VideoProgressResult:
    duration_seconds: float | None
    max_position_seconds: float | None
    completion_percent: float | None
    estimated_watch_seconds: float
    estimated_watch_percent: float | None
    play_count: int
    pause_count: int
    stop_count: int
    seek_count: int
    is_completed: bool
    is_suspicious: bool
    reason_codes: list[str]
    evidence: dict[str, Any]


def _cap_percent(value: float | None) -> float | None:
    if value is None:
        return None
    return round(max(0.0, min(100.0, float(value))), 2)


def calculate_video_progress(
    events: list[VideoEventInput],
    *,
    complete_threshold: float = 0.9,
    suspicious_watch_ratio: float = 0.25,
    max_passive_segment_seconds: int = 600,
) -> VideoProgressResult:
    ordered = sorted(events, key=lambda e: e.event_time or datetime.min)
    duration = next((e.duration_seconds for e in ordered if e.duration_seconds and e.duration_seconds > 0), None)
    max_position = max([e.current_time_seconds for e in ordered if e.current_time_seconds is not None] or [None])
    completion = _cap_percent((max_position / duration * 100.0) if duration and max_position is not None else None)

    play_count = sum(1 for e in ordered if e.event_type == 'play_video')
    pause_count = sum(1 for e in ordered if e.event_type == 'pause_video')
    stop_count = sum(1 for e in ordered if e.event_type == 'stop_video')
    seek_count = sum(1 for e in ordered if e.event_type in {'seek_video', 'edx.video.position.changed'})

    watch_seconds = 0.0
    reasons: list[str] = []
    segments: list[dict[str, Any]] = []
    active: VideoEventInput | None = None
    previous = None
    large_seek_count = 0
    for ev in ordered:
        if previous and ev.current_time_seconds is not None and previous.current_time_seconds is not None and ev.event_time and previous.event_time:
            wall_delta = max(0.0, (ev.event_time - previous.event_time).total_seconds())
            media_delta = ev.current_time_seconds - previous.current_time_seconds
            if media_delta > max(60.0, wall_delta + 30.0) and wall_delta <= 10.0:
                large_seek_count += 1
        if ev.event_type == 'play_video':
            active = ev
        elif ev.event_type in {'pause_video', 'stop_video'} and active and active.event_time and ev.event_time:
            wall = max(0.0, (ev.event_time - active.event_time).total_seconds())
            plausible = wall
            if active.current_time_seconds is not None and ev.current_time_seconds is not None:
                media_delta = max(0.0, ev.current_time_seconds - active.current_time_seconds)
                plausible = min(wall, media_delta + 10.0)
            capped = min(plausible, float(max_passive_segment_seconds))
            if capped > 0:
                watch_seconds += capped
                segments.append({'start': active.event_time.isoformat(), 'end': ev.event_time.isoformat(), 'seconds': round(capped, 2)})
            active = None
        previous = ev

    estimated_watch_percent = _cap_percent((watch_seconds / duration * 100.0) if duration else None)
    is_completed = bool(completion is not None and completion >= complete_threshold * 100.0)
    if large_seek_count:
        reasons.append('LARGE_SEEK_JUMP')
    if duration and completion is not None and completion >= complete_threshold * 100.0 and watch_seconds < duration * suspicious_watch_ratio:
        reasons.append('HIGH_COMPLETION_LOW_WATCH_TIME')
    if play_count >= 3 and duration and watch_seconds < min(30, duration * 0.1):
        reasons.append('MANY_VIDEOS_COMPLETED_TOO_FAST')
    return VideoProgressResult(
        duration_seconds=duration,
        max_position_seconds=max_position,
        completion_percent=completion,
        estimated_watch_seconds=round(watch_seconds, 2),
        estimated_watch_percent=estimated_watch_percent,
        play_count=play_count,
        pause_count=pause_count,
        stop_count=stop_count,
        seek_count=seek_count,
        is_completed=is_completed,
        is_suspicious=bool(reasons),
        reason_codes=reasons,
        evidence={'segments': segments[:20], 'large_seek_count': large_seek_count, 'event_count': len(ordered)},
    )
