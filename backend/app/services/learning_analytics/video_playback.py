"""Incremental media advancement, independent of legacy wall-time rule totals."""
from __future__ import annotations

import math
from datetime import datetime, timezone

VERSION = 'video_playback_v1'
PLAY = {'play_video', 'edx.video.played'}
STOP = {'pause_video', 'stop_video', 'edx.video.paused', 'edx.video.stopped'}
SEEK = {'seek_video', 'edx.video.position.changed'}


def _number(value):
    if isinstance(value, bool):
        return None
    try:
        n = float(value)
        return n if math.isfinite(n) and n >= 0 else None
    except (TypeError, ValueError, OverflowError):
        return None


def _time(value):
    try:
        t = value if isinstance(value, datetime) else datetime.fromisoformat(str(value))
        return t.astimezone(timezone.utc).replace(tzinfo=None) if t.tzinfo else t
    except (TypeError, ValueError):
        return None


def measure_playback(events, previous=None, historical_data=False) -> dict:
    previous = previous if isinstance(previous, dict) and previous.get('version') == VERSION else {}
    state = {'version': VERSION, 'complete_history': previous.get('complete_history', not historical_data) is True,
        'media_seconds': 0., 'wall_seconds': 0., 'passive_media_seconds': 0.,
        'observed_intervals': 0, 'unknown_intervals': 0, 'anchor': None, 'last_time': None,
        'last_events': [], 'last_closed': previous.get('last_closed')}
    for key in ('media_seconds', 'wall_seconds', 'passive_media_seconds', 'observed_intervals', 'unknown_intervals'):
        n = _number(previous.get(key, 0))
        if n is None:
            state['complete_history'] = False
        else:
            state[key] = n if key.endswith('seconds') else int(n)
    anchor = previous.get('anchor') if isinstance(previous.get('anchor'), dict) else None
    watermark = _time(previous.get('last_time'))
    signatures = set(previous.get('last_events') or [])
    state['last_time'] = previous.get('last_time')
    for ev in sorted(events, key=lambda e: _time(e.event_time) or datetime.min):
        when = _time(ev.event_time)
        if when is None:
            state['unknown_intervals'] += 1
            continue
        if watermark is not None and when < watermark:
            continue
        position = _number(ev.current_time_seconds)
        if watermark is None and ev.event_type in PLAY and (position is None or position > 2):
            state['complete_history'] = False
            state['unknown_intervals'] += 1
        signature = f'{ev.event_type}:{position}'
        if when != watermark:
            signatures = set()
        if signature in signatures:
            continue
        signatures.add(signature)
        if len(signatures) > 128:
            state['complete_history'] = False
        closed = state.get('last_closed') or {}
        closed_time = _time(closed.get('time'))
        companion_stop = (ev.event_type in STOP and closed_time is not None
            and 0 <= (when-closed_time).total_seconds() <= 2 and position is not None
            and position == _number(closed.get('position')))
        if not anchor and ev.event_type in STOP | SEEK and not companion_stop:
            state['complete_history'] = False
            state['unknown_intervals'] += 1
        if anchor:
            start, before = _time(anchor.get('time')), _number(anchor.get('position'))
            wall = (when-start).total_seconds() if start else 0
            if wall > 0:
                if ev.event_type in SEEK:
                    # The new position contains a jump; no pre-seek position is persisted.
                    if wall > 2:
                        state['unknown_intervals'] += 1
                elif before is None or position is None:
                    state['unknown_intervals'] += 1
                else:
                    advance = position-before
                    state['observed_intervals'] += 1
                    state['wall_seconds'] += wall
                    # Inferred from observed movement. Impossible jumps contribute no media.
                    media = max(0., advance) if 0 <= advance <= wall*4+2 else 0.
                    state['media_seconds'] += media
                    duration = _number(ev.duration_seconds) or 0.
                    if media > max(600., duration*.6):
                        state['passive_media_seconds'] += media
        if ev.event_type in STOP:
            anchor = None
            state['last_closed'] = {'time': when.isoformat(), 'position': position}
        elif ev.event_type in PLAY or (anchor and ev.event_type in SEEK):
            anchor = {'time': when.isoformat(), 'position': position}
        watermark = when
        state['last_time'] = when.isoformat()
    state['anchor'] = anchor
    state['last_events'] = sorted(signatures)[:128]
    for key in ('media_seconds', 'wall_seconds', 'passive_media_seconds'):
        state[key] = round(state[key], 6)
    return state
