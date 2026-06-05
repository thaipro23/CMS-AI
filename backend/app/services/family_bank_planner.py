from __future__ import annotations

import math
from collections import defaultdict
from dataclasses import dataclass
from typing import Any

from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.question import Question
from app.services.question_family import (
    reconcile_question_families,
    stable_family_id_for_question,
    stable_family_name,
)
from app.services.question_identity import (
    DIFFICULTIES,
    QuestionIdentityUnit,
    build_identity_units,
    normalize_difficulty,
    question_content_fingerprint,
)


def _target_counts(total_questions: int, distribution: dict[str, int] | None = None) -> dict[str, int]:
    total = max(int(total_questions or 0), 1)
    dist = distribution or {'easy': 50, 'medium': 30, 'hard': 20}
    weights = {diff: max(float(dist.get(diff, dist.get(diff.upper(), 0)) or 0), 0.0) for diff in DIFFICULTIES}
    if sum(weights.values()) <= 0:
        weights = {'easy': 50, 'medium': 30, 'hard': 20}
    raw = {diff: total * weights[diff] / sum(weights.values()) for diff in DIFFICULTIES}
    counts = {diff: int(math.floor(raw[diff])) for diff in DIFFICULTIES}
    remaining = total - sum(counts.values())
    for diff in sorted(DIFFICULTIES, key=lambda item: (raw[item] - counts[item], -DIFFICULTIES.index(item)), reverse=True):
        if remaining <= 0:
            break
        counts[diff] += 1
        remaining -= 1
    return counts


@dataclass
class StableFamilyGroup:
    family_id: str
    family_name: str
    difficulty: str
    concept_id: str | None
    concept_title: str | None
    units: list[QuestionIdentityUnit]
    average_quality: float

    @property
    def question_ids(self) -> list[str]:
        return [question_id for unit in self.units for question_id in unit.question_ids]

    @property
    def variant_count(self) -> int:
        return len(self.question_ids)


class FamilyBankPlanService:
    """Deterministic Family Slot planner based on existing concept metadata.

    GPT/concept extraction already runs before questions are stored. This planner
    never sends approved questions to GPT again. It reconciles stable family IDs,
    keeps each stable family wholly inside exactly one slot, uses every unique
    approved/published question exactly once, and rejects any duplicate question,
    Open edX component or visible-content fingerprint before publish/insert.
    """

    def __init__(self, db: Session):
        self.db = db

    def _eligible_questions(
        self,
        course_id: str,
        chapter_node_id: str | None = None,
        statuses: list[str] | None = None,
    ) -> list[Question]:
        statuses = statuses or ['approved', 'published']
        query = self.db.query(Question).filter(Question.course_id == course_id, Question.status.in_(statuses))
        if chapter_node_id:
            query = query.filter(Question.chapter_node_id == chapter_node_id)
        return list(query.all())

    @staticmethod
    def _family_groups(units: list[QuestionIdentityUnit]) -> dict[str, list[StableFamilyGroup]]:
        grouped: dict[tuple[str, str], list[QuestionIdentityUnit]] = defaultdict(list)
        for unit in units:
            question = unit.canonical_question
            difficulty = normalize_difficulty(getattr(question, 'difficulty', None))
            grouped[(difficulty, stable_family_id_for_question(question))].append(unit)

        result: dict[str, list[StableFamilyGroup]] = {difficulty: [] for difficulty in DIFFICULTIES}
        for (difficulty, family_id), family_units in grouped.items():
            family_units.sort(key=lambda unit: (
                int(getattr(unit.canonical_question, 'variant_no', 0) or 0),
                str(getattr(unit.canonical_question, 'created_at', '') or ''),
                str(unit.canonical_question.id),
            ))
            questions = [unit.canonical_question for unit in family_units]
            representative = questions[0]
            average_quality = sum(float(getattr(question, 'quality_score', 0.0) or 0.0) for question in questions) / max(len(questions), 1)
            result[difficulty].append(StableFamilyGroup(
                family_id=family_id,
                family_name=stable_family_name(representative),
                difficulty=difficulty,
                concept_id=getattr(representative, 'concept_id', None),
                concept_title=getattr(representative, 'concept_title', None),
                units=family_units,
                average_quality=average_quality,
            ))

        for difficulty in DIFFICULTIES:
            result[difficulty].sort(key=lambda family: (-family.variant_count, -family.average_quality, family.family_name.casefold(), family.family_id))
        return result

    @staticmethod
    def _effective_slot_targets(
        families: dict[str, list[StableFamilyGroup]],
        requested_targets: dict[str, int],
    ) -> tuple[dict[str, int], list[str]]:
        warnings: list[str] = []
        available = {difficulty: len(families[difficulty]) for difficulty in DIFFICULTIES}
        requested_total = sum(requested_targets.values())
        total_families = sum(available.values())
        nonempty = [difficulty for difficulty in DIFFICULTIES if available[difficulty] > 0]

        # Never split or repeat a stable family merely to reach a requested slot
        # count. If fewer families exist, the plan contains fewer slots.
        desired_total = min(requested_total, total_families)
        if desired_total < len(nonempty):
            desired_total = len(nonempty)
            warnings.append(
                f'Yêu cầu {requested_total} slot nhưng có câu ở {len(nonempty)} mức độ; tạo {desired_total} slot tối thiểu '
                'để dùng đủ câu mà không trộn difficulty trong một Problem Bank.'
            )
        if requested_total > total_families:
            warnings.append(
                f'Yêu cầu {requested_total} slot nhưng chỉ có {total_families} stable family; giảm còn {total_families} slot '
                'thay vì lặp hoặc tách cùng family sang nhiều slot.'
            )

        effective = {difficulty: min(requested_targets[difficulty], available[difficulty]) for difficulty in DIFFICULTIES}
        # Every non-empty difficulty needs at least one slot so all questions are used.
        for difficulty in nonempty:
            if effective[difficulty] == 0:
                effective[difficulty] = 1
                warnings.append(
                    f'{difficulty.upper()} được phân bổ 1 slot dù tỷ lệ yêu cầu là 0, vì đang có câu approved/published '
                    'và chế độ require_all_approved phải sử dụng toàn bộ câu duy nhất.'
                )

        while sum(effective.values()) > desired_total:
            candidates = [difficulty for difficulty in DIFFICULTIES if effective[difficulty] > 1]
            if not candidates:
                break
            chosen = max(candidates, key=lambda difficulty: (effective[difficulty] - requested_targets[difficulty], effective[difficulty], -DIFFICULTIES.index(difficulty)))
            effective[chosen] -= 1

        reallocated = 0
        while sum(effective.values()) < desired_total:
            candidates = [difficulty for difficulty in DIFFICULTIES if effective[difficulty] < available[difficulty]]
            if not candidates:
                break
            chosen = max(candidates, key=lambda difficulty: (
                available[difficulty] - effective[difficulty],
                requested_targets[difficulty] - effective[difficulty],
                -DIFFICULTIES.index(difficulty),
            ))
            effective[chosen] += 1
            reallocated += 1
        if reallocated:
            warnings.append(
                f'Đã phân bổ lại {reallocated} slot sang mức độ còn nhiều stable family để tận dụng toàn bộ câu mà không lặp family.'
            )
        return effective, warnings

    @staticmethod
    def _pack_families(
        families: dict[str, list[StableFamilyGroup]],
        requested_targets: dict[str, int],
        effective_targets: dict[str, int],
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[str]]:
        slots: list[dict[str, Any]] = []
        coverage: list[dict[str, Any]] = []
        warnings: list[str] = []
        slot_no = 1

        for difficulty in DIFFICULTIES:
            family_rows = list(families[difficulty])
            target = requested_targets[difficulty]
            actual_target = effective_targets[difficulty]
            if not family_rows:
                coverage.append({
                    'difficulty': difficulty.upper(),
                    'target_slots': target,
                    'available_families': 0,
                    'selected_slots': 0,
                    'optional_family_count': 0,
                    'repeated_slot_count': 0,
                    'status': 'no_questions' if target else 'not_requested',
                })
                continue

            if actual_target <= 0:
                raise ValueError(f'Không thể dùng đủ câu {difficulty.upper()} vì số slot thực tế bằng 0.')

            # Bin-pack complete stable families. A family is never split across
            # slots, so one learner attempt cannot receive two questions from the
            # same concept+difficulty family.
            bins: list[list[StableFamilyGroup]] = [[] for _ in range(actual_target)]
            loads = [0 for _ in range(actual_target)]
            for family in family_rows:
                index = min(range(actual_target), key=lambda idx: (loads[idx], len(bins[idx]), idx))
                bins[index].append(family)
                loads[index] += family.variant_count

            for bucket in bins:
                if not bucket:
                    continue
                family_payloads: list[dict[str, Any]] = []
                question_ids: list[str] = []
                for family in bucket:
                    family_questions = family.question_ids
                    question_ids.extend(family_questions)
                    family_payloads.append({
                        'family_id': family.family_id,
                        'family_name': family.family_name,
                        'concept_id': family.concept_id,
                        'concept_title': family.concept_title,
                        'variant_count': len(family_questions),
                        'question_ids': family_questions,
                        'source_family_ids': [family.family_id],
                        'ai_generated': False,
                        'reason': 'Stable family từ concept metadata đã có; không gọi GPT ở bước lập kế hoạch.',
                    })
                question_ids = list(dict.fromkeys(question_ids))
                slots.append({
                    'slot_no': slot_no,
                    'difficulty': difficulty.upper(),
                    'pick_count': 1,
                    'repeated_family': False,
                    'families': family_payloads,
                    'family_names': [family['family_name'] for family in family_payloads],
                    'question_ids': question_ids,
                    'variant_count': len(question_ids),
                    'rule': f'random 1/{max(len(question_ids), 1)} variants',
                    'warning': '',
                })
                slot_no += 1

            selected = len([slot for slot in slots if slot['difficulty'] == difficulty.upper()])
            optional = sum(max(len(slot['families']) - 1, 0) for slot in slots if slot['difficulty'] == difficulty.upper())
            status = 'stable_family_exact' if selected == target else ('reallocated_no_duplicate' if selected > target else 'reduced_no_duplicate')
            coverage.append({
                'difficulty': difficulty.upper(),
                'target_slots': target,
                'available_families': len(family_rows),
                'selected_slots': selected,
                'optional_family_count': optional,
                'repeated_slot_count': 0,
                'status': status,
            })
            if selected != target:
                warnings.append(
                    f'{difficulty.upper()} yêu cầu {target} slot, thực tế {selected} slot theo số stable family và chính sách không lặp/tách family.'
                )

        return slots, coverage, list(dict.fromkeys(warnings))

    async def preview_optimized_plan(
        self,
        course_id: str,
        *,
        chapter_node_id: str | None = None,
        total_questions: int = 10,
        difficulty_distribution: dict[str, int] | None = None,
        require_all_approved: bool | None = None,
    ) -> dict[str, Any]:
        require_all = bool(settings.family_plan_require_all_approved) or bool(require_all_approved)
        initial_questions = self._eligible_questions(course_id, chapter_node_id)
        if not initial_questions:
            raise ValueError('Không có câu approved/published phù hợp để lập kế hoạch.')
        distinct_chapters = {
            str(getattr(question, 'chapter_node_id', '') or '').strip()
            for question in initial_questions
            if str(getattr(question, 'chapter_node_id', '') or '').strip()
        }
        if not chapter_node_id and len(distinct_chapters) > 1:
            raise ValueError(
                f'Có câu hỏi thuộc {len(distinct_chapters)} Chapter khác nhau. Hãy chọn đúng Chapter trước khi tính kế hoạch, '
                'vì mỗi Family Slot Plan chỉ được dùng một Chapter Library.'
            )

        reconciliation = reconcile_question_families(
            self.db,
            course_id,
            chapter_node_id=chapter_node_id,
            commit=bool(settings.family_plan_reconcile_on_preview),
        )
        questions = self._eligible_questions(course_id, chapter_node_id)
        units, identity_warnings = build_identity_units(questions)
        if not units:
            raise ValueError('Không còn câu duy nhất hợp lệ sau khi loại bản ghi trùng.')

        families = self._family_groups(units)
        requested_targets = _target_counts(total_questions, difficulty_distribution)
        effective_targets, target_warnings = self._effective_slot_targets(families, requested_targets)
        slots, coverage, packing_warnings = self._pack_families(families, requested_targets, effective_targets)
        warnings = list(dict.fromkeys(identity_warnings + target_warnings + packing_warnings))

        combination_count = 1
        for slot in slots:
            combination_count *= max(int(slot.get('variant_count') or 0), 1)
            if combination_count > 10**12:
                combination_count = 10**12
                break

        plan: dict[str, Any] = {
            'ok': True,
            'course_id': course_id,
            'chapter_node_id': chapter_node_id,
            'total_questions': len(slots),
            'requested_total_questions': int(total_questions),
            'target_counts': {key.upper(): value for key, value in requested_targets.items()},
            'effective_target_counts': {key.upper(): value for key, value in effective_targets.items()},
            'shortage_policy': 'never_repeat_or_split_stable_family',
            'max_families_per_bank': max([len(slot.get('families') or []) for slot in slots] or [1]),
            'coverage': coverage,
            'slots': slots,
            'warnings': warnings,
            'combination_count_estimate': combination_count,
            'planner_engine': 'stable_family_deterministic_v1',
            'planner_mode': 'deterministic_existing_concepts',
            'uses_llm': False,
            'family_reconciliation': reconciliation,
            'eligible_question_count': len(units),
            'eligible_record_count': len(questions),
            'identity_unit_count': len(units),
            'exact_duplicate_record_count': sum(max(unit.record_count - 1, 0) for unit in units),
            'excluded_duplicate_question_ids': [question_id for unit in units for question_id in unit.duplicate_record_question_ids][:100],
            'stable_family_count': sum(len(rows) for rows in families.values()),
            'require_all_approved': require_all,
        }
        guard = self.validate_plan(course_id, plan, require_all=require_all)
        plan['hard_guard'] = guard
        plan['assigned_question_count'] = guard['assigned_question_count']
        if not guard['valid']:
            raise RuntimeError(f'Hard Duplicate Guard từ chối kế hoạch: {guard["summary"]}')
        plan['message'] = (
            f'Đã chuẩn hóa family và tính kế hoạch bằng thuật toán xác định; dùng {guard["assigned_question_count"]}/'
            f'{guard["eligible_question_count"]} câu duy nhất đúng một lần trong {len(slots)} slot. Không gọi GPT ở bước này.'
        )
        return plan

    # Backward-compatible method name for older internal callers. It is now
    # deterministic and never calls GPT, regardless of planner_mode.
    async def preview_ai_plan(self, course_id: str, **kwargs: Any) -> dict[str, Any]:
        kwargs.pop('planner_mode', None)
        return await self.preview_optimized_plan(course_id, **kwargs)

    def validate_plan(self, course_id: str, plan: dict[str, Any], *, require_all: bool | None = None) -> dict[str, Any]:
        require_all = bool(settings.family_plan_require_all_approved) or bool(require_all)
        chapter_node_id = plan.get('chapter_node_id')
        eligible = self._eligible_questions(course_id, chapter_node_id)
        units, _ = build_identity_units(eligible)
        all_by_id = {str(question.id): question for question in eligible}
        by_id: dict[str, Question] = {}
        duplicate_alias_to_canonical: dict[str, str] = {}
        stable_family_by_id: dict[str, str] = {}
        for unit in units:
            canonical = unit.canonical_question
            canonical_id = str(canonical.id)
            by_id[canonical_id] = canonical
            stable_family_by_id[canonical_id] = stable_family_id_for_question(canonical)
            for alias_id in unit.duplicate_record_question_ids:
                duplicate_alias_to_canonical[alias_id] = canonical_id

        eligible_ids = set(by_id)
        question_slots: dict[str, set[int]] = defaultdict(set)
        component_slots: dict[str, set[int]] = defaultdict(set)
        fingerprint_slots: dict[str, set[int]] = defaultdict(set)
        family_slots: dict[str, set[int]] = defaultdict(set)
        unknown_ids: set[str] = set()
        duplicate_record_ids_in_plan: set[str] = set()
        duplicate_inside_slot: set[str] = set()
        duplicate_component_inside_slot: set[str] = set()
        duplicate_fingerprint_inside_slot: set[str] = set()
        family_mismatch_question_ids: set[str] = set()
        family_mismatch_slots: list[int] = []
        difficulty_mismatch_question_ids: set[str] = set()
        empty_slots: list[int] = []
        mixed_scope_slots: list[int] = []

        for index, slot in enumerate(plan.get('slots') or [], start=1):
            slot_no = int(slot.get('slot_no') or index)
            raw_ids = [str(value) for value in (slot.get('question_ids') or []) if str(value).strip()]
            slot_difficulty = normalize_difficulty(slot.get('difficulty'))
            listed_family_ids = {
                str(family.get('family_id') or '').strip()
                for family in (slot.get('families') or [])
                if isinstance(family, dict) and str(family.get('family_id') or '').strip()
            }
            if not raw_ids:
                empty_slots.append(slot_no)
            seen_inside: set[str] = set()
            components_inside: set[str] = set()
            fingerprints_inside: set[str] = set()
            slot_scopes: set[str] = set()
            actual_family_ids: set[str] = set()
            for question_id in raw_ids:
                if question_id in seen_inside:
                    duplicate_inside_slot.add(question_id)
                seen_inside.add(question_id)
                if question_id in duplicate_alias_to_canonical:
                    duplicate_record_ids_in_plan.add(question_id)
                    continue
                question = by_id.get(question_id)
                if question is None:
                    if question_id in all_by_id:
                        duplicate_record_ids_in_plan.add(question_id)
                    else:
                        unknown_ids.add(question_id)
                    continue
                stable_family_id = stable_family_by_id[question_id]
                actual_family_ids.add(stable_family_id)
                family_slots[stable_family_id].add(slot_no)
                if stable_family_id not in listed_family_ids:
                    family_mismatch_question_ids.add(question_id)
                if normalize_difficulty(getattr(question, 'difficulty', None)) != slot_difficulty:
                    difficulty_mismatch_question_ids.add(question_id)
                question_slots[question_id].add(slot_no)
                scope_key = str(getattr(question, 'target_library_key', None) or getattr(question, 'chapter_node_id', None) or '').strip()
                if scope_key:
                    slot_scopes.add(scope_key)
                component_id = str(getattr(question, 'openedx_library_problem_id', '') or '').strip().strip('"\'')
                if component_id:
                    if component_id in components_inside:
                        duplicate_component_inside_slot.add(component_id)
                    components_inside.add(component_id)
                    component_slots[component_id].add(slot_no)
                fingerprint = question_content_fingerprint(question)
                if fingerprint in fingerprints_inside:
                    duplicate_fingerprint_inside_slot.add(fingerprint)
                fingerprints_inside.add(fingerprint)
                fingerprint_slots[fingerprint].add(slot_no)
            if listed_family_ids != actual_family_ids:
                family_mismatch_slots.append(slot_no)
            if len(slot_scopes) > 1:
                mixed_scope_slots.append(slot_no)

        assigned_ids = set(question_slots)
        duplicate_question_ids = sorted(question_id for question_id, locations in question_slots.items() if len(locations) > 1)
        duplicate_component_ids = sorted(component_id for component_id, locations in component_slots.items() if len(locations) > 1)
        duplicate_fingerprints = sorted(fingerprint for fingerprint, locations in fingerprint_slots.items() if len(locations) > 1)
        duplicate_family_ids = sorted(family_id for family_id, locations in family_slots.items() if len(locations) > 1)
        missing_ids = sorted(eligible_ids - assigned_ids)
        valid = not (
            duplicate_question_ids
            or duplicate_component_ids
            or duplicate_fingerprints
            or duplicate_family_ids
            or duplicate_record_ids_in_plan
            or unknown_ids
            or duplicate_inside_slot
            or duplicate_component_inside_slot
            or duplicate_fingerprint_inside_slot
            or family_mismatch_question_ids
            or family_mismatch_slots
            or difficulty_mismatch_question_ids
            or empty_slots
            or mixed_scope_slots
            or (require_all and missing_ids)
        )

        summary_parts: list[str] = []
        if duplicate_question_ids:
            summary_parts.append(f'{len(duplicate_question_ids)} question_id nằm ở nhiều slot')
        if duplicate_component_ids:
            summary_parts.append(f'{len(duplicate_component_ids)} Open edX component nằm ở nhiều slot')
        if duplicate_fingerprints:
            summary_parts.append(f'{len(duplicate_fingerprints)} nội dung câu giống nhau nằm ở nhiều slot')
        if duplicate_family_ids:
            summary_parts.append(f'{len(duplicate_family_ids)} stable family bị tách qua nhiều slot')
        if duplicate_record_ids_in_plan:
            summary_parts.append(f'{len(duplicate_record_ids_in_plan)} bản ghi trùng được đưa vào plan thay vì bản canonical')
        if duplicate_inside_slot:
            summary_parts.append(f'{len(duplicate_inside_slot)} question_id bị lặp trong cùng slot')
        if duplicate_component_inside_slot:
            summary_parts.append(f'{len(duplicate_component_inside_slot)} Open edX component bị lặp trong cùng slot')
        if duplicate_fingerprint_inside_slot:
            summary_parts.append(f'{len(duplicate_fingerprint_inside_slot)} nội dung câu giống nhau bị lặp trong cùng slot')
        if family_mismatch_question_ids:
            summary_parts.append(f'{len(family_mismatch_question_ids)} câu nằm sai stable family của slot')
        if family_mismatch_slots:
            summary_parts.append(f'{len(family_mismatch_slots)} slot khai báo family không khớp câu thực tế')
        if difficulty_mismatch_question_ids:
            summary_parts.append(f'{len(difficulty_mismatch_question_ids)} câu nằm sai difficulty của slot')
        if unknown_ids:
            summary_parts.append(f'{len(unknown_ids)} question_id không thuộc tập approved/published')
        if require_all and missing_ids:
            summary_parts.append(f'{len(missing_ids)} câu approved/published duy nhất chưa được sử dụng')
        if empty_slots:
            summary_parts.append(f'{len(empty_slots)} slot rỗng')
        if mixed_scope_slots:
            summary_parts.append(f'{len(mixed_scope_slots)} slot trộn nhiều Chapter/Library')
        if not summary_parts:
            summary_parts.append('Kế hoạch hợp lệ: mọi câu duy nhất và mọi stable family được dùng đúng một lần, không trùng trong hoặc giữa các slot')

        return {
            'valid': valid,
            'mode': 'all_approved_exactly_once_stable_family' if require_all else 'no_cross_slot_duplicate_stable_family',
            'eligible_question_count': len(eligible_ids),
            'eligible_record_count': len(eligible),
            'deduplicated_record_count': max(len(eligible) - len(eligible_ids), 0),
            'assigned_question_count': len(assigned_ids),
            'slot_count': len(plan.get('slots') or []),
            'all_questions_assigned': not missing_ids,
            'no_cross_slot_duplicates': not (duplicate_question_ids or duplicate_component_ids or duplicate_fingerprints or duplicate_family_ids),
            'no_duplicate_anywhere': not (
                duplicate_question_ids or duplicate_component_ids or duplicate_fingerprints or duplicate_family_ids
                or duplicate_record_ids_in_plan or duplicate_inside_slot or duplicate_component_inside_slot
                or duplicate_fingerprint_inside_slot or family_mismatch_question_ids or family_mismatch_slots
                or difficulty_mismatch_question_ids
            ),
            'duplicate_question_ids': duplicate_question_ids[:50],
            'duplicate_component_ids': duplicate_component_ids[:50],
            'duplicate_fingerprint_count': len(duplicate_fingerprints),
            'duplicate_family_ids': duplicate_family_ids[:50],
            'duplicate_record_question_ids_in_plan': sorted(duplicate_record_ids_in_plan)[:50],
            'duplicate_inside_slot_question_ids': sorted(duplicate_inside_slot)[:50],
            'duplicate_inside_slot_component_ids': sorted(duplicate_component_inside_slot)[:50],
            'duplicate_inside_slot_fingerprint_count': len(duplicate_fingerprint_inside_slot),
            'family_mismatch_question_ids': sorted(family_mismatch_question_ids)[:50],
            'family_mismatch_slots': family_mismatch_slots[:50],
            'difficulty_mismatch_question_ids': sorted(difficulty_mismatch_question_ids)[:50],
            'unknown_question_ids': sorted(unknown_ids)[:50],
            'missing_question_ids': missing_ids[:50],
            'empty_slots': empty_slots[:50],
            'mixed_scope_slots': mixed_scope_slots[:50],
            'summary': '; '.join(summary_parts),
        }

    def assert_plan_safe(self, course_id: str, plan: dict[str, Any], *, require_all: bool | None = None) -> dict[str, Any]:
        guard = self.validate_plan(course_id, plan, require_all=require_all)
        if not guard['valid']:
            raise ValueError(f'Hard Duplicate Guard từ chối kế hoạch: {guard["summary"]}')
        return guard

    def selected_question_ids_from_plan(self, plan: dict[str, Any]) -> list[str]:
        ids: list[str] = []
        seen: set[str] = set()
        for slot in plan.get('slots') or []:
            for question_id in slot.get('question_ids') or []:
                question_id = str(question_id)
                if question_id and question_id not in seen:
                    seen.add(question_id)
                    ids.append(question_id)
        return ids
