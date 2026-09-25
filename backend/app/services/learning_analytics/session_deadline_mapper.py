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
    # All descendant Open edX usage keys under this Bài/chapter, including
    # sequential and vertical containers. Quiz tracking commonly emits the
    # unit/sequential key rather than the problem key itself.
    match_keys: list[str] = field(default_factory=list)

    @property
    def videos(self) -> list[SessionComponent]:
        return [c for c in self.components if c.block_type == 'video']

    @property
    def quiz(self) -> SessionComponent | None:
        quizzes = [c for c in self.components if c.block_type in {'problem', 'quiz', 'sequential_quiz', 'library_content'}]
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
    has_quiz = any(c.block_type in {'problem', 'quiz', 'sequential_quiz', 'library_content'} for c in comps)
    if has_video or has_quiz or re.search(r'(?:bài|bai|session|lesson)\s*\d+', text, re.I):
        return 'LEARNING_SESSION'
    if comps:
        return 'SUPPLEMENTARY'
    return 'UNKNOWN'


def _natural_session_sort_key(title: str, index: int) -> tuple[int, int, str]:
    m = re.search(r'(?:bài|bai|session|lesson)\s*(\d+)', (title or '').lower())
    return (int(m.group(1)) if m else 10_000 + index, index, title or '')


def _block_id(block: dict[str, Any]) -> str:
    return str(
        block.get('usage_key')
        or block.get('block_id')
        or block.get('id')
        or ''
    ).strip()


def _block_type(block: dict[str, Any]) -> str:
    return str(block.get('block_type') or block.get('type') or '').strip().lower()


def _block_title(block: dict[str, Any]) -> str:
    return str(block.get('display_name') or block.get('title') or block.get('name') or '').strip()


def _build_block_index(blocks: list[dict[str, Any]]) -> tuple[dict[str, dict[str, Any]], dict[str, list[str]]]:
    by_id: dict[str, dict[str, Any]] = {}
    children_by_parent: dict[str, list[str]] = {}
    for block in blocks:
        if not isinstance(block, dict):
            continue
        bid = _block_id(block)
        if bid:
            by_id[bid] = block
        parent = str(block.get('parent_block_id') or block.get('parent') or '').strip()
        if parent and bid:
            children_by_parent.setdefault(parent, []).append(bid)
    return by_id, children_by_parent


def _child_blocks(
    block: dict[str, Any],
    *,
    by_id: dict[str, dict[str, Any]],
    children_by_parent: dict[str, list[str]],
) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    seen: set[str] = set()

    explicit = block.get('children') if isinstance(block.get('children'), list) else []
    for child in explicit:
        item: dict[str, Any] | None = None
        if isinstance(child, dict):
            item = child
        else:
            item = by_id.get(str(child or '').strip())
        if not item:
            continue
        cid = _block_id(item)
        key = cid or f'inline:{id(item)}'
        if key in seen:
            continue
        seen.add(key)
        result.append(item)

    parent_id = _block_id(block)
    for cid in children_by_parent.get(parent_id, []):
        if cid in seen:
            continue
        item = by_id.get(cid)
        if not item:
            continue
        seen.add(cid)
        result.append(item)
    return result


def _descendant_keys(
    session_block: dict[str, Any],
    *,
    by_id: dict[str, dict[str, Any]],
    children_by_parent: dict[str, list[str]],
) -> list[str]:
    keys: list[str] = []
    visited: set[str] = set()

    def walk(block: dict[str, Any]) -> None:
        bid = _block_id(block)
        key = bid or f'inline:{id(block)}'
        if key in visited:
            return
        visited.add(key)
        if bid:
            keys.append(bid)
        for child in _child_blocks(
            block,
            by_id=by_id,
            children_by_parent=children_by_parent,
        ):
            walk(child)

    for child in _child_blocks(
        session_block,
        by_id=by_id,
        children_by_parent=children_by_parent,
    ):
        walk(child)
    return keys


def _descendant_components(
    session_block: dict[str, Any],
    *,
    by_id: dict[str, dict[str, Any]],
    children_by_parent: dict[str, list[str]],
) -> list[SessionComponent]:
    components: list[SessionComponent] = []
    visited: set[str] = set()
    part_index = 0

    def walk(block: dict[str, Any]) -> None:
        nonlocal part_index
        bid = _block_id(block)
        key = bid or f'inline:{id(block)}'
        if key in visited:
            return
        visited.add(key)

        btype = _block_type(block)
        if btype in {'video', 'problem', 'quiz', 'sequential_quiz', 'library_content'}:
            if btype == 'video':
                part_index += 1
            components.append(SessionComponent(
                usage_key=bid,
                block_type=btype,
                title=_block_title(block),
                part_index=part_index if btype == 'video' else None,
                metadata=block,
            ))
        for child in _child_blocks(
            block,
            by_id=by_id,
            children_by_parent=children_by_parent,
        ):
            walk(child)

    for child in _child_blocks(
        session_block,
        by_id=by_id,
        children_by_parent=children_by_parent,
    ):
        walk(child)
    return components


def build_session_mappings_from_blocks(
    course_id: str,
    blocks: list[dict[str, Any]],
    *,
    course_start_at: datetime | None = None,
    manual_deadlines: dict[int, datetime] | None = None,
) -> list[CourseSessionMapping]:
    """Map normalized Open edX blocks to Bài/Session -> video/quiz components.

    RealOpenEdXConnector returns a flat block list where children commonly
    contains usage-key strings. Resolve the tree recursively so sequential ->
    vertical -> video/problem/library_content descendants are preserved.
    """
    manual_deadlines = manual_deadlines or {}
    clean_blocks = [block for block in blocks if isinstance(block, dict)]
    by_id, children_by_parent = _build_block_index(clean_blocks)

    chapter_sessions: list[dict[str, Any]] = []
    sequential_sessions: list[dict[str, Any]] = []
    fallback_sessions: list[dict[str, Any]] = []
    leaf_types = {'video', 'problem', 'quiz', 'sequential_quiz', 'library_content', 'html'}

    for idx, block in enumerate(clean_blocks):
        block_type = _block_type(block)
        title = _block_title(block)
        if block_type == 'chapter':
            chapter_sessions.append({'idx': idx, 'block': block})
        elif block_type in {'sequential', 'session'}:
            sequential_sessions.append({'idx': idx, 'block': block})
        elif block_type not in leaf_types and re.search(r'(?:bài|bai|session|lesson)\s*\d+', title.lower()):
            fallback_sessions.append({'idx': idx, 'block': block})

    # Production FPT course structure is typically:
    # chapter (Bài N) -> sequential (Phần 1 / Phần 2 / Quiz) -> vertical
    # -> video/problem. The analytics "Bài/Session" is therefore the chapter,
    # not every sequential. Prefer chapter containers whenever present so a
    # course with 11 Bài and 33 sequentials produces 11 sessions, not 44.
    # Sequential remains a safe fallback for courses without chapters.
    sessions = chapter_sessions or sequential_sessions or fallback_sessions

    sessions.sort(
        key=lambda item: _natural_session_sort_key(
            _block_title(item['block']),
            int(item['idx']),
        )
    )
    session_count = len(sessions)
    quality = 'GOOD' if session_count in {11, 12} else ('PARTIAL' if session_count > 0 else 'LOW')
    mappings: list[CourseSessionMapping] = []

    for one_based, item in enumerate(sessions, start=1):
        block = item['block']
        title = _block_title(block) or f'Bài {one_based}'
        usage_key = _block_id(block) or f'{course_id}:session:{one_based}'
        week = week_for_session(one_based, session_count or 1)
        deadline = manual_deadlines.get(one_based) or infer_deadline(course_start_at, week)
        source = 'MANUAL' if one_based in manual_deadlines else ('INFERRED' if deadline else 'MISSING')

        components = _descendant_components(
            block,
            by_id=by_id,
            children_by_parent=children_by_parent,
        )
        match_keys = _descendant_keys(
            block,
            by_id=by_id,
            children_by_parent=children_by_parent,
        )
        session_type = classify_session_type(
            title,
            _block_type(block),
            components,
        )
        mappings.append(
            CourseSessionMapping(
                one_based,
                session_type,
                usage_key,
                title,
                week,
                deadline,
                source,
                quality,
                components,
                match_keys,
            )
        )
    return mappings
