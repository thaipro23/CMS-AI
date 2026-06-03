from app.services.quality_checker import QualityChecker


def test_anti_trick_rejects_double_negative():
    q = {
        'question': 'Đâu không phải là không đúng về REST API?',
        'options': {'A': 'A', 'B': 'B', 'C': 'C', 'D': 'D'},
        'correct_answer': 'A', 'source_ref': 'slide:1', 'explanation': 'test'
    }
    result = QualityChecker().check(q)
    assert result.passed is False
    assert 'anti-trick' in result.reason
