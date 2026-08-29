from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any


@dataclass(slots=True)
class SessionComponent:
    usage_key: str
    block_type: str
    title: str = ''
    part_index: int | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class CourseSessionMapping:
    session_index: int
    session_type: str
    session_key: str
    session_title: str
    week_index: int
    deadline_at: datetime | None
    deadline_source: str
    deadline_mapping_quality: str
    components: list[SessionComponent] = field(default_factory=list)

    @property
    def videos(self) -> list[SessionComponent]:
        return [c for c in self.components if c.block_type == 'video']

    @property
    def quiz(self) -> SessionComponent | None:
        quizzes = [c for c in self.components if c.block_type in {'problem', 'quiz', 'sequential_quiz'}]
        return quizzes[-1] if quizzes else None


def session_week_pattern(session_count: int, weeks: int = 6) -> list[int]:
    """Return number of sessions per week, preserving course order.

    Special cases required by operations are kept explicit. Other counts use a
    largest-remainder style split over 6 weeks and are marked lower quality by
    the caller.
    """
    count = max(0, int(session_count or 0))
    if count == 0:
        return [0] * weeks
    if count == 12:
        return [2, 2, 2, 2, 2, 2]
    if count == 11:
        return [2, 2, 2, 2, 2, 1]
    base = count // weeks
    remainder = count % weeks
    return [base + (1 if idx < remainder else 0) for idx in range(weeks)]


def week_for_session(session_index: int, session_count: int, weeks: int = 6) -> int:
    pattern = session_week_pattern(session_count, weeks=weeks)
    cursor = 0
    for idx, size in enumerate(pattern, start=1):
        cursor += size
        if session_index <= cursor:
            return idx
    return weeks


def infer_deadline(start_date: datetime | None, week_index: int) -> datetime | None:
    if not start_date:
        return None
    # Deadline at the end of the week bucket. Keep time from start_date only if
    # caller provided it; this is still marked INFERRED.
    return start_date + timedelta(days=7 * week_index) - timedelta(seconds=1)


def classify_session_type(title: str | None, block_type: str | None = None, components: list[SessionComponent] | None = None) -> str:
    text = str(title or '').strip().lower()
    if re.search(r'(final\s*test|final|thi\s*cuối|kiem\s*tra\s*cuoi|kiểm\s*tra\s*cuối)', text, re.I):
        return 'FINAL_TEST'
    if re.search(r'(assignment|asm|bài\s*tập\s*lớn|bai\s*tap\s*lon)', text, re.I):
        return 'ASSIGNMENT'
    comps = components or []
    has_video = any(c.block_type == 'video' for c in comps)
    has_quiz = any(c.block_type in {'problem', 'quiz', 'sequential_quiz'} for c in comps)
    if has_video or has_quiz or re.search(r'(?:bài|bai|session|lesson)\s*\d+', text, re.I):
        return 'LEARNING_SESSION'
    if comps:
        return 'SUPPLEMENTARY'
    return 'UNKNOWN'


def _natural_session_sort_key(title: str, index: int) -> tuple[int, int, str]:
    m = re.search(r'(?:bài|bai|session|lesson)\s*(\d+)', (title or '').lower())
    return (int(m.group(1)) if m else 10_000 + index, index, title or '')


def build_session_mappings_from_blocks(
    course_id: str,
    blocks: list[dict[str, Any]],
    *,
    course_start_at: datetime | None = None,
    manual_deadlines: dict[int, datetime] | None = None,
) -> list[CourseSessionMapping]:
    """Map course blocks to Bài/Session -> video/quiz components.

    The adapter accepts already-synced block dictionaries. It does not call Open
    edX directly, so it is safe for tests and production API paths.
    """
    manual_deadlines = manual_deadlines or {}
    sessions: list[dict[str, Any]] = []
    for idx, block in enumerate(blocks):
        block_type = str(block.get('block_type') or block.get('type') or '').lower()
        title = str(block.get('display_name') or block.get('title') or '')
        if block_type in {'sequential', 'session'} or re.search(r'(?:bài|bai|session|lesson)\s*\d+', title.lower()):
            sessions.append({'idx': idx, 'block': block})
    sessions.sort(key=lambda item: _natural_session_sort_key(str(item['block'].get('display_name') or item['block'].get('title') or ''), int(item['idx'])))
    session_count = len(sessions)
    quality = 'GOOD' if session_count in {11, 12} else ('PARTIAL' if session_count > 0 else 'LOW')
    mappings: list[CourseSessionMapping] = []
    for one_based, item in enumerate(sessions, start=1):
        block = item['block']
        title = str(block.get('display_name') or block.get('title') or f'Bài {one_based}')
        usage_key = str(block.get('usage_key') or block.get('id') or f'{course_id}:session:{one_based}')
        week = week_for_session(one_based, session_count or 1)
        deadline = manual_deadlines.get(one_based) or infer_deadline(course_start_at, week)
        source = 'MANUAL' if one_based in manual_deadlines else 'INFERRED'
        children = block.get('children') if isinstance(block.get('children'), list) else []
        components: list[SessionComponent] = []
        for child_idx, child in enumerate(children, start=1):
            if not isinstance(child, dict):
                continue
            btype = str(child.get('block_type') or child.get('type') or '').lower()
            if btype not in {'video', 'problem', 'quiz', 'sequential_quiz'}:
                continue
            components.append(SessionComponent(
                usage_key=str(child.get('usage_key') or child.get('id') or ''),
                block_type=btype,
                title=str(child.get('display_name') or child.get('title') or ''),
                part_index=child_idx if btype == 'video' else None,
                metadata=child,
            ))
        session_type = classify_session_type(title, str(block.get('block_type') or block.get('type') or ''), components)
        mappings.append(CourseSessionMapping(one_based, session_type, usage_key, title, week, deadline, source, quality, components))
    return mappings
