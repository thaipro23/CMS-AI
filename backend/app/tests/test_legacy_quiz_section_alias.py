from __future__ import annotations

from types import SimpleNamespace

from app.services.question_bank.helpers import extract_chapter_number
from app.services.question_bank.quiz_creation import QuestionBankQuizCreationWorkflowService


def test_extract_chapter_number_accepts_legacy_q_and_quiz_titles() -> None:
    assert extract_chapter_number('Q1') == '1'
    assert extract_chapter_number('Q2') == '2'
    assert extract_chapter_number('Quiz 01') == '1'
    assert extract_chapter_number('Quiz 02') == '2'
    assert extract_chapter_number('Bài 1') == '1'
    assert extract_chapter_number('Bài 2.1') == '2.1'


def test_legacy_q1_maps_to_openedx_bai_1_section() -> None:
    parent = SimpleNamespace(db=None)
    parent._chapter_display_name = lambda chapter: chapter.title
    service = QuestionBankQuizCreationWorkflowService(parent)

    chapter = SimpleNamespace(title='Q1')
    section = {
        'block_id': 'block-v1:FPT+DEMO+SU26+type@chapter+block@chapter-1',
        'display_name': 'Bài 1',
    }

    matched, score, reason = service._match_chapter_to_section(chapter, [section], set())

    assert matched == section
    assert score >= 0.86
    assert reason == 'Trùng số bài 1'


def test_legacy_q2_maps_to_openedx_bai_2_section_without_republishing_release() -> None:
    parent = SimpleNamespace(db=None)
    parent._chapter_display_name = lambda chapter: chapter.title
    service = QuestionBankQuizCreationWorkflowService(parent)

    chapter = SimpleNamespace(title='Q2')
    sections = [
        {'block_id': 'section-1', 'display_name': 'Bài 1'},
        {'block_id': 'section-2', 'display_name': 'Bài 2'},
    ]

    matched, score, reason = service._match_chapter_to_section(chapter, sections, set())

    assert matched == sections[1]
    assert score >= 0.86
    assert reason == 'Trùng số bài 2'
