from pathlib import Path

from app.services.answer_randomizer import normalize_and_shuffle_options
from app.services.pedagogy import remap_pedagogy_after_shuffle
from app.services.prompt_builder import QUESTION_POLICY


def test_pedagogy_misconceptions_follow_backend_answer_shuffle():
    item = {
        'question': 'HTTP method nào dùng trong tình huống thử nghiệm?',
        'difficulty': 'easy',
        'source_node_id': 'unit-1',
        'options': {'A': 'alpha', 'B': 'beta', 'C': 'gamma', 'D': 'delta'},
        'correct_answer': 'A',
        'pedagogy': {
            'hint': 'Một quy tắc nền giúp suy luận nhưng không nói đáp án.',
            'misconceptions': {'A': '', 'B': 'reason-B', 'C': 'reason-C', 'D': 'reason-D'},
        },
    }
    randomized = normalize_and_shuffle_options(item, index=2, force_shuffle=True)
    remapped = remap_pedagogy_after_shuffle(
        item['pedagogy'], randomized.source_label_by_new_label, randomized.correct_answer
    )
    assert remapped['hint'] == item['pedagogy']['hint']
    for new_label, old_label in randomized.source_label_by_new_label.items():
        expected = '' if new_label == randomized.correct_answer else item['pedagogy']['misconceptions'][old_label]
        assert remapped['misconceptions'][new_label] == expected


def test_structured_output_contract_removes_redundant_model_fields_and_adds_compact_pedagogy():
    source = (Path(__file__).parents[1] / 'services' / 'model_gateway.py').read_text()
    schema_block = source[source.index('def _question_json_schema'):source.index('def _system_instruction')]
    assert "'pedagogy': pedagogy" in schema_block
    for removed in [
        "'question_family_id'", "'variant_no'", "'concept_key'", "'question_type'",
        "'source_ref'", "'source_type'", "'source_page'", "'source_timestamp_start'",
        "'source_timestamp_end'", "'source_node_id'", "'source_excerpt'", "'tags'", "'ai_rationale'"
    ]:
        assert removed not in schema_block


def test_prompt_explicitly_bounds_pedagogy_output_and_prevents_answer_leak():
    assert 'pedagogy.hint: CHỈ 1 câu ngắn' in QUESTION_POLICY
    assert 'ưu tiên 12-22 từ' in QUESTION_POLICY
    assert 'giọng gần gũi, tự nhiên với sinh viên' in QUESTION_POLICY
    assert 'không tiếng lóng/suồng sã' in QUESTION_POLICY
    assert 'không paraphrase trực tiếp đáp án đúng' in QUESTION_POLICY
    assert 'source_evidence ưu tiên <= 24 từ và chỉ dùng để kiểm chứng nguồn' in QUESTION_POLICY
    assert 'pedagogy.clue' not in QUESTION_POLICY
    assert 'pedagogy.example' not in QUESTION_POLICY
    assert 'mỗi phương án sai là một cụm rất ngắn' in QUESTION_POLICY
    assert 'không viết hướng dẫn làm bài' in QUESTION_POLICY.lower()
    assert 'Backend tự lấy source_ref/type/page/timestamp/node từ chunk' in QUESTION_POLICY
