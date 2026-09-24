from types import SimpleNamespace

from app.services.academic.assessment_components import (
    canonical_assessment_components,
    canonical_assessment_identity,
)
from app.services.academic_service import AcademicService


def test_structural_demo_and_part_rows_never_become_assessment_columns():
    rows = [
        {"key": "quiz-real", "name": "Quiz 1", "quiz_number": 1, "percent": 80},
        {
            "key": "demo-a",
            "name": "Demo",
            "category": "quiz",
            "quiz_number": 2,
            "planned": True,
            "percent": None,
        },
        {"key": "demo-b", "name": "Demo", "category": "subsection", "percent": 90},
        {"key": "demo-lesson-1", "name": "Demo bài 1", "percent": 100},
        {"key": "part-1-a", "name": "Phần 1", "percent": 100},
        {"key": "part-1-b", "name": "Phần 1", "percent": 80},
        {
            "key": "final-a",
            "name": "Final test",
            "assessment_type": "final_test",
            "percent": 70,
        },
    ]

    result = canonical_assessment_components(rows)

    assert [(row["key"], row["name"]) for row in result] == [
        ("quiz:1", "Quiz 1"),
        ("final_test", "Final test"),
    ]


def test_quiz_duplicates_collapse_by_number_and_prefer_real_score():
    rows = [
        {
            "key": "outline-q2",
            "name": "Quiz 2",
            "quiz_number": 2,
            "planned": True,
            "percent": None,
            "deadline_date": "2026-10-10",
        },
        {
            "key": "grade-q2",
            "name": "Learning Check 2",
            "quiz_number": 2,
            "planned": False,
            "percent": 95,
        },
    ]

    result = canonical_assessment_components(rows)

    assert len(result) == 1
    assert result[0]["key"] == "quiz:2"
    assert result[0]["name"] == "Quiz 2"
    assert result[0]["percent"] == 95
    assert result[0]["planned"] is False
    assert result[0]["deadline_date"] == "2026-10-10"


def test_storage_key_number_does_not_create_phantom_quiz():
    rows = [
        {
            "key": "block@quiz-14-random",
            "name": "Demo",
            "category": "problem",
            "percent": 100,
        },
    ]

    assert canonical_assessment_components(rows) == []


def test_position_derived_quiz_number_on_demo_is_not_trusted():
    rows = [
        {
            "key": "demo-outline",
            "name": "Demo",
            "category": "quiz",
            "quiz_number": 7,
            "planned": True,
        },
    ]

    assert canonical_assessment_components(rows) == []


def test_explicit_assessment_type_can_use_positive_quiz_number():
    row = {
        "key": "opaque",
        "name": "Checkpoint",
        "assessment_type": "quiz",
        "quiz_number": 3,
    }

    assert canonical_assessment_identity(row) == "quiz:3"


def test_empty_or_non_assessment_rows_are_valid():
    assert canonical_assessment_components([]) == []
    assert canonical_assessment_components([{"name": "Assignment", "percent": 100}]) == []


def _service() -> AcademicService:
    service = AcademicService.__new__(AcademicService)
    service.db = None
    return service


def test_normalizer_preserves_explicit_assessment_contract():
    result = _service()._normalize_component_score_item({
        "key": "opaque",
        "name": "Checkpoint",
        "assessment_type": "quiz",
        "quiz_number": 4,
        "percent": 75,
    })

    assert result is not None
    assert result["assessment_type"] == "quiz"
    assert result["quiz_number"] == 4


def test_teacher_summary_filters_structural_rows(monkeypatch):
    service = _service()
    monkeypatch.setattr(
        service,
        "_component_scores_from_snapshot",
        lambda _snapshot: [
            {"key": "demo", "name": "Demo", "category": "quiz", "quiz_number": 1, "percent": 100},
            {"key": "part", "name": "Phần 1", "percent": 80},
            {"key": "q2", "name": "Quiz 2", "percent": 90},
            {"key": "final", "name": "Final test", "percent": 70},
        ],
    )

    result = service._component_summary_from_snapshots([object()])

    assert [(row["key"], row["name"]) for row in result] == [
        ("quiz:2", "Quiz 2"),
        ("final_test", "Final test"),
    ]


def test_student_policy_receives_raw_components_but_response_is_canonical(monkeypatch):
    service = _service()
    raw = [
        {"key": "demo", "name": "Demo", "category": "quiz", "quiz_number": 1, "percent": 100},
        {"key": "q2", "name": "Quiz 2", "percent": 90},
    ]
    monkeypatch.setattr(service, "_component_scores_from_snapshot", lambda _snapshot: raw)
    monkeypatch.setattr(
        service,
        "_enrich_component_scores_for_class",
        lambda items, _cls, _schedule=None: list(items),
    )

    captured: dict[str, object] = {}

    class Policy:
        def evaluate_student(self, **kwargs):
            captured["components"] = kwargs["components"]
            return {
                "exam_eligible": False,
                "exam_status": "not_eligible",
                "exam_status_label": "Chưa đủ điều kiện",
                "exam_reasons": [],
                "assignment_status": None,
                "assignment_score_10": None,
            }

    student = SimpleNamespace(
        id="student-1",
        student_code="PH1",
        username="ph1",
        email="ph1@example.edu.vn",
        full_name="Student One",
        phone=None,
        metadata_json=None,
        campus="hn",
        branch="poly",
        active=True,
    )
    result = service._student_mapping_item(
        "class-1",
        student,
        None,
        None,
        cls=SimpleNamespace(id="class-1"),
        block=SimpleNamespace(),
        policy_service=Policy(),
        assignment_scores={},
        deadline_overrides={},
    )

    assert captured["components"] == raw
    assert [(row["key"], row["name"]) for row in result["learning_component_scores"]] == [
        ("quiz:2", "Quiz 2"),
    ]
