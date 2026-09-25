from __future__ import annotations

from pathlib import Path

from app.services.learning_analytics.session_deadline_mapper import (
    build_session_mappings_from_blocks,
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
