from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from typing import Iterable

from app.models.question import Question

DIFFICULTIES = ('easy', 'medium', 'hard')


def normalize_difficulty(value: object) -> str:
    difficulty = str(value or 'easy').strip().lower()
    return difficulty if difficulty in DIFFICULTIES else 'easy'


def normalize_visible_text(value: object) -> str:
    """Normalize learner-visible text for deterministic exact-duplicate checks."""
    text = unicodedata.normalize('NFKC', str(value or '')).casefold()
    text = re.sub(r'[^\w\s]+', ' ', text, flags=re.UNICODE)
    return re.sub(r'\s+', ' ', text).strip()


def question_content_fingerprint(question: Question) -> str:
    """Return a conservative identity for a learner-visible question.

    The stem is the primary identity. If the stem is blank, normalized choices
    are used as a fallback. The same fingerprint may never be assigned to more
    than one Family Slot.
    """
    stem = normalize_visible_text(getattr(question, 'question_text', ''))
    if not stem:
        options = sorted(
            normalize_visible_text(getattr(question, name, ''))
            for name in ('option_a', 'option_b', 'option_c', 'option_d')
        )
        stem = json.dumps(options, ensure_ascii=False)
    return hashlib.sha256(stem.encode('utf-8')).hexdigest()


class _UnionFind:
    def __init__(self, ids: Iterable[str]):
        self.parent = {value: value for value in ids}

    def find(self, value: str) -> str:
        parent = self.parent[value]
        if parent != value:
            self.parent[value] = self.find(parent)
        return self.parent[value]

    def union(self, left: str, right: str) -> None:
        root_left = self.find(left)
        root_right = self.find(right)
        if root_left != root_right:
            self.parent[root_right] = root_left


def _canonical_sort_key(question: Question) -> tuple:
    component = str(getattr(question, 'openedx_library_problem_id', '') or '').strip().strip('"\'')
    status = str(getattr(question, 'status', '') or '').lower()
    return (
        -int(bool(component)),
        -int(status == 'published'),
        int(bool(getattr(question, 'is_duplicate', False))),
        -float(getattr(question, 'quality_score', 0.0) or 0.0),
        str(getattr(question, 'created_at', '') or ''),
        str(question.id),
    )


@dataclass
class QuestionIdentityUnit:
    """One unique learner-visible question, possibly backed by duplicate DB rows."""

    unit_id: str
    difficulty: str
    questions: list[Question]
    fingerprint_keys: list[str]
    component_ids: list[str]
    family_ids: list[str]
    concept_keys: list[str]
    mixed_difficulties: list[str] = field(default_factory=list)

    @property
    def canonical_question(self) -> Question:
        return self.questions[0]

    @property
    def question_ids(self) -> list[str]:
        return [str(self.canonical_question.id)] if self.questions else []

    @property
    def all_record_question_ids(self) -> list[str]:
        return [str(question.id) for question in self.questions]

    @property
    def duplicate_record_question_ids(self) -> list[str]:
        return [str(question.id) for question in self.questions[1:]]

    @property
    def record_count(self) -> int:
        return len(self.questions)


def build_identity_units(questions: list[Question]) -> tuple[list[QuestionIdentityUnit], list[str]]:
    """Collapse exact duplicate rows/components into canonical identity units.

    This is deterministic and does not call an LLM. A duplicated DB row is not
    assigned extra random weight because that would allow the same learner-
    visible question to appear more than once.
    """
    if not questions:
        return [], []

    ids = [str(question.id) for question in questions]
    union = _UnionFind(ids)
    by_fingerprint: dict[str, str] = {}
    by_question_hash: dict[str, str] = {}
    by_component: dict[str, str] = {}

    for question in questions:
        qid = str(question.id)
        fingerprint = question_content_fingerprint(question)
        previous = by_fingerprint.get(fingerprint)
        if previous:
            union.union(qid, previous)
        else:
            by_fingerprint[fingerprint] = qid

        question_hash = str(getattr(question, 'question_hash', '') or '').strip()
        if question_hash:
            previous = by_question_hash.get(question_hash)
            if previous:
                union.union(qid, previous)
            else:
                by_question_hash[question_hash] = qid

        component_id = str(getattr(question, 'openedx_library_problem_id', '') or '').strip().strip('"\'')
        if component_id:
            previous = by_component.get(component_id)
            if previous:
                union.union(qid, previous)
            else:
                by_component[component_id] = qid

    grouped: dict[str, list[Question]] = defaultdict(list)
    for question in questions:
        grouped[union.find(str(question.id))].append(question)

    units: list[QuestionIdentityUnit] = []
    warnings: list[str] = []
    for members in grouped.values():
        members = sorted(members, key=_canonical_sort_key)
        diff_counts = Counter(normalize_difficulty(getattr(question, 'difficulty', None)) for question in members)
        difficulty = sorted(DIFFICULTIES, key=lambda diff: (-diff_counts[diff], DIFFICULTIES.index(diff)))[0]
        mixed = [diff for diff, count in diff_counts.items() if count and diff != difficulty]
        stable_key = '|'.join(sorted(str(question.id) for question in members))
        unit_id = f'identity-{hashlib.sha256(stable_key.encode("utf-8")).hexdigest()[:16]}'
        units.append(QuestionIdentityUnit(
            unit_id=unit_id,
            difficulty=difficulty,
            questions=members,
            fingerprint_keys=sorted({question_content_fingerprint(question) for question in members}),
            component_ids=sorted({
                str(getattr(question, 'openedx_library_problem_id', '') or '').strip().strip('"\'')
                for question in members
                if str(getattr(question, 'openedx_library_problem_id', '') or '').strip().strip('"\'')
            }),
            family_ids=sorted({
                str(getattr(question, 'question_family_id', '') or '').strip()
                for question in members
                if str(getattr(question, 'question_family_id', '') or '').strip()
            }),
            concept_keys=sorted({
                str(getattr(question, 'concept_key', '') or '').strip()
                for question in members
                if str(getattr(question, 'concept_key', '') or '').strip()
            }),
            mixed_difficulties=mixed,
        ))
        if len(members) > 1:
            warnings.append(
                f'{len(members)} bản ghi biểu diễn cùng một câu; dùng bản canonical {members[0].id} và loại '
                f'{len(members) - 1} bản trùng khỏi kế hoạch để không tăng trọng số random.'
            )
        if mixed:
            warnings.append(
                f'Identity unit {unit_id} có difficulty không đồng nhất; dùng {difficulty.upper()} cho bản canonical.'
            )

    units.sort(key=lambda unit: (DIFFICULTIES.index(unit.difficulty), str(unit.canonical_question.id)))
    return units, list(dict.fromkeys(warnings))
