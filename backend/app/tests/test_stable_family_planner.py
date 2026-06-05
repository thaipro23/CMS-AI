from types import SimpleNamespace

import pytest

from app.services.family_bank_planner import FamilyBankPlanService
from app.services.question_family import (
    build_question_family_id,
    reconcile_question_families,
    stable_family_id_for_question,
)
from app.services.question_identity import build_identity_units, question_content_fingerprint


class FakeQuery:
    def __init__(self, rows):
        self.rows = rows

    def filter(self, *args, **kwargs):
        return self

    def all(self):
        return list(self.rows)

    def count(self):
        return len(self.rows)

    def first(self):
        return self.rows[0] if self.rows else None


class FakeDb:
    def __init__(self, rows):
        self.rows = rows
        self.commits = 0

    def query(self, *args, **kwargs):
        return FakeQuery(self.rows)

    def commit(self):
        self.commits += 1

    def flush(self):
        pass


def question(
    qid: str,
    text: str,
    *,
    difficulty: str = 'easy',
    concept_key: str = 'brand-concept-key',
    concept_title: str = 'Brand',
    concept_id: str | None = None,
    family: str | None = None,
    component: str | None = None,
    chapter: str = 'chapter-1',
    created_at: str | None = None,
):
    return SimpleNamespace(
        id=qid,
        course_id='course-v1:FPT+DOM123+SU26',
        status='approved',
        chapter_node_id=chapter,
        difficulty=difficulty,
        question_text=text,
        option_a='Đáp án đúng',
        option_b='Phương án B',
        option_c='Phương án C',
        option_d='Phương án D',
        correct_answer='A',
        question_hash=None,
        openedx_library_problem_id=component,
        question_family_id=family,
        variant_no=None,
        concept_id=concept_id,
        concept_key=concept_key,
        concept_title=concept_title,
        topic=concept_title,
        learning_objective='',
        source_node_id='node-1',
        source_chunk_id='chunk-1',
        source_node_title='Bài 1',
        target_library_key='lib:FPT:dom123-bai-1',
        quality_score=0.9,
        is_duplicate=False,
        created_at=created_at or qid,
    )


def test_stable_family_id_ignores_model_family_and_variant_suffix():
    base = dict(
        course_id='course-v1:FPT+DOM123+SU26',
        chapter_node_id='chapter-1',
        concept_key='brand-concept-key',
        difficulty='easy',
    )
    left = build_question_family_id(**base)
    right = build_question_family_id(**base)
    assert left == right
    assert left.startswith('fam-') and left.endswith('-easy')
    assert build_question_family_id(**{**base, 'difficulty': 'hard'}) != left


def test_stored_concept_id_is_authoritative_and_title_does_not_merge_distinct_concepts():
    same_concept_left = question(
        'q1', 'Câu A', concept_id='concept-123', concept_key='', concept_title='Tên hiển thị A', family='fam-random-easy-1',
    )
    same_concept_right = question(
        'q2', 'Câu B', concept_id='concept-123', concept_key='', concept_title='Tên hiển thị B', family='cf-other-easy',
    )
    distinct_concept = question(
        'q3', 'Câu C', concept_id='concept-999', concept_key='', concept_title='Tên hiển thị A', family='fam-random-easy-2',
    )
    assert stable_family_id_for_question(same_concept_left) == stable_family_id_for_question(same_concept_right)
    assert stable_family_id_for_question(same_concept_left) != stable_family_id_for_question(distinct_concept)


def test_legacy_variant_suffix_is_reconciled_when_concept_links_are_missing():
    rows = [
        question('q1', 'Câu A', concept_key='', concept_title='', family='fam-0c71e885-easy-1'),
        question('q2', 'Câu B', concept_key='', concept_title='', family='fam-0c71e885-easy-5'),
    ]
    reconcile_question_families(FakeDb(rows), 'course-v1:FPT+DOM123+SU26')  # type: ignore[arg-type]
    assert rows[0].question_family_id == rows[1].question_family_id
    assert [row.variant_no for row in rows] == [1, 2]


def test_reconciliation_is_idempotent_for_backend_owned_family_without_concept_link():
    rows = [
        question('q1', 'Câu A', concept_key='', concept_title='', family='fam-0c71e885-easy-1'),
        question('q2', 'Câu B', concept_key='', concept_title='', family='fam-0c71e885-easy-2'),
    ]
    db = FakeDb(rows)
    reconcile_question_families(db, 'course-v1:FPT+DOM123+SU26')  # type: ignore[arg-type]
    first = [row.question_family_id for row in rows]
    reconcile_question_families(db, 'course-v1:FPT+DOM123+SU26')  # type: ignore[arg-type]
    second = [row.question_family_id for row in rows]
    assert first == second
    assert first[0].startswith('fam-v1-')


def test_reconciliation_merges_legacy_family_ids_and_resequences_variants():
    rows = [
        question('q1', 'Brand là gì?', family='fam-old-easy-1', created_at='1'),
        question('q2', 'Branding là gì?', family='fam-old-easy-2', created_at='2'),
        question('q3', 'Brand Identity là gì?', family='cf-old-easy', created_at='3'),
    ]
    summary = reconcile_question_families(FakeDb(rows), 'course-v1:FPT+DOM123+SU26')  # type: ignore[arg-type]
    assert summary['uses_llm'] is False
    assert summary['family_count_before'] == 3
    assert summary['family_count_after'] == 1
    assert len({row.question_family_id for row in rows}) == 1
    assert [row.variant_no for row in rows] == [1, 2, 3]


def test_identity_fingerprint_prevents_same_visible_question_from_getting_extra_weight():
    rows = [question('q1', 'Logo là gì?'), question('q2', 'Logo là gì!')]
    assert question_content_fingerprint(rows[0]) == question_content_fingerprint(rows[1])  # type: ignore[arg-type]
    units, warnings = build_identity_units(rows)  # type: ignore[arg-type]
    assert len(units) == 1
    assert units[0].question_ids == ['q1']
    assert units[0].duplicate_record_question_ids == ['q2']
    assert warnings


@pytest.mark.asyncio
async def test_planner_uses_existing_concepts_without_llm_and_keeps_family_whole():
    rows = [
        question('q1', 'Brand là gì?', family='fam-random-1'),
        question('q2', 'Branding là gì?', family='fam-random-2'),
        question('q3', 'Logo là gì?', concept_key='logo-key', concept_title='Logo', family='fam-random-3'),
    ]
    plan = await FamilyBankPlanService(FakeDb(rows)).preview_optimized_plan(  # type: ignore[arg-type]
        'course-v1:FPT+DOM123+SU26',
        chapter_node_id='chapter-1',
        total_questions=2,
        difficulty_distribution={'easy': 100, 'medium': 0, 'hard': 0},
        require_all_approved=True,
    )
    assigned = [qid for slot in plan['slots'] for qid in slot['question_ids']]
    brand_family_id = stable_family_id_for_question(rows[0])
    brand_slots = [slot for slot in plan['slots'] if brand_family_id in {family['family_id'] for family in slot['families']}]
    assert plan['uses_llm'] is False
    assert plan['planner_engine'] == 'stable_family_deterministic_v1'
    assert plan['hard_guard']['valid'] is True
    assert len(assigned) == len(set(assigned)) == 3
    assert len(brand_slots) == 1
    assert set(brand_slots[0]['question_ids']) == {'q1', 'q2'}


@pytest.mark.asyncio
async def test_requested_slots_are_reduced_instead_of_splitting_or_repeating_family():
    rows = [
        question('q1', 'Brand là gì?'),
        question('q2', 'Branding là gì?'),
        question('q3', 'Brand Identity là gì?'),
    ]
    plan = await FamilyBankPlanService(FakeDb(rows)).preview_optimized_plan(  # type: ignore[arg-type]
        'course-v1:FPT+DOM123+SU26',
        chapter_node_id='chapter-1',
        total_questions=5,
        difficulty_distribution={'easy': 100, 'medium': 0, 'hard': 0},
        require_all_approved=True,
    )
    assert len(plan['slots']) == 1
    assert plan['slots'][0]['variant_count'] == 3
    assert plan['hard_guard']['duplicate_family_ids'] == []
    assert any('giảm còn 1 slot' in warning for warning in plan['warnings'])


@pytest.mark.asyncio
async def test_more_families_than_slots_are_bin_packed_and_all_questions_used_once():
    rows = [
        question(f'q{i}', f'Câu hỏi {i}', concept_key=f'concept-{i}', concept_title=f'Concept {i}')
        for i in range(1, 7)
    ]
    plan = await FamilyBankPlanService(FakeDb(rows)).preview_optimized_plan(  # type: ignore[arg-type]
        'course-v1:FPT+DOM123+SU26',
        chapter_node_id='chapter-1',
        total_questions=3,
        difficulty_distribution={'easy': 100, 'medium': 0, 'hard': 0},
        require_all_approved=True,
    )
    assigned = [qid for slot in plan['slots'] for qid in slot['question_ids']]
    families = [family['family_id'] for slot in plan['slots'] for family in slot['families']]
    assert len(plan['slots']) == 3
    assert len(assigned) == len(set(assigned)) == 6
    assert len(families) == len(set(families)) == 6
    assert plan['hard_guard']['valid'] is True


def test_hard_guard_rejects_same_stable_family_split_across_slots():
    rows = [question('q1', 'Brand là gì?'), question('q2', 'Branding là gì?')]
    reconcile_question_families(FakeDb(rows), 'course-v1:FPT+DOM123+SU26')  # type: ignore[arg-type]
    family_id = rows[0].question_family_id
    plan = {
        'chapter_node_id': 'chapter-1',
        'slots': [
            {'slot_no': 1, 'families': [{'family_id': family_id}], 'question_ids': ['q1']},
            {'slot_no': 2, 'families': [{'family_id': family_id}], 'question_ids': ['q2']},
        ],
    }
    guard = FamilyBankPlanService(FakeDb(rows)).validate_plan(  # type: ignore[arg-type]
        'course-v1:FPT+DOM123+SU26', plan, require_all=True,
    )
    assert guard['valid'] is False
    assert guard['duplicate_family_ids'] == [family_id]
