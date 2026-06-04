from __future__ import annotations

import re
from collections import Counter, defaultdict
from dataclasses import dataclass
from difflib import SequenceMatcher
from typing import Iterable

from app.models.question import Question

STOP_WORDS = {
    'trong', 'một', 'của', 'và', 'là', 'được', 'dùng', 'để', 'theo', 'nào', 'gì',
    'khi', 'sau', 'với', 'cho', 'các', 'sau đây', 'đúng', 'mô', 'tả', 'vai', 'trò',
    'chính', 'chức', 'năng', 'lệnh', 'bạn', 'muốn', 'database', 'code', 'model',
}

KEY_TERMS = [
    'entity framework core', 'ef core', 'dbcontext', 'dbset', 'savechanges',
    'migration', 'add-migration', 'update-database', 'schema', 'runtime',
    'problem bank', 'responses api', 'cost control', 'open edx', 'library',
]


def normalize_text(text: str) -> str:
    return re.sub(r'\s+', ' ', re.sub(r'[^\w\s\-]+', ' ', (text or '').lower(), flags=re.UNICODE)).strip()


def concept_key(text: str) -> str:
    normalized = normalize_text(text)
    for term in KEY_TERMS:
        if term in normalized:
            return term
    tokens = [t for t in normalized.split() if len(t) > 2 and t not in STOP_WORDS]
    return ' '.join(tokens[:4]) or normalized[:60] or 'unknown'


def near_duplicate_groups(questions: Iterable[Question], threshold: float = 0.88) -> list[dict]:
    rows = list(questions)
    used: set[str] = set()
    groups: list[dict] = []
    for q in rows:
        if q.id in used:
            continue
        base = normalize_text(q.question_text)
        members = [q]
        used.add(q.id)
        for other in rows:
            if other.id in used:
                continue
            score = SequenceMatcher(None, base, normalize_text(other.question_text)).ratio()
            if score >= threshold:
                members.append(other)
                used.add(other.id)
        if len(members) > 1:
            groups.append({
                'size': len(members),
                'representative_question_id': members[0].id,
                'representative_question_text': members[0].question_text,
                'question_ids': [m.id for m in members],
                'statuses': dict(Counter(m.status for m in members)),
                'difficulties': dict(Counter(m.difficulty for m in members)),
            })
    return groups


def diversity_report(questions: list[Question]) -> dict:
    by_concept: dict[str, list[Question]] = defaultdict(list)
    by_family: dict[str, list[Question]] = defaultdict(list)
    for q in questions:
        key = getattr(q, 'concept_title', None) or getattr(q, 'concept_key', None) or concept_key(q.question_text)
        by_concept[key].append(q)
        family_key = getattr(q, 'question_family_id', None) or f'legacy:{concept_key(q.question_text)}'
        by_family[family_key].append(q)
    concept_rows = []
    for key, items in by_concept.items():
        concept_rows.append({
            'concept': key,
            'count': len(items),
            'question_ids': [q.id for q in items[:10]],
            'sample': items[0].question_text if items else '',
            'difficulty_counts': dict(Counter(q.difficulty for q in items)),
            'status_counts': dict(Counter(q.status for q in items)),
        })
    concept_rows.sort(key=lambda row: row['count'], reverse=True)
    family_rows = []
    for key, items in by_family.items():
        family_rows.append({
            'family_id': key,
            'count': len(items),
            'concept_title': getattr(items[0], 'concept_title', '') if items else '',
            'difficulty_counts': dict(Counter(q.difficulty for q in items)),
            'status_counts': dict(Counter(q.status for q in items)),
            'variant_numbers': [getattr(q, 'variant_no', None) for q in items if getattr(q, 'variant_no', None)],
            'question_ids': [q.id for q in items[:20]],
        })
    family_rows.sort(key=lambda row: row['count'], reverse=True)
    duplicate_groups = near_duplicate_groups(questions)
    total = len(questions)
    overloaded = [row for row in concept_rows if total and row['count'] / total > 0.25 and row['count'] >= 4]
    return {
        'total_questions': total,
        'concept_count': len(concept_rows),
        'top_concepts': concept_rows[:20],
        'overloaded_concepts': overloaded,
        'family_count': len(family_rows),
        'top_families': family_rows[:50],
        'multi_variant_family_count': len([row for row in family_rows if row['count'] > 1]),
        'near_duplicate_group_count': len(duplicate_groups),
        'near_duplicate_groups': duplicate_groups[:50],
        'diversity_score': round(max(0.0, 100.0 - len(duplicate_groups) * 5 - len(overloaded) * 10), 2),
    }
