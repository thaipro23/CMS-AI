from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

_TRACKING_JSON_RE = re.compile(r"\s-\s(?P<payload>\{.*\})\s*$")
VIDEO_EVENTS = {
    'play_video', 'pause_video', 'stop_video', 'seek_video',
    'edx.video.played', 'edx.video.paused', 'edx.video.stopped', 'edx.video.position.changed',
}
QUIZ_SERVER_EVENTS = {
    'problem_check', 'problem_graded', 'problem_save', 'edx.grades.problem.submitted',
    'edx.completion.block_completion.changed',
}
QUIZ_SESSION_EVENTS = {
    '/api/unit-reset/v1/quiz-session/start',
    '/api/unit-reset/v1/quiz-session/status',
    '/api/unit-reset/v1/quiz-session/reset',
}
ITEMBANK_EVENTS = {'edx.itembankblock.content.assigned'}
ANSWER_REVEAL_EVENTS = {'problem_show', 'showanswer'}
NAVIGATION_EVENTS = {'seq_next', 'seq_prev'}
CAPTION_EVENTS = {'edx.video.closed_captions.hidden'}
_RELEVANT_EVENTS = VIDEO_EVENTS | QUIZ_SERVER_EVENTS | QUIZ_SESSION_EVENTS | ITEMBANK_EVENTS | ANSWER_REVEAL_EVENTS | NAVIGATION_EVENTS | CAPTION_EVENTS
_NOISE_PATTERNS = (
    '/theming/asset/', '/api/notifications/', '/api/mfe_config/', '/csrf/api/v1/token',
    '/api/course_home/', '/api/learning_sequences/', '/api/courseware/course/',
    '/courseware-search/enabled/', '/api/user_tours/', '/favicon', '/static/',
)


@dataclass(slots=True)
class ParsedTrackingEvent:
    raw_line_hash: str
    event_time: datetime | None
    event_type: str
    event_source: str
    user_id: str | None
    username: str | None
    course_id: str | None
    org_id: str | None
    session_id: str | None
    video_id: str | None
    video_code: str | None
    video_duration_seconds: float | None
    current_time_seconds: float | None
    page_url: str | None
    referer: str | None
    raw_event: dict[str, Any]
    raw_context: dict[str, Any]
    raw_json: dict[str, Any]

    def as_model_kwargs(self) -> dict[str, Any]:
        return {
            'raw_line_hash': self.raw_line_hash,
            'event_time': self.event_time,
            'event_type': self.event_type,
            'event_source': self.event_source,
            'user_id': self.user_id,
            'username': self.username,
            'course_id': self.course_id,
            'org_id': self.org_id,
            'session_id': self.session_id,
            'video_id': self.video_id,
            'video_code': self.video_code,
            'video_duration_seconds': self.video_duration_seconds,
            'current_time_seconds': self.current_time_seconds,
            'page_url': self.page_url,
            'referer': self.referer,
            'raw_event': self.raw_event,
            'raw_context': self.raw_context,
            'raw_json': self.raw_json,
        }


class TrackingParseError(ValueError):
    pass


def _safe_float(value: Any) -> float | None:
    if value is None or value == '':
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _safe_str(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _parse_time(value: Any) -> datetime | None:
    if not value:
        return None
    text = str(value).strip()
    if not text:
        return None
    try:
        # Open edX tracking logs commonly use an ISO string with Z suffix.
        parsed = datetime.fromisoformat(text.replace('Z', '+00:00'))
        if parsed.tzinfo is not None:
            parsed = parsed.astimezone(timezone.utc).replace(tzinfo=None)
        return parsed
    except ValueError:
        return None


def extract_tracking_json(line: str) -> dict[str, Any]:
    """Extract the JSON object from a tracking.log line.

    Supports both raw JSON lines and Tutor/Open edX log lines like:
    ``... logger.py:41 - {json}``.
    """
    text = (line or '').strip()
    if not text:
        raise TrackingParseError('empty_line')
    payload = text if text.startswith('{') else None
    if payload is None:
        match = _TRACKING_JSON_RE.search(text)
        if match:
            payload = match.group('payload')
    if not payload:
        raise TrackingParseError('json_payload_not_found')
    try:
        data = json.loads(payload)
    except json.JSONDecodeError as exc:
        raise TrackingParseError('invalid_outer_json') from exc
    if not isinstance(data, dict):
        raise TrackingParseError('outer_json_is_not_object')
    return data


def parse_nested_event(value: Any) -> dict[str, Any]:
    if value is None:
        return {}
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        value = value.strip()
        if not value:
            return {}
        try:
            parsed = json.loads(value)
            return parsed if isinstance(parsed, dict) else {'value': parsed}
        except json.JSONDecodeError:
            return {'value': value}
    return {'value': value}


def _derive_video_id(event: dict[str, Any], page: str | None) -> str | None:
    for key in ('id', 'video_id', 'code', 'video_code', 'youtube_id'):
        val = _safe_str(event.get(key))
        if val:
            return val
    if page:
        # Fallback: keep deterministic but not over-smart. The session mapper can
        # later attach this to a component if page contains usage keys.
        match = re.search(r'(?:video|block)@([^/?#&]+)', page)
        if match:
            return match.group(1)
    return None


def parse_tracking_log_line(line: str, *, include_caption_events: bool = True) -> ParsedTrackingEvent | None:
    raw_hash = hashlib.sha256((line or '').encode('utf-8', errors='ignore')).hexdigest()
    data = extract_tracking_json(line)
    event_type = _safe_str(data.get('event_type')) or _safe_str(data.get('name')) or ''
    if not event_type:
        raise TrackingParseError('event_type_missing')
    page_for_noise = _safe_str(data.get('page')) or ''
    if event_type not in _RELEVANT_EVENTS:
        if any(pattern in page_for_noise for pattern in _NOISE_PATTERNS):
            return None
        return None
    if event_type == 'edx.video.closed_captions.hidden' and not include_caption_events:
        return None

    context = data.get('context') if isinstance(data.get('context'), dict) else {}
    event = parse_nested_event(data.get('event'))
    page = _safe_str(data.get('page')) or _safe_str(event.get('page'))
    referer = _safe_str(data.get('referer')) or _safe_str(data.get('agent'))
    course_id = _safe_str(context.get('course_id')) or _safe_str(data.get('course_id')) or _safe_str(event.get('course_id'))
    org_id = _safe_str(context.get('org_id')) or (course_id.split('+', 1)[0].replace('course-v1:', '') if course_id and '+' in course_id else None)
    current_time = _safe_float(event.get('currentTime'))
    if current_time is None:
        current_time = _safe_float(event.get('current_time'))
    duration = _safe_float(event.get('duration'))
    video_id = _derive_video_id(event, page)
    return ParsedTrackingEvent(
        raw_line_hash=raw_hash,
        event_time=_parse_time(data.get('time')),
        event_type=event_type,
        event_source=_safe_str(data.get('event_source')) or _safe_str(data.get('source')) or 'openedx_tracking_log',
        user_id=_safe_str((context or {}).get('user_id')) or _safe_str(data.get('user_id')),
        username=_safe_str(data.get('username')) or _safe_str((context or {}).get('username')),
        course_id=course_id,
        org_id=org_id,
        session_id=_safe_str(data.get('session')) or _safe_str(event.get('session')),
        video_id=video_id,
        video_code=_safe_str(event.get('code')) or video_id,
        video_duration_seconds=duration,
        current_time_seconds=current_time,
        page_url=page,
        referer=referer,
        raw_event=event,
        raw_context=context or {},
        raw_json=data,
    )
