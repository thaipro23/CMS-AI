"""Execute the real worker body without starting Celery or external services."""
import ast
import asyncio
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.core.config import settings


@pytest.mark.parametrize('comparison_fails', [False, True])
def test_worker_compares_class_once_after_all_learners(monkeypatch, comparison_fails):
    from app.services.learning_analytics import analytics_core_service
    from app.services.academic import subject_delivery
    from app.services import audit_log
    calls = []

    class Service:
        def __init__(self, db):
            pass
        async def ensure_session_structure_from_openedx(self, **kwargs):
            return {'status': 'completed', 'session_count': 1, 'video_count': 1}
        def _student_usernames_for_class(self, **kwargs):
            return [f'sv{i}' for i in range(60)]
        def recalculate_course_video_progress(self, **kwargs):
            return {}
        def recalculate_student_session_progress(self, **kwargs):
            assert kwargs.get('refresh_quiz_integrity') is False
            calls.append(('learner', kwargs['username']))
            return {'sessions': 1, 'quiz': {}}
        def recalculate_learning_behavior(self, **kwargs):
            return {'processed': 1, 'counts': {'NORMAL': 1}}
        def recalculate_class_quiz_integrity(self, **kwargs):
            calls.append(('class', kwargs['class_id']))
            if comparison_fails:
                raise RuntimeError('comparison timeout')
            return {'status': 'completed', 'results': 60}

    job = SimpleNamespace(id='j', status='queued', job_type='learning_analytics_recalculate',
                          class_id='class', request_json={'course_id': 'course'},
                          started_at=None, progress_current=0, result_json=None)
    db = SimpleNamespace(bind=None, get=lambda *a: job, add=lambda *a: None,
                         commit=lambda: None, rollback=lambda: None, close=lambda: None)
    monkeypatch.setattr(analytics_core_service, 'LearningAnalyticsCoreService', Service)
    monkeypatch.setattr(subject_delivery, 'AcademicSubjectDeliveryService', lambda db: SimpleNamespace(
        assert_cms_workflow_allowed_for_class=lambda *a, **kw: None))
    monkeypatch.setattr(audit_log, 'log_audit', lambda *a, **kw: None)
    source = Path(__file__).resolve().parents[1] / 'worker.py'
    tree = ast.parse(source.read_text())
    function = next(n for n in tree.body if isinstance(n, ast.FunctionDef)
                    and n.name == 'analytics_class_recalculate_task')
    function.decorator_list = []
    namespace = {'SessionLocal': lambda: db, 'datetime': datetime, 'settings': settings,
                 'asyncio': asyncio, 'defaultdict': defaultdict,
                 'json_safe_value': lambda value: value}
    exec(compile(ast.Module(body=[function], type_ignores=[]), str(source), 'exec'), namespace)
    result = namespace['analytics_class_recalculate_task']('j')
    assert calls == [*[('learner', f'sv{i}') for i in range(60)], ('class', 'class')]
    assert result['processed_user_count'] == 60
    assert job.status == 'completed'
    assert result['quiz_integrity']['status'] == ('failed' if comparison_fails else 'completed')
    assert ('QUIZ_INTEGRITY_RECALCULATE_FAILED' in result['warnings']) is comparison_fails
