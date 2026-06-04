from __future__ import annotations

import hashlib
import re
import unicodedata
from dataclasses import dataclass
from typing import Any

from app.models.question import Question


def _ascii_slug(value: object, max_len: int = 60) -> str:
    text = unicodedata.normalize('NFKD', str(value or '').strip().lower()).encode('ascii', 'ignore').decode('ascii')
    text = re.sub(r'[^a-z0-9]+', '-', text).strip('-')
    return (text or 'unknown')[:max_len].strip('-') or 'unknown'


def _short_hash(value: object, size: int = 8) -> str:
    return hashlib.sha1(str(value or '').encode('utf-8')).hexdigest()[:size]


def _course_code(course_id: str) -> str:
    if 'course-v1:' in course_id and '+' in course_id:
        parts = course_id.split(':', 1)[1].split('+')
        if len(parts) >= 2 and parts[1].strip():
            return parts[1].strip()
    parts = course_id.split('+')
    return parts[1].strip() if len(parts) >= 2 and parts[1].strip() else (course_id.rsplit('/', 1)[-1] or course_id)


def _clean_tag(value: object, max_len: int = 96) -> str:
    """Return a tag safe enough for CMS UI filtering.

    The connector sends tags as display strings. We keep them deterministic and
    readable, while avoiding extremely long Open edX block ids in the visible tag
    list. Full ids remain in metadata for backend filtering/debugging.
    """
    text = re.sub(r'\s+', ' ', str(value or '').strip())
    text = text.replace('\n', ' ').replace('\r', ' ')
    return text[:max_len].strip()


@dataclass(frozen=True)
class CMSTagPayload:
    tag_names: list[str]
    tag_map: dict[str, str]

    def as_metadata(self) -> dict[str, Any]:
        return {
            'tag_names': self.tag_names,
            'tags': self.tag_names,
            'tag_map': self.tag_map,
        }


def build_library_tags(course_id: str, chapter_node_id: str, chapter_title: str | None, difficulty: str | None = None) -> CMSTagPayload:
    course = _course_code(course_id).upper()
    chapter_label = _clean_tag(chapter_title or chapter_node_id, 80)

    # v25.9.14.2: one Library per Chapter.  The Library itself only needs
    # course/chapter/AI tags; difficulty/family are component tags.
    tag_map = {
        'ai': 'ai-learning-check',
        'course': f'course:{course}',
        'chapter': f'chapter:{chapter_label}',
        'generated': 'generated',
    }
    return CMSTagPayload(tag_names=_dedupe(tag_map.values()), tag_map=tag_map)


def _family_display_name(question: Question) -> str:
    value = question.concept_title or question.topic or question.learning_objective or question.question_family_id or 'Family'
    return _clean_tag(value, 80)


def build_question_tags(question: Question, target: Any) -> CMSTagPayload:
    diff = (question.difficulty or getattr(target, 'difficulty', None) or 'easy').strip().upper()

    library_tags = build_library_tags(
        question.course_id,
        getattr(target, 'chapter_node_id', '') or question.chapter_node_id or '',
        getattr(target, 'chapter_title', '') or question.chapter_title or '',
        None,
    )
    tag_map = {
        **library_tags.tag_map,
        'family': f'family:{_family_display_name(question)}',
        'difficulty': f'difficulty:{diff}',
    }

    # Standard tag set for the Open edX Library UI:
    # course:MUL211, chapter:Bài 2, family:Vector/Raster,
    # difficulty:EASY/MEDIUM/HARD, ai-learning-check, generated.
    return CMSTagPayload(tag_names=_dedupe(tag_map.values())[:6], tag_map=tag_map)


def merge_tags(current: list | None, generated: list[str]) -> list[str]:
    return _dedupe([*(str(x) for x in (current or []) if x), *generated])


def _dedupe(items: list[str] | tuple[str, ...] | Any) -> list[str]:
    seen: set[str] = set()
    output: list[str] = []
    for item in items:
        text = _clean_tag(item)
        key = text.lower()
        if text and key not in seen:
            seen.add(key)
            output.append(text)
    return output
