from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

VIDEO_EVENTS = {
    'play_video', 'pause_video', 'stop_video', 'seek_video',
    'edx.video.played', 'edx.video.paused', 'edx.video.stopped', 'edx.video.position.changed',
}
PLAY_EVENTS = {'play_video', 'edx.video.played'}
PAUSE_STOP_EVENTS = {'pause_video', 'stop_video', 'edx.video.paused', 'edx.video.stopped'}
SEEK_EVENTS = {'seek_video', 'edx.video.position.changed'}


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
    consistency_percent: float | None = None
    video_quality_percent: float | None = None
    long_passive_segment_count: int = 0
    long_passive_seconds: float = 0.0
    passive_watch_seconds: float = 0.0


def _cap_percent(value: float | None) -> float | None:
    if value is None:
        return None
    return round(max(0.0, min(100.0, float(value))), 2)


def _quality(completion_percent: float | None, watch_percent: float | None) -> tuple[float | None, float | None]:
    if completion_percent is None or watch_percent is None:
        return None, None
    completion = max(0.0, min(1.0, completion_percent / 100.0))
    watch = max(0.0, min(1.0, watch_percent / 100.0))
    consistency = max(0.0, 1.0 - abs(completion - watch))
    quality = min(completion, watch) * consistency
    return round(consistency * 100.0, 2), round(quality * 100.0, 2)


def _has_interaction_between(events: list[VideoEventInput], start: datetime, end: datetime) -> bool:
    for ev in events:
        if ev.event_time and start < ev.event_time < end and ev.event_type in SEEK_EVENTS:
            return True
    return False


def calculate_video_progress(
    events: list[VideoEventInput],
    *,
    complete_threshold: float = 0.9,
    suspicious_watch_ratio: float = 0.25,
    max_passive_segment_seconds: int = 600,
) -> VideoProgressResult:
    """Calculate video progress with dynamic passive-watch capping.

    Open edX video logs are interaction events, not an exact stopwatch. We only
    cap aggressively when a long play segment has no interaction evidence. The
    same segment is then emitted as long-passive evidence for idle analysis.
    """
    ordered = sorted(events, key=lambda e: e.event_time or datetime.min)
    duration = next((e.duration_seconds for e in ordered if e.duration_seconds and e.duration_seconds > 0), None)
    max_position = max([e.current_time_seconds for e in ordered if e.current_time_seconds is not None] or [None])
    completion = _cap_percent((max_position / duration * 100.0) if duration and max_position is not None else None)

    play_count = sum(1 for e in ordered if e.event_type in PLAY_EVENTS)
    pause_count = sum(1 for e in ordered if e.event_type in {'pause_video', 'edx.video.paused'})
    stop_count = sum(1 for e in ordered if e.event_type in {'stop_video', 'edx.video.stopped'})
    seek_count = sum(1 for e in ordered if e.event_type in SEEK_EVENTS)

    watch_seconds = 0.0
    passive_watch_seconds = 0.0
    long_passive_seconds = 0.0
    long_passive_segment_count = 0
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
        if ev.event_type in PLAY_EVENTS:
            active = ev
        elif ev.event_type in PAUSE_STOP_EVENTS and active and active.event_time and ev.event_time:
            wall = max(0.0, (ev.event_time - active.event_time).total_seconds())
            plausible = wall
            if active.current_time_seconds is not None and ev.current_time_seconds is not None:
                media_delta = max(0.0, ev.current_time_seconds - active.current_time_seconds)
                plausible = min(wall, media_delta + 10.0)
            has_interaction = _has_interaction_between(ordered, active.event_time, ev.event_time)
            dynamic_threshold = max(float(max_passive_segment_seconds), float(duration or 0) * 0.60)
            passive_cap = max(float(max_passive_segment_seconds), float(duration or 0) * 0.30)
            capped = plausible
            passive = False
            if plausible > dynamic_threshold and not has_interaction:
                passive = True
                long_passive_segment_count += 1
                long_passive_seconds += plausible
                capped = min(plausible, passive_cap)
            if capped > 0:
                watch_seconds += capped
                if passive:
                    passive_watch_seconds += capped
                segments.append({
                    'start': active.event_time.isoformat(),
                    'end': ev.event_time.isoformat(),
                    'seconds': round(capped, 2),
                    'raw_seconds': round(plausible, 2),
                    'dynamic_cap_applied': passive,
                    'has_interaction': has_interaction,
                })
            active = None
        previous = ev

    estimated_watch_percent = _cap_percent((watch_seconds / duration * 100.0) if duration else None)
    consistency_percent, video_quality_percent = _quality(completion, estimated_watch_percent)
    is_completed = bool(completion is not None and completion >= complete_threshold * 100.0)
    if large_seek_count:
        reasons.append('LARGE_SEEK_JUMP')
    if long_passive_segment_count:
        reasons.append('LONG_PASSIVE_PLAYBACK')
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
        is_suspicious=bool([r for r in reasons if r != 'LONG_PASSIVE_PLAYBACK']),
        reason_codes=reasons,
        consistency_percent=consistency_percent,
        video_quality_percent=video_quality_percent,
        long_passive_segment_count=long_passive_segment_count,
        long_passive_seconds=round(long_passive_seconds, 2),
        passive_watch_seconds=round(passive_watch_seconds, 2),
        evidence={
            'segments': segments[:20],
            'large_seek_count': large_seek_count,
            'event_count': len(ordered),
            'dynamic_watch_cap': True,
            'long_passive_segment_count': long_passive_segment_count,
            'long_passive_seconds': round(long_passive_seconds, 2),
            'passive_watch_seconds': round(passive_watch_seconds, 2),
            'consistency_percent': consistency_percent,
            'video_quality_percent': video_quality_percent,
        },
    )
