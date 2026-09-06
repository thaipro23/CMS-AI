from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock
from xml.etree import ElementTree as ET
import json

import httpx
import pytest

from app.models.question import Question
from app.models.question_bank import BankReleaseQuestion, QuestionBankRelease
from app.modules.openedx_connector.real import RealOpenEdXConnector
from app.services.bank_operation_jobs import bank_operation_error_code, bank_operation_user_message
from app.services.openedx_exporter import question_to_openedx_olx
from app.services.question_bank.quiz_creation import QuestionBankQuizCreationWorkflowService
from app.tests.test_legacy_quiz_cms_old_import import _session
from app.tests.test_openedx_exporter import make_question


def source_release(db, key, difficulties, mode='manual'):
    release = QuestionBankRelease(id=key, bank_version_id=f'v-{key}', subject_id='subject',
        chapter_id=key, release_code=key, status='published', openedx_library_key=f'lib:FPT:{key}',
        metadata_json={'verification_complete': True})
    db.add(release)
    for i, difficulty in enumerate(difficulties):
        question = Question(id=f'{key}-{i}', course_id='bank:test', bank_version_id=f'v-{key}',
            question_text=f'Câu hỏi {i} của {key}?', topic='Q1', difficulty=difficulty,
            authoring_mode=mode, source_type='legacy_quiz_excel' if mode == 'import' else mode,
            source_evidence=json.dumps({'difficulty_classified': True}),
            question_type='multi_select' if i % 2 else 'single_select', status='published',
            option_a='A', option_b='B', option_c='', option_d='', correct_answer='A')
        db.add(question)
        db.add(BankReleaseQuestion(bank_release_id=key, question_id=question.id, difficulty=difficulty,
            openedx_library_problem_id=f'lb:FPT:{key}:problem:p{i}'))
    db.commit()
    return release


@pytest.mark.parametrize('mode', ['manual', 'import'])
def test_manual_quiz_samples_ten_easy_and_five_medium_from_whole_pools(mode):
    with _session() as db:
        release = source_release(db, 'manual', ['easy'] * 30 + ['medium'] * 20, mode)
        plan = QuestionBankQuizCreationWorkflowService(SimpleNamespace(db=db))._build_release_quiz_plan(
            release=release, total_questions=15, difficulty_easy=67, difficulty_medium=33, difficulty_hard=0)
        assert plan['sampling_strategy'] == 'difficulty_pool'
        assert [(slot['difficulty'], slot['pick_count'], len(slot['question_ids'])) for slot in plan['slots']] == [('EASY', 10, 30), ('MEDIUM', 5, 20)]
        assert all(slot['families'] == [] for slot in plan['slots'])
        ids = [qid for slot in plan['slots'] for qid in slot['question_ids']]
        assert len(ids) == len(set(ids)) == 50
        assert {db.get(Question, qid).question_type for qid in ids} == {'single_select', 'multi_select'}
        assert all(title.startswith('Câu hỏi:') for slot in plan['slots'] for title in slot['problem_display_names'].values())


@pytest.mark.parametrize('assessment', ['quiz', 'final_test'])
@pytest.mark.parametrize('mode', ['manual', 'import', 'ai'])
def test_take_all_ten_questions_uses_actual_difficulties(assessment, mode):
    with _session() as db:
        release = source_release(db, 'takeall', ['easy'] * 7 + ['medium'] * 3, mode)
        service = QuestionBankQuizCreationWorkflowService(SimpleNamespace(db=db))
        config = dict(total_questions=10, difficulty_easy=50, difficulty_medium=30, difficulty_hard=20)
        plan = service._build_final_test_plan(source_releases=[release], source_details=[], **config) if assessment == 'final_test' else service._build_release_quiz_plan(release=release, **config)
        assert plan['effective_target_counts'] == {'EASY': 7, 'MEDIUM': 3, 'HARD': 0}
        assert sum(slot['pick_count'] for slot in plan['slots']) == 10
        assert all(slot['pick_count'] == len(slot['question_ids']) for slot in plan['slots'])
        assert len({qid for slot in plan['slots'] for qid in slot['question_ids']}) == 10


def test_final_pools_keep_libraries_separate_and_cover_every_lesson():
    with _session() as db:
        releases = [source_release(db, f'lesson{i}', ['easy'] * 4 + ['medium'] * 2) for i in range(8)]
        plan = QuestionBankQuizCreationWorkflowService(SimpleNamespace(db=db))._build_final_test_plan(
            source_releases=releases, source_details=[], total_questions=15,
            difficulty_easy=67, difficulty_medium=33, difficulty_hard=0)
        assert all(count > 0 for count in plan['source_release_pick_counts'].values())
        assert sum(slot['pick_count'] for slot in plan['slots']) == 15
        for slot in plan['slots']:
            assert slot['pick_count'] <= len(slot['openedx_problem_ids'])
            assert all(ref.startswith('lb:' + slot['library_key'][4:] + ':') for ref in slot['openedx_problem_ids'])


def test_final_pool_splits_large_lesson_into_bounded_problem_banks():
    with _session() as db:
        release = source_release(db, 'large-lesson', ['easy'] * 50)
        plan = QuestionBankQuizCreationWorkflowService(SimpleNamespace(db=db))._build_final_test_plan(
            source_releases=[release], source_details=[], total_questions=10,
            difficulty_easy=100, difficulty_medium=0, difficulty_hard=0)

        assert len(plan['slots']) == 5
        assert [len(slot['openedx_problem_ids']) for slot in plan['slots']] == [10] * 5
        assert [slot['pick_count'] for slot in plan['slots']] == [2] * 5
        assert sum(slot['pick_count'] for slot in plan['slots']) == 10
        assert len({component for slot in plan['slots'] for component in slot['openedx_problem_ids']}) == 50
        assert all(slot['source_bank_count'] == 5 for slot in plan['slots'])


def test_final_pool_balances_eight_equal_lessons_without_exceeding_total():
    with _session() as db:
        releases = [source_release(db, f'lesson-{index}', ['easy'] * 50) for index in range(8)]
        plan = QuestionBankQuizCreationWorkflowService(SimpleNamespace(db=db))._build_final_test_plan(
            source_releases=releases, source_details=[], total_questions=50,
            difficulty_easy=100, difficulty_medium=0, difficulty_hard=0)

        picks = list(plan['source_release_pick_counts'].values())
        assert sum(picks) == 50
        assert sorted(picks) == [6] * 6 + [7] * 2
        assert max(picks) - min(picks) <= 1
        assert plan['source_release_candidate_counts'] == {f'lesson-{index}': 50 for index in range(8)}
        assert plan['source_release_distribution_policy'] == 'capacity_balanced_water_filling_v1'


def test_native_ai_still_requires_requested_difficulty_when_not_taking_all():
    with _session() as db:
        release = source_release(db, 'ai', ['medium'] * 10, 'ai')
        with pytest.raises(ValueError, match='không đủ câu theo độ khó'):
            QuestionBankQuizCreationWorkflowService(SimpleNamespace(db=db))._build_release_quiz_plan(
                release=release, total_questions=5, difficulty_easy=100, difficulty_medium=0, difficulty_hard=0)


@pytest.mark.parametrize('assessment', ['quiz', 'final_test'])
def test_request_more_than_available_is_rejected(assessment):
    with _session() as db:
        release = source_release(db, 'short', ['easy'] * 10)
        service = QuestionBankQuizCreationWorkflowService(SimpleNamespace(db=db))
        config = dict(total_questions=11, difficulty_easy=100, difficulty_medium=0, difficulty_hard=0)
        with pytest.raises(ValueError, match='không đủ 11 câu'):
            if assessment == 'quiz':
                service._build_release_quiz_plan(release=release, **config)
            else:
                service._build_final_test_plan(source_releases=[release], source_details=[], **config)


@pytest.mark.parametrize('mode', ['manual', 'import'])
def test_exported_question_title_uses_prompt_instead_of_q1(mode):
    xml = question_to_openedx_olx(make_question(authoring_mode=mode, topic='Q1', learning_objective='Q1', source_node_title='Q1'))
    root = ET.fromstring(xml)
    assert root.get('display_name') == 'Câu hỏi: GET dùng để làm gì?'
    assert root.find('.//multiplechoiceresponse') is not None
    assert root.find('.//choice[@correct="true"]').text == 'Lấy dữ liệu'


def connector_slots():
    return [{'slot_no': i + 1, 'library_key': f'lib:FPT:lesson{i}', 'openedx_problem_ids': [f'lb:FPT:lesson{i}:problem:p'], 'pick_count': 1} for i in range(3)]


@pytest.mark.asyncio
async def test_connector_sends_final_banks_sequentially_and_preserves_contract():
    connector = RealOpenEdXConnector()
    connector._post_connector_json = AsyncMock(return_value={'ok': True, 'implementation': 'native_ulmo_itembank',
        'problem_bank_blocks': [{'usage_key': 'bank', 'block_type': 'itembank', 'selection_verified': True}]})
    result = await connector.insert_problem_banks('course-v1:FPT+TEST+FA26', 'unit', connector_slots())
    sent = [json.loads(call.kwargs['body']) for call in connector._post_connector_json.await_args_list]
    assert [item['slots'] for item in sent] == [[slot] for slot in connector_slots()]
    assert [item['metadata']['cleanup_legacy_ai_randomized_blocks'] for item in sent] == [True, False, False]
    assert all(call.kwargs['retry_safe'] is False for call in connector._post_connector_json.await_args_list)
    assert result['slots_inserted'] == len(result['problem_bank_blocks']) == 3


@pytest.mark.asyncio
async def test_connector_timeout_has_cause_and_never_retries_writes():
    connector = RealOpenEdXConnector()
    connector._post_connector_json = AsyncMock(side_effect=httpx.ReadTimeout(''))
    with pytest.raises(httpx.ReadTimeout) as caught:
        await connector.insert_problem_banks('course-v1:FPT+TEST+FA26', 'unit', connector_slots())
    connector._post_connector_json.assert_awaited_once()
    assert bank_operation_error_code(caught.value) == 'OPENEDX_REQUEST_TIMEOUT'
    assert 'nhóm câu 1/3' in bank_operation_user_message(caught.value)
    assert bank_operation_user_message(httpx.ReadTimeout('')).strip()


@pytest.mark.asyncio
async def test_cross_bank_duplicates_are_rejected_before_remote_mutation():
    connector = RealOpenEdXConnector()
    connector._post_connector_json = AsyncMock()
    slots = connector_slots()
    with pytest.raises(ValueError, match='nhiều nhóm'):
        await connector.insert_problem_banks('course-v1:FPT+TEST+FA26', 'unit', [slots[0], slots[0]])
    connector._post_connector_json.assert_not_awaited()


def test_worker_persists_timeout_and_audits_requester(monkeypatch):
    from app import worker
    from app.services.bank_operation_jobs import BankOperationJobService
    from app.services.question_bank_service import VersionedQuestionBankService
    db, ops, audit = Mock(), Mock(), Mock()
    job = SimpleNamespace(id='job', request_json={'assessment_type': 'final_test'}, requested_by='teacher', release_id='r', course_id='course')
    ops.get_job.return_value = job
    monkeypatch.setattr(worker, 'SessionLocal', lambda: db)
    monkeypatch.setattr(BankOperationJobService, '__new__', lambda cls, db: ops)
    monkeypatch.setattr(VersionedQuestionBankService, 'create_quiz_from_release', AsyncMock(side_effect=httpx.ReadTimeout('')))
    monkeypatch.setattr('app.services.audit_log.log_audit', audit)
    with pytest.raises(httpx.ReadTimeout):
        worker.bank_quiz_create_task.run(job.id)
    ops.fail.assert_called_once()
    assert audit.call_args.kwargs['actor_id'] == 'teacher'
    assert audit.call_args.kwargs['message']
    assert audit.call_args.kwargs['metadata']['exception_class'] == 'ReadTimeout'
