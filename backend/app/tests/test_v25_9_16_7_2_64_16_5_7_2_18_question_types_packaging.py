from __future__ import annotations

import ast
import json
import sys
import types
from pathlib import Path

import pytest

try:
    import openai  # type: ignore  # noqa: F401
except ModuleNotFoundError:
    module = types.ModuleType('openai')
    class _AsyncOpenAI:  # pragma: no cover - dependency shim for schema-only tests
        def __init__(self, *args, **kwargs):
            pass
    module.AsyncOpenAI = _AsyncOpenAI
    sys.modules['openai'] = module

from app.core.errors import public_http_exception
from app.services.model_gateway import ModelGateway
from app.services.problem_parser import parse_problem_xml
from app.services.prompt_builder import build_question_prompt
from app.services.question_bank.import_export import preview_openedx_problem_import
from app.services.question_content import normalize_question_content
from app.services.question_type_quota import (
    allocate_column_counts_to_rows,
    exact_type_counts,
    feasible_type_difficulty_matrix,
    feasible_type_difficulty_matrix_with_flexible,
    proportional_counts,
)

ROOT = Path(__file__).resolve().parents[3]
VERSION = '25.9.16.7.2.64.16.5.7.2.18'
HEAD = '0061_v25_9_16_7_2_64_39'


def read(rel: str) -> str:
    return (ROOT / rel).read_text(encoding='utf-8')


def test_release_version_and_migration_head_contract_are_synchronized() -> None:
    assert read('VERSION').strip() == VERSION
    for rel in (
        'backend/app/core/config.py', 'frontend/package.json', 'frontend/package-lock.json',
        'frontend/Dockerfile', 'docker-compose.prod.yml', '.env.example', '.env.production.example',
        'Jenkinsfile', 'deploy/k8s/base/kustomization.yaml', 'deploy/k8s/jobs/kustomization.yaml',
        'scripts/uat-build-gate.sh', 'scripts/claude-code-review-pack.sh',
    ):
        assert VERSION in read(rel), rel
    assert f"_EXPECTED_ALEMBIC_REVISION = '{HEAD}'" in read('backend/app/api/routes/health.py')
    assert f"EXPECTED_ALEMBIC_HEAD='{HEAD}'" in read('scripts/uat-build-gate.sh')
    assert f"EXPECTED_ALEMBIC_HEAD='{HEAD}'" in read('scripts/claude-code-review-pack.sh')

    migration_60 = read('backend/alembic/versions/0060_v25_9_16_7_2_64_38_question_authoring_types_media.py')
    migration_61 = read('backend/alembic/versions/0061_v25_9_16_7_2_64_39_quiz_blueprint_type_quota.py')
    assert "revision = '0060_v25_9_16_7_2_64_38'" in migration_60
    assert "down_revision = '0059_v25_9_16_7_2_64_37'" in migration_60
    assert f"revision = '{HEAD}'" in migration_61
    assert "down_revision = '0060_v25_9_16_7_2_64_38'" in migration_61


def test_generation_type_mix_rounding_and_bucket_allocation_are_exact() -> None:
    counts = proportional_counts(
        total=17,
        weights={'single_select': 70, 'multi_select': 30},
        allowed_types=('single_select', 'multi_select'),
    )
    assert counts == {'single_select': 12, 'multi_select': 5}
    rows = allocate_column_counts_to_rows([5, 3, 9], counts)
    assert [sum(row.values()) for row in rows] == [5, 3, 9]
    assert sum(row['single_select'] for row in rows) == 12
    assert sum(row['multi_select'] for row in rows) == 5


def test_quiz_exact_type_quota_and_feasible_matrix() -> None:
    type_counts = exact_type_counts(
        total=10, single_select_count=4, multi_select_count=3,
        text_input_count=2, numerical_input_count=1,
    )
    assert sum(type_counts.values()) == 10
    difficulty = {'easy': 5, 'medium': 3, 'hard': 2}
    availability = {
        ('easy', 'single_select'): 3, ('easy', 'multi_select'): 2,
        ('easy', 'text_input'): 2, ('easy', 'numerical_input'): 1,
        ('medium', 'single_select'): 3, ('medium', 'multi_select'): 2,
        ('medium', 'text_input'): 1, ('medium', 'numerical_input'): 1,
        ('hard', 'single_select'): 2, ('hard', 'multi_select'): 2,
        ('hard', 'text_input'): 1, ('hard', 'numerical_input'): 1,
    }
    matrix = feasible_type_difficulty_matrix(
        difficulty_targets=difficulty, type_targets=type_counts, availability=availability,
    )
    assert sum(matrix.values()) == 10
    for diff, target in difficulty.items():
        assert sum(value for (row_diff, _), value in matrix.items() if row_diff == diff) == target
    for qtype, target in type_counts.items():
        assert sum(value for (_, row_type), value in matrix.items() if row_type == qtype) == target
    for key, value in matrix.items():
        assert value <= availability[key]


def test_quiz_type_quota_fails_closed_when_matrix_is_impossible() -> None:
    with pytest.raises(ValueError, match='không đủ tổ hợp'):
        feasible_type_difficulty_matrix(
            difficulty_targets={'easy': 2, 'medium': 0, 'hard': 0},
            type_targets={'single_select': 0, 'multi_select': 2},
            availability={('easy', 'single_select'): 2, ('easy', 'multi_select'): 0},
        )


def test_quiz_matrix_uses_each_unclassified_legacy_question_only_once() -> None:
    matrix, flexible = feasible_type_difficulty_matrix_with_flexible(
        difficulty_targets={'easy': 1, 'medium': 1, 'hard': 1},
        type_targets={'single_select': 3},
        availability={
            ('easy', 'single_select'): 1,
            ('medium', 'single_select'): 0,
            ('hard', 'single_select'): 0,
        },
        flexible_availability={'single_select': 2},
    )
    assert matrix == {
        ('easy', 'single_select'): 1,
        ('medium', 'single_select'): 1,
        ('hard', 'single_select'): 1,
    }
    assert sum(flexible.values()) == 2
    assert flexible[('easy', 'single_select')] == 0


def test_canonical_question_content_validates_all_four_response_types() -> None:
    single = normalize_question_content('single_select', {'response': {'type': 'single_select', 'options': [
        {'id': 'a', 'text': 'A', 'correct': True}, {'id': 'b', 'text': 'B', 'correct': False},
    ]}})
    multi = normalize_question_content('multi_select', {'response': {'type': 'multi_select', 'options': [
        {'id': 'a', 'text': 'A', 'correct': True}, {'id': 'b', 'text': 'B', 'correct': True}, {'id': 'c', 'text': 'C', 'correct': False},
    ]}})
    text = normalize_question_content('text_input', {'response': {'type': 'text_input', 'accepted_answers': [
        {'text': 'HTTP', 'case_sensitive': False}, {'text': 'http', 'case_sensitive': False},
    ]}})
    numerical = normalize_question_content('numerical_input', {'response': {
        'type': 'numerical_input', 'answer': '3.14', 'tolerance': '1', 'tolerance_type': 'percent',
    }})
    assert single['response']['type'] == 'single_select'
    assert sum(1 for item in multi['response']['options'] if item['correct']) == 2
    assert text['response']['accepted_answers'][0]['text'] == 'HTTP'
    assert numerical['response']['tolerance_type'] == 'percent'

    with pytest.raises(ValueError):
        normalize_question_content('multi_select', {'response': {'type': 'multi_select', 'options': [
            {'id': 'a', 'text': 'A', 'correct': True}, {'id': 'b', 'text': 'B', 'correct': False},
        ]}})


def test_openedx_parser_preserves_response_types_and_grading_semantics() -> None:
    olx = '''<problem>
      <multiplechoiceresponse><label>Q1</label><choicegroup>
        <choice correct="true">A</choice><choice correct="false">B</choice>
      </choicegroup></multiplechoiceresponse>
      <choiceresponse><label>Q2</label><checkboxgroup>
        <choice correct="true">A</choice><choice correct="true">B</choice><choice correct="false">C</choice>
      </checkboxgroup></choiceresponse>
      <stringresponse answer="hello" type="cs"><label>Q3</label><additional_answer answer="hi"/><textline/></stringresponse>
      <numericalresponse answer="3.14"><label>Q4</label><responseparam type="tolerance" default="1%"/><formulaequationinput/></numericalresponse>
    </problem>'''
    rows = parse_problem_xml(olx)
    assert [row.question_type for row in rows] == ['single_select', 'multi_select', 'text_input', 'numerical_input']
    assert [choice.correct for choice in rows[1].choices] == [True, True, False]
    assert rows[2].accepted_answers == ['hello', 'hi']
    assert rows[2].case_sensitive is True
    assert rows[3].numerical_answer == '3.14'
    assert rows[3].numerical_tolerance == '1'
    assert rows[3].numerical_tolerance_type == 'percent'


def test_openedx_import_rejects_unsupported_string_grading_instead_of_changing_semantics() -> None:
    preview = preview_openedx_problem_import(
        '<problem><stringresponse answer="^abc$" type="regexp"><label>Regex</label><textline/></stringresponse></problem>'
    )
    assert preview['ok'] is False
    assert preview['valid_count'] == 0
    assert preview['invalid_count'] == 1
    assert 'regexp' in preview['errors'][0]['error']


def test_model_gateway_structured_schema_distinguishes_single_and_multi_select() -> None:
    gateway = ModelGateway()
    single = gateway._question_json_schema('single_select')
    multi = gateway._question_json_schema('multi_select')
    single_item = single['properties']['questions']['items']
    multi_item = multi['properties']['questions']['items']
    assert 'correct_answer' in single_item['properties']
    assert 'correct_answers' not in single_item['properties']
    assert 'correct_answers' in multi_item['properties']
    assert multi_item['properties']['correct_answers']['minItems'] == 2
    assert multi_item['properties']['correct_answers']['maxItems'] == 3
    assert multi_item['properties']['correct_answers']['uniqueItems'] is True

    multi_prompt = build_question_prompt('HTTP và HTTPS', 3, target_question_type='multi_select')
    assert 'correct_answers' in multi_prompt
    assert '2 đến 3 đáp án đúng' in multi_prompt


def test_public_error_mapper_keeps_domain_errors_and_sanitizes_unexpected_failures() -> None:
    try:
        raise ValueError('Quota loại câu hỏi không hợp lệ.')
    except ValueError:
        exc = public_http_exception(status_code=400, code='QUIZ_FAILED', message='Không thể tạo Quiz')
    assert exc.status_code == 400
    assert exc.detail['message'] == 'Quota loại câu hỏi không hợp lệ.'

    try:
        raise RuntimeError('secret upstream traceback should not leak')
    except RuntimeError:
        exc = public_http_exception(status_code=400, code='QUIZ_FAILED', message='Không thể tạo Quiz')
    assert exc.status_code == 500
    assert 'secret upstream' not in json.dumps(exc.detail)


def test_frontend_workflows_expose_authoring_import_and_type_quota() -> None:
    chapter = read('frontend/app/bank/_components/pages/ChapterWorkspacePage.tsx')
    quiz = read('frontend/app/bank/quiz/page.tsx')
    api = read('frontend/lib/api.ts')
    assert 'QuestionAuthoringEditor' in chapter
    assert '+ Thêm câu hỏi' in chapter
    assert 'Import Open edX' in chapter
    assert 'question_type_single_select' in chapter and 'question_type_multi_select' in chapter
    assert 'BankOpenEdxImportModal' in chapter
    for marker in ('singleSelectCount', 'multiSelectCount', 'textInputCount', 'numericalInputCount'):
        assert marker in quiz
    assert 'Kiểm tra quota với Release' in quiz
    assert 'previewBankOpenEdxImport' in api and 'importBankOpenEdxQuestions' in api


def test_worker_tasks_do_not_turn_broad_failures_into_celery_success() -> None:
    source = read('backend/app/worker.py')
    tree = ast.parse(source)
    task_functions = []
    for node in tree.body:
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        decorators = ' '.join(ast.unparse(item) for item in node.decorator_list)
        if '.task' in decorators or 'shared_task' in decorators:
            task_functions.append(node)
    assert task_functions
    offenders = []
    for fn in task_functions:
        for handler in (node for node in ast.walk(fn) if isinstance(node, ast.ExceptHandler)):
            broad = handler.type is None or (isinstance(handler.type, ast.Name) and handler.type.id in {'Exception', 'BaseException'})
            if not broad:
                continue
            has_return = any(isinstance(item, ast.Return) for stmt in handler.body for item in ast.walk(stmt))
            has_raise = any(isinstance(item, ast.Raise) for stmt in handler.body for item in ast.walk(stmt))
            if has_return and not has_raise:
                offenders.append((fn.name, handler.lineno))
    assert offenders == []


def test_error_boundary_packaging_gate_exists_and_is_wired() -> None:
    checker = read('scripts/error-boundary-contract-check.py')
    assert 'CELERY_SWALLOWED_FAILURE' in checker
    assert 'RAW_EXCEPTION_PUBLIC_MESSAGE' in checker
    assert 'BARE_EXCEPT' in checker
    assert 'error-boundary-contract-check.py' in read('scripts/uat-build-gate.sh')
    assert 'error-boundary-contract-check.py' in read('scripts/claude-code-review-pack.sh')


def _question_for_export(qtype: str, content: dict, *, text: str = 'Câu kiểm thử?'):
    from app.models.question import Question
    from app.services.question_content import apply_canonical_content

    q = Question(
        id=f'test-{qtype}',
        course_id='bank:test',
        question_type=qtype,
        question_text=text,
        option_a='', option_b='', option_c='', option_d='', correct_answer='A',
        explanation='Giải thích kiểm thử',
        difficulty='medium',
        cognitive_level='understand',
        learning_objective='Mục tiêu',
        pedagogy_json={},
        tags=[], quality_flags=[], status='pending_review',
    )
    apply_canonical_content(q, qtype, content)
    return q


def test_openedx_exporter_emits_native_olx_for_all_four_question_types() -> None:
    from xml.etree import ElementTree as ET
    from app.services.openedx_exporter import question_to_openedx_olx

    cases = {
        'single_select': ({'response': {'type': 'single_select', 'options': [
            {'id': 'a', 'text': 'Đúng', 'correct': True}, {'id': 'b', 'text': 'Sai', 'correct': False},
        ]}}, 'multiplechoiceresponse'),
        'multi_select': ({'response': {'type': 'multi_select', 'options': [
            {'id': 'a', 'text': 'Đúng 1', 'correct': True}, {'id': 'b', 'text': 'Đúng 2', 'correct': True},
            {'id': 'c', 'text': 'Sai', 'correct': False},
        ]}}, 'checkboxgroup'),
        'text_input': ({'response': {'type': 'text_input', 'accepted_answers': [
            {'text': 'HTTP', 'case_sensitive': False}, {'text': 'Hypertext Transfer Protocol', 'case_sensitive': False},
        ]}}, 'stringresponse'),
        'numerical_input': ({'response': {'type': 'numerical_input', 'answer': '3.14', 'tolerance': '1', 'tolerance_type': 'percent'}}, 'numericalresponse'),
    }
    for qtype, (content, expected_tag) in cases.items():
        olx = question_to_openedx_olx(_question_for_export(qtype, content))
        root = ET.fromstring(olx)
        assert root.tag == 'problem'
        assert root.find(f'.//{expected_tag}') is not None, (qtype, olx)


def test_question_image_validation_checks_real_bytes_mime_and_svg_rejection() -> None:
    import io
    from PIL import Image
    from app.services.question_media import validate_question_image

    buffer = io.BytesIO()
    Image.new('RGB', (24, 12), 'white').save(buffer, format='PNG')
    image = validate_question_image(buffer.getvalue(), declared_content_type='image/png')
    assert image.mime_type == 'image/png'
    assert (image.width, image.height) == (24, 12)
    assert len(image.sha256) == 64
    with pytest.raises(ValueError, match='Content-Type'):
        validate_question_image(buffer.getvalue(), declared_content_type='image/jpeg')
    with pytest.raises(ValueError, match='không phải ảnh hợp lệ'):
        validate_question_image(b'<svg xmlns="http://www.w3.org/2000/svg"></svg>', declared_content_type='image/svg+xml')


def test_model_gateway_rejects_wrong_count_and_bad_multi_answer_sets_before_db() -> None:
    gateway = ModelGateway()
    valid = [{
        'question': 'Chọn các giao thức web?', 'question_type': 'multi_select',
        'options': {'A': 'HTTP', 'B': 'HTTPS', 'C': 'FTP', 'D': 'SSH'},
        'correct_answers': ['A', 'B'],
    }]
    checked = gateway._validate_generated_questions(valid, question_count=1, target_question_type='multi_select')
    assert checked[0]['correct_answers'] == ['A', 'B']
    with pytest.raises(RuntimeError, match='sai số lượng'):
        gateway._validate_generated_questions(valid, question_count=2, target_question_type='multi_select')
    bad = [{**valid[0], 'correct_answers': ['A', 'A']}]
    with pytest.raises(RuntimeError, match='correct_answers'):
        gateway._validate_generated_questions(bad, question_count=1, target_question_type='multi_select')


def test_legacy_quiz_type_quota_remains_all_single_select() -> None:
    assert exact_type_counts(total=7) == {
        'single_select': 7,
        'multi_select': 0,
        'text_input': 0,
        'numerical_input': 0,
    }
