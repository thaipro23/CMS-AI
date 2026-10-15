import asyncio
from contextvars import Context

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

import app.services.fa26_compat as compat
from app.models.question_bank import BankOperationJob
from app.services.bank_operation_jobs import BankOperationJobService


def _mutate_raw_config_and_check_other_context(context):
    raw = context.run(compat._QUIZ_CONSTRAINT_CONTEXT.get)
    if raw is None:
        assert Context().run(compat.current_quiz_constraint_config)['question_type_weights']['single_select'] == 50
        return
    saved = dict(raw['question_type_weights'])
    try:
        raw['question_type_weights']['single_select'] = 99
        # A raw mutable default must not poison another request's defaults.
        assert Context().run(compat.current_quiz_constraint_config)['question_type_weights']['single_select'] == 50
    finally:
        raw['question_type_weights'].clear()
        raw['question_type_weights'].update(saved)


def test_unbound_context_cannot_mutate_another_contexts_default_weights():
    _mutate_raw_config_and_check_other_context(Context())


def test_worker_default_reset_does_not_share_nested_weights():
    engine = create_engine('sqlite:///:memory:')
    BankOperationJob.__table__.create(engine)
    with Session(engine) as db:
        context = Context()
        # Other legacy tests temporarily replace the service's __new__ slot.
        service = object.__new__(BankOperationJobService)
        BankOperationJobService.__init__(service, db)
        assert context.run(compat._get_job_compat, service, 'missing-job') is None
        _mutate_raw_config_and_check_other_context(context)
    engine.dispose()


def test_nested_request_binding_restores_parent_even_after_exception():
    def run():
        outer = compat.bind_quiz_constraint_request({'difficulty_enabled': False})
        try:
            with pytest.raises(RuntimeError):
                inner = compat.bind_quiz_constraint_request({'difficulty_enabled': True})
                try:
                    assert compat.current_quiz_constraint_config()['difficulty_enabled'] is True
                    raise RuntimeError('request failed')
                finally:
                    compat.reset_quiz_constraint_request(inner)
            assert compat.current_quiz_constraint_config()['difficulty_enabled'] is False
        finally:
            compat.reset_quiz_constraint_request(outer)
        assert compat.current_quiz_constraint_config()['difficulty_enabled'] is True
    Context().run(run)


@pytest.mark.asyncio
async def test_concurrent_tasks_and_returned_snapshots_keep_separate_config():
    ready = [asyncio.Event(), asyncio.Event()]
    async def request(index, difficulty):
        payload = {'difficulty_enabled': difficulty, 'question_type_weights': {'single_select': 70 + index}}
        token = compat.bind_quiz_constraint_request(payload)
        try:
            payload['question_type_weights']['single_select'] = 99
            ready[index].set()
            await ready[1-index].wait()
            snapshot = compat.current_quiz_constraint_config()
            assert snapshot['difficulty_enabled'] is difficulty
            assert snapshot['question_type_weights']['single_select'] == 70 + index
            snapshot['question_type_weights']['single_select'] = 0
            assert compat.current_quiz_constraint_config()['question_type_weights']['single_select'] == 70 + index
        finally:
            compat.reset_quiz_constraint_request(token)
    await asyncio.gather(request(0, False), request(1, True))
