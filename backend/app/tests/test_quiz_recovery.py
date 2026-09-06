from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import pytest

from app.models.question_bank import CourseQuizInstance, EdxCourseChapterMapping, EdxCourseMapping, Subject, SubjectChapter
from app.services.question_bank import quiz_creation, release_publish
from app.services.question_bank.quiz_creation import QuestionBankQuizCreationWorkflowService
from app.services.question_bank.release_publish import QuestionBankReleasePublishWorkflowService
from app.tests.test_legacy_quiz_cms_old_import import _session
from app.tests.test_quiz_difficulty_pools import source_release

COURSE = 'course-v1:FPL+MEC129+FA26'
ROOT = 'block-v1:FPL+MEC129+FA26+type@sequential+block@final'
UNIT = 'block-v1:FPL+MEC129+FA26+type@vertical+block@final-unit'


def instance(db, **kwargs):
    row = CourseQuizInstance(id='old', openedx_course_id=COURSE, subject_id='subject', chapter_id='final',
                             bank_release_id='source', **kwargs)
    db.add(row)
    db.commit()
    return row


@pytest.mark.asyncio
@pytest.mark.parametrize('root,unit', [(ROOT, None), (ROOT, UNIT), (None, UNIT)])
async def test_recovery_uses_root_including_old_failed_records(monkeypatch, root, unit):
    connector = SimpleNamespace(delete_quiz_node=AsyncMock(return_value={'ok': True, 'deleted': True, 'already_missing': True}), get_course_blocks=AsyncMock(return_value=[]))
    monkeypatch.setattr(release_publish, 'get_openedx_connector', lambda: connector)
    with _session() as db:
        row = instance(db, status='rollback_manual_required', openedx_quiz_node_id=root, openedx_unit_node_id=unit,
                       metadata_json={'manual_cleanup_required': True, 'error_message': 'Lỗi tạo bài kiểm tra'})
        service = QuestionBankReleasePublishWorkflowService(SimpleNamespace(db=db))
        result = await service.rollback_course_quiz_instance(instance_id=row.id)
        assert connector.delete_quiz_node.await_args.kwargs['node_id'] == (root or unit)
        assert result['ok'] is True and result['status'] == 'rolled_back'
        assert row.metadata_json['manual_cleanup_required'] is False
        assert row.metadata_json['error_message'] == 'Lỗi tạo bài kiểm tra'
        # Repeated recovery must be idempotent, including when CMS later goes down.
        connector.delete_quiz_node.reset_mock()
        assert (await service.rollback_course_quiz_instance(instance_id=row.id))['ok'] is True
        connector.delete_quiz_node.assert_not_awaited()


@pytest.mark.asyncio
async def test_empty_final_test_section_does_not_count_as_existing_quiz(monkeypatch):
    connector = SimpleNamespace(
        delete_quiz_node=AsyncMock(return_value={'ok': False, 'deleted': False}),
        get_course_blocks=AsyncMock(return_value=[{'block_id': 'section-final', 'type': 'chapter', 'display_name': 'Final test'}]),
    )
    monkeypatch.setattr(release_publish, 'get_openedx_connector', lambda: connector)
    with _session() as db:
        row = instance(db, status='rollback_manual_required', metadata_json={'quiz_title': 'Final test', 'unit_title': 'Final test'})
        result = await QuestionBankReleasePublishWorkflowService(SimpleNamespace(db=db)).rollback_course_quiz_instance(instance_id=row.id)
        assert result['ok'] is True
        assert result['status'] == 'rolled_back'
        assert result['delete_result']['status'] == 'verified_absent_in_course_tree'


@pytest.mark.asyncio
@pytest.mark.parametrize('outcome', [httpx.ReadTimeout('slow CMS'), {'ok': True, 'deleted': False}, {'ok': 'true', 'deleted': 'true'}])
async def test_unconfirmed_deletion_never_unlocks_or_claims_success(monkeypatch, outcome):
    delete = AsyncMock(side_effect=outcome) if isinstance(outcome, Exception) else AsyncMock(return_value=outcome)
    monkeypatch.setattr(release_publish, 'get_openedx_connector', lambda: SimpleNamespace(delete_quiz_node=delete, get_course_blocks=AsyncMock(return_value=[{'block_id': ROOT, 'type': 'sequential', 'display_name': 'Final test'}])))
    with _session() as db:
        row = instance(db, status='rollback_manual_required', openedx_quiz_node_id=ROOT)
        result = await QuestionBankReleasePublishWorkflowService(SimpleNamespace(db=db)).rollback_course_quiz_instance(instance_id=row.id)
        assert result['ok'] is False
        assert result['status'] == 'rollback_manual_required'
        assert result['manual_cleanup_required'] is True


@pytest.mark.asyncio
async def test_recovery_of_already_compensated_failure_does_not_block_again(monkeypatch):
    connector = SimpleNamespace(delete_quiz_node=AsyncMock())
    monkeypatch.setattr(release_publish, 'get_openedx_connector', lambda: connector)
    with _session() as db:
        row = instance(db, status='failed', metadata_json={'compensating_rollback_result': {'ok': True, 'deleted': True}})
        result = await QuestionBankReleasePublishWorkflowService(SimpleNamespace(db=db)).rollback_course_quiz_instance(instance_id=row.id)
        assert result['status'] == 'rolled_back'
        connector.delete_quiz_node.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize('assessment', ['quiz', 'final_test'])
@pytest.mark.parametrize('stage', ['policy', 'timer', 'banks'])
async def test_partial_creation_can_recover_then_create_exactly_one_assessment(monkeypatch, assessment, stage):
    policy = {'ok': True, 'verified': True, 'after': {'max_attempts': 1, 'showanswer': 'never'}}
    result = {'ok': True, 'created_nodes': [{'usage_key': ROOT, 'block_type': 'sequential'}, {'usage_key': UNIT, 'block_type': 'vertical'}],
              'leaf_unit_node_id': UNIT, 'course_quiz_policy_result': policy}
    connector = SimpleNamespace(create_quiz_node=AsyncMock(return_value=result),
        upsert_quiz_timer_config=AsyncMock(return_value={'ok': True}),
        insert_problem_banks=AsyncMock(return_value={'ok': True}),
        delete_quiz_node=AsyncMock(side_effect=httpx.ReadTimeout('delete timeout')))
    monkeypatch.setattr(quiz_creation, 'get_openedx_connector', lambda: connector)
    monkeypatch.setattr(release_publish, 'get_openedx_connector', lambda: connector)
    with _session() as db:
        release = source_release(db, 'source', ['easy'] * 7 + ['medium'] * 3)
        db.add(Subject(id='subject', department_id='dep', code='MEC129', name='Môn học'))
        db.add(SubjectChapter(id='final', subject_id='subject', title='Final test', chapter_no=9))
        db.add(EdxCourseMapping(id='course-map', openedx_course_id=COURSE, subject_id='subject'))
        db.add(EdxCourseChapterMapping(id='mapping', course_mapping_id='course-map', subject_chapter_id='final',
            bank_release_id=release.id, openedx_parent_node_id='block-v1:FPL+MEC129+FA26+type@chapter+block@final'))
        db.commit()
        parent = SimpleNamespace(db=db, _chapter_quiz_suffix=lambda chapter: '9', _chapter_mapping_validation=lambda **kw: {'ok': True, 'checks': []})
        workflow = QuestionBankQuizCreationWorkflowService(parent)
        monkeypatch.setattr(workflow, '_final_test_source_releases', lambda **kw: ([release], []))
        config = dict(course_chapter_mapping_id='mapping', quiz_title='Final test', total_questions=10, assessment_type=assessment)
        if stage == 'policy':
            result['course_quiz_policy_result'] = {}
        elif stage == 'timer':
            connector.upsert_quiz_timer_config.side_effect = httpx.ReadTimeout('timer timeout')
        else:
            connector.insert_problem_banks.side_effect = httpx.ReadTimeout('bank timeout')
        with pytest.raises((RuntimeError, httpx.ReadTimeout)):
            await workflow.create_quiz_from_release(**config)
        old = db.query(CourseQuizInstance).one()
        assert old.status == 'rollback_manual_required'
        assert (old.openedx_quiz_node_id, old.openedx_unit_node_id) == (ROOT, UNIT)
        assert old.metadata_json['quiz_result']['leaf_unit_node_id'] == UNIT
        # Model production's old record: only the root was persisted on failure.
        old.openedx_unit_node_id = None
        db.commit()
        with pytest.raises(ValueError, match='Khôi phục'):
            await workflow.create_quiz_from_release(**config)
        connector.delete_quiz_node.side_effect = None
        connector.delete_quiz_node.return_value = {'ok': True, 'deleted': True, 'already_missing': True}
        recovery = await QuestionBankReleasePublishWorkflowService(parent).rollback_course_quiz_instance(instance_id=old.id)
        assert recovery['ok'] is True
        result['course_quiz_policy_result'] = policy
        connector.upsert_quiz_timer_config.side_effect = None
        connector.insert_problem_banks.side_effect = None
        created = await workflow.create_quiz_from_release(**config)
        assert created['status'] == 'created'
        assert sum(slot['pick_count'] for slot in created['plan']['slots']) == 10
        assert db.query(CourseQuizInstance).filter_by(status='created').count() == 1
        assert db.query(CourseQuizInstance).count() == 2
