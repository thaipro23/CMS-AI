from __future__ import annotations

import re
import unicodedata
from collections.abc import Iterable, Mapping
from typing import Any


QUIZ_LABEL = re.compile(
    r'\b(?:quiz|learning\s*check|lc)\s*#?\s*(\d{1,3})\b',
    re.IGNORECASE,
)
LABEL_FIELDS = ('name', 'label', 'display_name', 'title')
MERGED_FIELDS = (
    'deadline_date',
    'available_from',
    'submitted_at',
    'deadline_mode',
    'schedule_warning',
    'quiz_status',
    'source',
    'category',
    'weight',
    'possible',
)


def _positive_int(value: Any) -> int | None:
    try:
        number = int(value)
    except (TypeError, ValueError):
        return None
    return number if 1 <= number <= 999 else None


def _normalize_label(value: Any) -> str:
    normalized = unicodedata.normalize('NFKC', str(value or '')).strip().lower()
    return re.sub(r'\s+', ' ', normalized)


def canonical_assessment_identity(item: Mapping[str, Any]) -> str | None:
    explicit = _positive_int(item.get('quiz_number'))
    labels = [str(item.get(key) or '').strip() for key in LABEL_FIELDS]
    match = QUIZ_LABEL.search(' '.join(label for label in labels if label))
    assessment_type = str(item.get('assessment_type') or '').strip().lower()
    number = (
        _positive_int(match.group(1))
        if match
        else explicit if assessment_type == 'quiz' else None
    )
    if number:
        return f'quiz:{number}'
    if assessment_type == 'final_test' or any(
        _normalize_label(label) == 'final test'
        for label in labels
    ):
        return 'final_test'
    return None


def _has_score(item: Mapping[str, Any]) -> bool:
    return item.get('percent') is not None or item.get('earned') is not None


def _preference(item: Mapping[str, Any]) -> tuple[int, int, int]:
    scored = _has_score(item)
    planned = bool(item.get('planned'))
    return (
        int(scored and not planned),
        int(scored),
        int(not planned),
    )


def canonical_assessment_components(
    items: Iterable[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for raw in items:
        if not isinstance(raw, Mapping):
            continue
        item = dict(raw)
        identity = canonical_assessment_identity(item)
        if identity is not None:
            grouped.setdefault(identity, []).append(item)

    canonical: list[dict[str, Any]] = []
    for identity, rows in grouped.items():
        preferred = max(rows, key=_preference)
        merged = dict(preferred)
        for field in MERGED_FIELDS:
            if merged.get(field) not in (None, ''):
                continue
            for row in rows:
                if row.get(field) not in (None, ''):
                    merged[field] = row[field]
                    break
        if identity.startswith('quiz:'):
            number = int(identity.split(':', 1)[1])
            merged.update({
                'key': identity,
                'name': f'Quiz {number}',
                'quiz_number': number,
                'assessment_type': 'quiz',
            })
        else:
            merged.update({
                'key': 'final_test',
                'name': 'Final test',
                'quiz_number': None,
                'assessment_type': 'final_test',
            })
        canonical.append(merged)

    return sorted(
        canonical,
        key=lambda item: (
            1 if item['key'] == 'final_test' else 0,
            int(item.get('quiz_number') or 0),
        ),
    )
