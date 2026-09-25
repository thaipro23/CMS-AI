from __future__ import annotations

from pathlib import Path
from datetime import datetime
from types import SimpleNamespace

from app.services.learning_analytics.session_deadline_mapper import (
    build_session_mappings_from_blocks,
)
from app.services.learning_analytics.analytics_core_service import (
    LearningAnalyticsCoreService,
)


ROOT = Path(__file__).resolve().parents[3]


def test_flat_openedx_tree_uses_chapter_as_session_and_hydrates_descendants():
    course_id = "course-v1:FPL+BUS1052+FA26"
    chapter = f"{course_id}+type@chapter+block@bai-1"
    seq_part_1 = f"{course_id}+type@sequential+block@phan-1"
    seq_part_2 = f"{course_id}+type@sequential+block@phan-2"
    seq_quiz = f"{course_id}+type@sequential+block@quiz-1"
    unit_1 = f"{course_id}+type@vertical+block@unit-1"
    unit_2 = f"{course_id}+type@vertical+block@unit-2"
    unit_quiz = f"{course_id}+type@vertical+block@unit-quiz"
    video_1 = f"{course_id}+type@video+block@video-1"
    video_2 = f"{course_id}+type@video+block@video-2"
    problem = f"{course_id}+type@problem+block@problem-1"

    blocks = [
        {"block_id": chapter, "type": "chapter", "display_name": "Bài 1", "children": [seq_part_1, seq_part_2, seq_quiz]},
        {"block_id": seq_part_1, "type": "sequential", "display_name": "Phần 1", "parent_block_id": chapter, "children": [unit_1]},
        {"block_id": seq_part_2, "type": "sequential", "display_name": "Phần 2", "parent_block_id": chapter, "children": [unit_2]},
        {"block_id": seq_quiz, "type": "sequential", "display_name": "Quiz 01", "parent_block_id": chapter, "children": [unit_quiz]},
        {"block_id": unit_1, "type": "vertical", "display_name": "Unit 1", "parent_block_id": seq_part_1, "children": [video_1]},
        {"block_id": unit_2, "type": "vertical", "display_name": "Unit 2", "parent_block_id": seq_part_2, "children": [video_2]},
        {"block_id": unit_quiz, "type": "vertical", "display_name": "Quiz Unit", "parent_block_id": seq_quiz, "children": [problem]},
        {"block_id": video_1, "type": "video", "display_name": "Video 1", "parent_block_id": unit_1, "children": []},
        {"block_id": video_2, "type": "video", "display_name": "Video 2", "parent_block_id": unit_2, "children": []},
        {"block_id": problem, "type": "problem", "display_name": "Quiz 1", "parent_block_id": unit_quiz, "children": []},
    ]

    sessions = build_session_mappings_from_blocks(course_id, blocks)

    assert len(sessions) == 1
    session = sessions[0]
    assert session.session_key == chapter
    assert [item.block_type for item in session.components] == ["video", "video", "problem"]
    assert [item.usage_key for item in session.videos] == [video_1, video_2]
    assert session.quiz is not None
    assert session.quiz.usage_key == problem
    assert set(session.match_keys) == {
        seq_part_1,
        seq_part_2,
        seq_quiz,
        unit_1,
        unit_2,
        unit_quiz,
        video_1,
        video_2,
        problem,
    }


def test_parent_links_work_when_children_array_is_missing():
    course_id = "course-v1:FPL+BUS1052+FA26"
    chapter = f"{course_id}+type@chapter+block@bai-2"
    seq = f"{course_id}+type@sequential+block@phan-1"
    vertical = f"{course_id}+type@vertical+block@unit-2"
    video = f"{course_id}+type@video+block@video-2"

    sessions = build_session_mappings_from_blocks(
        course_id,
        [
            {"block_id": chapter, "type": "chapter", "display_name": "Bài 2", "children": []},
            {"block_id": seq, "type": "sequential", "display_name": "Phần 1", "parent_block_id": chapter, "children": []},
            {"block_id": vertical, "type": "vertical", "display_name": "Unit 2", "parent_block_id": seq, "children": []},
            {"block_id": video, "type": "video", "display_name": "Video 2", "parent_block_id": vertical, "children": []},
        ],
    )

    assert len(sessions) == 1
    assert sessions[0].session_key == chapter
    assert [item.usage_key for item in sessions[0].videos] == [video]


def test_problem_bank_library_content_is_a_quiz_component():
    course_id = "course-v1:FPL+BUS1052+FA26"
    seq = f"{course_id}+type@sequential+block@quiz-1"
    unit = f"{course_id}+type@vertical+block@quiz-unit-1"
    bank = f"{course_id}+type@library_content+block@problem-bank-1"

    sessions = build_session_mappings_from_blocks(
        course_id,
        [
            {
                "block_id": seq,
                "type": "sequential",
                "display_name": "Bài 1 - Quiz",
                "children": [unit],
            },
            {
                "block_id": unit,
                "type": "vertical",
                "display_name": "Quiz Unit",
                "parent_block_id": seq,
                "children": [bank],
            },
            {
                "block_id": bank,
                "type": "library_content",
                "display_name": "Problem Bank",
                "parent_block_id": unit,
                "children": [],
            },
        ],
    )

    assert len(sessions) == 1
    assert sessions[0].quiz is not None
    assert sessions[0].quiz.block_type == "library_content"
    assert sessions[0].quiz.usage_key == bank


def test_chapter_prevents_sequentials_becoming_duplicate_sessions():
    course_id = "course-v1:FPL+BUS1052+FA26"
    chapter = f"{course_id}+type@chapter+block@bai-1"
    seq_1 = f"{course_id}+type@sequential+block@phan-1"
    seq_2 = f"{course_id}+type@sequential+block@phan-2"
    seq_quiz = f"{course_id}+type@sequential+block@quiz-1"

    sessions = build_session_mappings_from_blocks(
        course_id,
        [
            {"block_id": chapter, "type": "chapter", "display_name": "Bài 1", "children": [seq_1, seq_2, seq_quiz]},
            {"block_id": seq_1, "type": "sequential", "display_name": "Phần 1", "parent_block_id": chapter, "children": []},
            {"block_id": seq_2, "type": "sequential", "display_name": "Phần 2", "parent_block_id": chapter, "children": []},
            {"block_id": seq_quiz, "type": "sequential", "display_name": "Quiz 01", "parent_block_id": chapter, "children": []},
        ],
    )

    assert len(sessions) == 1
    assert sessions[0].session_key == chapter


def test_worker_rebuilds_session_structure_before_video_recalculate():
    source = (ROOT / "backend" / "app" / "worker.py").read_text(encoding="utf-8")

    ensure_pos = source.index("service.ensure_session_structure_from_openedx(")
    video_pos = source.index("service.recalculate_course_video_progress(")
    session_pos = source.index("service.recalculate_student_session_progress(")

    assert ensure_pos < video_pos < session_pos
    assert "SESSION_STRUCTURE_FETCH_FAILED" in source
    assert "SESSION_STRUCTURE_NO_BLOCKS" in source
    assert "SESSION_STRUCTURE_NO_SESSIONS" in source


def _analytics_service_without_db() -> LearningAnalyticsCoreService:
    return object.__new__(LearningAnalyticsCoreService)


def _attempt(
    *,
    attempt_id: str,
    sequence: str | None,
    unit: str | None,
    assigned: list[str] | None = None,
    submission_count: int = 0,
):
    return SimpleNamespace(
        id=attempt_id,
        sequence_usage_key=sequence,
        unit_usage_key=unit,
        assigned_problem_usage_keys_json=assigned or [],
        submission_count=submission_count,
        score_earned=None,
        score_possible=None,
        last_submission_at=None,
        first_submission_at=None,
        ended_at=None,
        started_at=datetime(2026, 9, 25, 3, 0, 0),
    )


def test_quiz_session_resolution_prefers_unit_over_stale_sequence():
    service = _analytics_service_without_db()

    seq_bai_1 = "block-v1:FPL+BUS1052+FA26+type@sequential+block@quiz-01"
    unit_bai_2 = "block-v1:FPL+BUS1052+FA26+type@vertical+block@quiz-unit-02"

    sessions = [
        {
            "session_index": 1,
            "session_key": "block-v1:FPL+BUS1052+FA26+type@chapter+block@bai-1",
            "quiz_usage_key": None,
            "components": [],
            "match_keys": [seq_bai_1],
        },
        {
            "session_index": 2,
            "session_key": "block-v1:FPL+BUS1052+FA26+type@chapter+block@bai-2",
            "quiz_usage_key": None,
            "components": [],
            "match_keys": [unit_bai_2],
        },
    ]

    attempt = _attempt(
        attempt_id="ambiguous-start-only",
        sequence=seq_bai_1,
        unit=unit_bai_2,
    )

    resolved, diagnostics = service._resolve_quiz_attempts_by_session(
        attempts=[attempt],
        sessions=sessions,
    )

    assert set(resolved) == {2}
    assert resolved[2].id == "ambiguous-start-only"
    assert diagnostics["ambiguous_attempt_count"] == 0
    assert diagnostics["unmatched_attempt_count"] == 0


def test_quiz_session_resolution_prefers_assigned_problem_over_unit():
    service = _analytics_service_without_db()

    unit_bai_1 = "block-v1:FPL+BUS1052+FA26+type@vertical+block@unit-1"
    problem_bai_2 = "block-v1:FPL+BUS1052+FA26+type@problem+block@problem-2"

    sessions = [
        {
            "session_index": 1,
            "session_key": "block-v1:FPL+BUS1052+FA26+type@chapter+block@bai-1",
            "quiz_usage_key": None,
            "components": [],
            "match_keys": [unit_bai_1],
        },
        {
            "session_index": 2,
            "session_key": "block-v1:FPL+BUS1052+FA26+type@chapter+block@bai-2",
            "quiz_usage_key": problem_bai_2,
            "components": [],
            "match_keys": [problem_bai_2],
        },
    ]

    attempt = _attempt(
        attempt_id="problem-wins",
        sequence=None,
        unit=unit_bai_1,
        assigned=[problem_bai_2],
        submission_count=1,
    )

    resolved, _ = service._resolve_quiz_attempts_by_session(
        attempts=[attempt],
        sessions=sessions,
    )

    assert set(resolved) == {2}


def test_video_session_match_accepts_materialized_bare_video_hash():
    service = _analytics_service_without_db()

    video_hash = "489882c136534cd28d2a51731569f5f3"
    full_key = (
        "block-v1:FPL+BUS1052+FA26+type@video+block@"
        + video_hash
    )
    expected = {
        "session": {"session_index": 4},
        "component": {"usage_key": full_key},
    }

    result = service._match_video_session(
        video_id=video_hash,
        video_code="vYBJEpXbOYg",
        lookup={full_key: expected},
    )

    assert result == expected
