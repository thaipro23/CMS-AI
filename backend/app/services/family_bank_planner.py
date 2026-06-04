from __future__ import annotations

import math
import re
import unicodedata
from collections import defaultdict
from dataclasses import dataclass
from typing import Any

from sqlalchemy.orm import Session

from app.models.question import Question
from app.services.library_service import ChapterLibraryService

DIFFICULTIES = ('easy', 'medium', 'hard')


def _slug(value: object, max_len: int = 64) -> str:
    text = unicodedata.normalize('NFKD', str(value or '').strip().lower()).encode('ascii', 'ignore').decode('ascii')
    text = re.sub(r'[^a-z0-9]+', '-', text).strip('-')
    return (text or 'family')[:max_len].strip('-') or 'family'


def _difficulty(value: object) -> str:
    diff = str(value or 'easy').strip().lower()
    return diff if diff in DIFFICULTIES else 'easy'


def _course_code(course_id: str) -> str:
    if 'course-v1:' in course_id and '+' in course_id:
        parts = course_id.split(':', 1)[1].split('+')
        if len(parts) >= 2 and parts[1].strip():
            return parts[1].strip().upper()
    parts = course_id.split('+')
    return (parts[1] if len(parts) >= 2 and parts[1].strip() else course_id).upper()


def _family_id(question: Question) -> str:
    if question.question_family_id:
        return question.question_family_id
    base = question.concept_key or question.concept_title or question.topic or question.learning_objective or question.question_text[:80]
    return f'{_slug(base)}-{_difficulty(question.difficulty)}'


def _family_name(question: Question) -> str:
    value = question.concept_title or question.topic or question.learning_objective or question.source_node_title or _family_id(question)
    text = re.sub(r'\s+', ' ', str(value or '').strip())
    if not text:
        text = _family_id(question)
    return text[:80]


def _variant_sort_key(question: Question) -> tuple:
    # Prefer higher quality, already reviewed/published, then stable variant number.
    quality = float(question.quality_score or 0.0)
    status_score = 2 if question.status == 'published' else (1 if question.status == 'approved' else 0)
    variant = question.variant_no or 9999
    return (-status_score, -quality, variant, question.created_at)


def _target_counts(total_questions: int, distribution: dict[str, int] | None = None) -> dict[str, int]:
    total = max(int(total_questions or 0), 1)
    dist = distribution or {'easy': 50, 'medium': 30, 'hard': 20}
    weights = {diff: max(float(dist.get(diff, dist.get(diff.upper(), 0)) or 0), 0.0) for diff in DIFFICULTIES}
    if sum(weights.values()) <= 0:
        weights = {'easy': 50, 'medium': 30, 'hard': 20}
    raw = {diff: total * weights[diff] / sum(weights.values()) for diff in DIFFICULTIES}
    counts = {diff: int(math.floor(raw[diff])) for diff in DIFFICULTIES}
    remaining = total - sum(counts.values())
    for diff in sorted(DIFFICULTIES, key=lambda d: (raw[d] - counts[d]), reverse=True):
        if remaining <= 0:
            break
        counts[diff] += 1
        remaining -= 1
    return counts


@dataclass
class FamilyGroup:
    family_id: str
    family_name: str
    concept_id: str | None
    concept_title: str | None
    difficulty: str
    questions: list[Question]
    score: float

    @property
    def variant_count(self) -> int:
        return len(self.questions)

    def question_ids(self) -> list[str]:
        return [q.id for q in self.questions]


class FamilyBankPlanService:
    """Build editable Family Slot Problem Bank plans.

    A slot is what the teacher will eventually create as one Problem Bank in
    Studio.  Each slot picks exactly 1 component.  The slot may contain one
    family, or up to two families when there are more families than slots and
    the teacher wants compact plans.  When families are insufficient, soft mode
    repeats strong families with warnings instead of silently claiming perfect
    coverage.
    """

    def __init__(self, db: Session):
        self.db = db

    def _families(self, course_id: str, chapter_node_id: str | None = None, statuses: list[str] | None = None) -> dict[str, list[FamilyGroup]]:
        statuses = statuses or ['approved', 'published']
        query = self.db.query(Question).filter(Question.course_id == course_id, Question.status.in_(statuses))
        if chapter_node_id:
            query = query.filter(Question.chapter_node_id == chapter_node_id)
        rows = query.all()
        grouped: dict[tuple[str, str], list[Question]] = defaultdict(list)
        for q in rows:
            grouped[(_difficulty(q.difficulty), _family_id(q))].append(q)
        result: dict[str, list[FamilyGroup]] = {diff: [] for diff in DIFFICULTIES}
        for (diff, family_id), questions in grouped.items():
            questions = sorted(questions, key=_variant_sort_key)
            representative = questions[0]
            avg_quality = sum(float(q.quality_score or 0.0) for q in questions) / max(len(questions), 1)
            # Prefer families with enough variants and good quality.  Keep the
            # formula simple/deterministic so teachers can edit the final plan.
            score = avg_quality + min(len(questions), 5) * 0.15
            result[diff].append(FamilyGroup(
                family_id=family_id,
                family_name=_family_name(representative),
                concept_id=representative.concept_id,
                concept_title=representative.concept_title,
                difficulty=diff,
                questions=questions,
                score=score,
            ))
        for diff in DIFFICULTIES:
            result[diff].sort(key=lambda item: (-item.score, -item.variant_count, item.family_name.lower()))
        return result

    def preview_plan(
        self,
        course_id: str,
        *,
        chapter_node_id: str | None = None,
        total_questions: int = 10,
        difficulty_distribution: dict[str, int] | None = None,
        shortage_policy: str = 'allow_repeat_with_warning',
        max_families_per_bank: int = 2,
    ) -> dict[str, Any]:
        max_families_per_bank = min(max(int(max_families_per_bank or 2), 1), 2)
        counts = _target_counts(total_questions, difficulty_distribution)
        families_by_diff = self._families(course_id, chapter_node_id=chapter_node_id)
        slots: list[dict[str, Any]] = []
        coverage: list[dict[str, Any]] = []
        warnings: list[str] = []
        slot_no = 1

        for diff in DIFFICULTIES:
            target = counts[diff]
            families = families_by_diff.get(diff, [])
            selected_primary = families[:target]
            available = len(families)
            repeated_count = 0
            optional_family_count = 0

            if available >= target:
                base_slots = selected_primary
                extras = families[target:]
                for index, family in enumerate(base_slots):
                    family_list = [family]
                    # If there are more families than required slots, allow at
                    # most two families in one Problem Bank.  The bank still
                    # randoms 1 component, so these extra families become
                    # optional alternatives instead of creating more blocks.
                    if extras and max_families_per_bank > 1:
                        extra = extras.pop(0)
                        family_list.append(extra)
                        optional_family_count += 1
                    slots.append(self._slot_dict(slot_no, diff, family_list, repeated=False))
                    slot_no += 1
                status = 'ok' if optional_family_count == 0 else 'ok_with_optional_families'
            else:
                # Create one slot per available family first.
                for family in families:
                    slots.append(self._slot_dict(slot_no, diff, [family], repeated=False))
                    slot_no += 1
                missing = target - available
                if missing > 0:
                    if shortage_policy == 'strict':
                        warnings.append(f'{diff.upper()} thiếu {missing} family, chỉ tạo được {available}/{target} slot không trùng gốc.')
                    else:
                        # Soft mode: repeat the strongest families.  Each
                        # repeated slot is flagged so UI can warn the teacher.
                        repeat_pool = [fam for fam in families if fam.variant_count >= 2] or families
                        if repeat_pool:
                            for i in range(missing):
                                family = repeat_pool[i % len(repeat_pool)]
                                slots.append(self._slot_dict(slot_no, diff, [family], repeated=True))
                                slot_no += 1
                                repeated_count += 1
                            warnings.append(f'{diff.upper()} thiếu {missing} family nên đã lặp {repeated_count} slot family. Giáo viên nên kiểm tra trước khi đẩy sang Open edX.')
                        else:
                            warnings.append(f'{diff.upper()} không có family nào để tạo slot.')
                status = 'insufficient_family' if shortage_policy == 'strict' and available < target else ('ok_with_repeated_family' if repeated_count else 'ok')

            coverage.append({
                'difficulty': diff.upper(),
                'target_slots': target,
                'available_families': available,
                'selected_slots': len([s for s in slots if s['difficulty'].lower() == diff]),
                'optional_family_count': optional_family_count,
                'repeated_slot_count': repeated_count,
                'status': status,
            })

        combination_count = 1
        for slot in slots:
            variant_count = int(slot.get('variant_count') or 0)
            combination_count *= max(variant_count, 1)
            if combination_count > 10**12:
                combination_count = 10**12
                break

        return {
            'ok': True,
            'course_id': course_id,
            'chapter_node_id': chapter_node_id,
            'total_questions': int(total_questions),
            'target_counts': {key.upper(): value for key, value in counts.items()},
            'shortage_policy': shortage_policy,
            'max_families_per_bank': max_families_per_bank,
            'coverage': coverage,
            'slots': slots,
            'warnings': warnings,
            'combination_count_estimate': combination_count,
            'message': 'Kế hoạch có lặp family cần review.' if warnings else 'Kế hoạch family slot hợp lệ.',
        }

    def _slot_dict(self, slot_no: int, difficulty: str, families: list[FamilyGroup], *, repeated: bool) -> dict[str, Any]:
        questions: list[Question] = []
        for family in families:
            questions.extend(family.questions)
        # Deduplicate while preserving order.
        seen: set[str] = set()
        unique_questions: list[Question] = []
        for q in questions:
            if q.id not in seen:
                seen.add(q.id)
                unique_questions.append(q)
        return {
            'slot_no': slot_no,
            'difficulty': difficulty.upper(),
            'pick_count': 1,
            'repeated_family': repeated,
            'families': [
                {
                    'family_id': fam.family_id,
                    'family_name': fam.family_name,
                    'concept_id': fam.concept_id,
                    'concept_title': fam.concept_title,
                    'variant_count': fam.variant_count,
                    'question_ids': fam.question_ids(),
                } for fam in families
            ],
            'family_names': [fam.family_name for fam in families],
            'question_ids': [q.id for q in unique_questions],
            'variant_count': len(unique_questions),
            'rule': f'random 1/{max(len(unique_questions), 1)} variants',
            'warning': 'Lặp family do không đủ family khác nhau.' if repeated else '',
        }

    def selected_question_ids_from_plan(self, plan: dict[str, Any]) -> list[str]:
        ids: list[str] = []
        seen: set[str] = set()
        for slot in plan.get('slots') or []:
            for qid in slot.get('question_ids') or []:
                if qid and qid not in seen:
                    seen.add(qid)
                    ids.append(qid)
        return ids
