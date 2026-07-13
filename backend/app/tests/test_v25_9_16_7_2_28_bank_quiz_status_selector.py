from pathlib import Path


def _root() -> Path:
    return Path(__file__).resolve().parents[3]


def test_bank_quiz_table_uses_status_column_for_creation_choice():
    page = (_root() / 'frontend' / 'app' / 'bank' / 'quiz' / 'page.tsx').read_text(encoding='utf-8')

    assert '<th>Tạo gì</th>' not in page
    assert '<th>Trạng thái</th>' in page
    assert 'aria-label={`Chọn trạng thái ${item.chapter_title}`}' in page
    assert '<option value="quiz">Tạo Quiz</option>' in page
    assert '<option value="final_test">Tạo Final test</option>' in page
    assert '<option value="skip">Không tạo</option>' in page
    assert '<option value="assignment">' not in page
    assert 'Không tạo quiz' not in page
    assert 'Assignment/nội dung' not in page


def test_bank_quiz_default_final_test_and_assignment_statuses_are_clear():
    page = (_root() / 'frontend' / 'app' / 'bank' / 'quiz' / 'page.tsx').read_text(encoding='utf-8')
    service = ((_root() / 'backend' / 'app' / 'services' / 'question_bank_service.py').read_text(encoding='utf-8') + (_root() / 'backend' / 'app' / 'services' / 'question_bank' / 'quiz_creation.py').read_text(encoding='utf-8'))

    assert "if (title.includes('final')) return 'final_test'" in page
    assert "if (title.includes('assignment') || title.includes('asm')) return 'skip'" in page
    assert "'assignment': 'Không tạo'" in service
    assert "'skip': 'Không tạo'" in service
    assert 'đổi trạng thái dòng sang Không tạo' in service
