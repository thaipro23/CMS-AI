from __future__ import annotations

import os
import sys
import types
from pathlib import Path

import pytest

os.environ.setdefault('DATABASE_URL', 'sqlite+pysqlite:///:memory:')
os.environ.setdefault('APP_ENV', 'test')
from fastapi import HTTPException

if 'openai' not in sys.modules:
    module = types.ModuleType('openai')
    module.AsyncOpenAI = object
    sys.modules['openai'] = module
if 'jose' not in sys.modules:
    jose_module = types.ModuleType('jose')
    jose_module.JWTError = type('JWTError', (Exception,), {})
    jose_module.jwt = types.SimpleNamespace()
    sys.modules['jose'] = jose_module

from app.core.rbac import UserContext


ROOT = Path(__file__).resolve().parents[3]


def test_celery_routes_and_reliability_settings_are_active():
    source = (ROOT / 'backend' / 'app' / 'worker.py').read_text(encoding='utf-8')
    assert 'task_acks_late=bool(settings.celery_task_acks_late)' in source
    assert 'task_reject_on_worker_lost=bool(settings.celery_task_reject_on_worker_lost)' in source
    assert 'worker_prefetch_multiplier=int(settings.celery_worker_prefetch_multiplier)' in source
    assert "'generate_questions_task': {'queue': 'generation'}" in source
    assert "'academic_teacher_report_job_task': {'queue': 'exports'}" in source
    assert "'analytics_ingest_task': {'queue': 'analytics'}" in source
    assert "'academic_ap_sync_task': {'queue': 'sync'}" in source
    assert "'visibility_timeout': int(settings.celery_broker_visibility_timeout_seconds)" in source
    env = (ROOT / '.env.production.example').read_text(encoding='utf-8')
    assert 'CELERY_TASK_ACKS_LATE=true' in env
    assert 'CELERY_TASK_REJECT_ON_WORKER_LOST=true' in env


def test_compose_splits_heavy_and_analytics_workers():
    source = (ROOT / 'docker-compose.prod.yml').read_text(encoding='utf-8')
    assert 'worker-heavy:' in source
    assert 'worker-analytics:' in source
    assert '--queues=interactive,sync' in source
    assert '--queues=generation,exports' in source
    assert '--queues=analytics' in source
    assert '--prefetch-multiplier=${CELERY_WORKER_PREFETCH_MULTIPLIER:-1}' in source
    assert '--max-tasks-per-child=${CELERY_WORKER_MAX_TASKS_PER_CHILD:-25}' in source


def test_large_sync_teacher_export_is_rejected(monkeypatch):
    from app.api.routes import academic as route

    class FakeService:
        def __init__(self, _db):
            pass

        def training_teacher_report(self, _user, **kwargs):
            assert kwargs['include_students'] is False
            return {'total': 21, 'summary': {'unique_student_count': 500}}

    monkeypatch.setattr(route, 'AcademicService', FakeService)
    monkeypatch.setattr(route.settings, 'academic_teacher_report_sync_export_max_teachers', 20)
    monkeypatch.setattr(route.settings, 'academic_teacher_report_sync_export_max_students', 1000)
    user = UserContext(user_id='admin', username='admin', role='admin', permissions={'view_training_reports'}, raw_claims={})
    with pytest.raises(HTTPException) as exc:
        route.export_training_teacher_report(term_id='term', user=user, db=object())
    assert exc.value.status_code == 409
    assert exc.value.detail['code'] == 'TEACHER_EXPORT_REQUIRES_BACKGROUND_JOB'


def test_small_sync_teacher_export_keeps_compatibility(monkeypatch):
    from app.api.routes import academic as route

    calls: list[dict] = []

    class FakeService:
        def __init__(self, _db):
            pass

        def training_teacher_report(self, _user, **kwargs):
            calls.append(kwargs)
            if not kwargs.get('include_students'):
                return {'total': 1, 'summary': {'unique_student_count': 10}}
            return {'items': [], 'student_watch_rows': [], 'summary': {}}

    monkeypatch.setattr(route, 'AcademicService', FakeService)
    monkeypatch.setattr(route, '_build_training_teacher_report_xlsx', lambda report: b'xlsx')
    monkeypatch.setattr(route.settings, 'academic_teacher_report_sync_export_max_teachers', 20)
    monkeypatch.setattr(route.settings, 'academic_teacher_report_sync_export_max_students', 1000)
    user = UserContext(user_id='admin', username='admin', role='admin', permissions={'view_training_reports'}, raw_claims={})
    response = route.export_training_teacher_report(term_id='term', user=user, db=object())
    assert response.media_type == 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    assert len(calls) == 2
    assert calls[0]['include_students'] is False
    assert calls[1]['include_students'] is True


def test_teacher_export_worker_writes_file_without_bytes_copy_and_rechecks_requester():
    source = (ROOT / 'backend' / 'app' / 'worker.py').read_text(encoding='utf-8')
    assert "_worker_user_from_request_json(" in source
    assert "_write_training_teacher_report_xlsx(report, path)" in source
    assert "academic_teacher_report_file_retention_hours" in source
    assert "content = _build_training_teacher_report_xlsx(report)" not in source
    assert "job.error_message = str(exc)" not in source[source.index("def academic_teacher_report_job_task"):source.index("@celery_app.task(name='analytics_ingest_task')")]
    assert "ACADEMIC_TEACHER_REPORT_FAILED" in source


def test_frontend_api_has_timeout_abort_retry_and_auth_expiry_contract():
    source = (ROOT / 'frontend' / 'lib' / 'api.ts').read_text(encoding='utf-8')
    assert 'export type ApiFetchInit' in source
    assert 'NEXT_PUBLIC_API_GET_TIMEOUT_MS' in source
    assert 'NEXT_PUBLIC_API_WRITE_TIMEOUT_MS' in source
    assert 'RETRYABLE_STATUS_CODES' in source
    assert 'signal: controller.signal' in source
    assert 'ai:auth-expired' in source
    assert 'initialIntervalMs' in source
    assert 'maxIntervalMs' in source
    assert 'backoffMultiplier' in source


def test_teacher_page_uses_background_export_and_abortable_backoff():
    source = (ROOT / 'frontend' / 'app' / 'teacher-management' / 'TeacherManagementPlatformPage.tsx').read_text(encoding='utf-8')
    assert 'waitForAcademicTrainingTeacherReportJob' in source
    assert 'new AbortController()' in source
    assert 'Xuất Excel nền' not in source
    assert 'Xuất trực tiếp' not in source
    assert 'downloadAcademicTrainingTeacherReport(' not in source


def test_rbac_scope_catalog_is_server_searched_instead_of_eager_full_tree():
    users = (ROOT / 'frontend' / 'app' / 'users' / 'page.tsx').read_text(encoding='utf-8')
    route = (ROOT / 'backend' / 'app' / 'api' / 'routes' / 'question_bank_v2.py').read_text(encoding='utf-8')
    assert 'searchSubjects' in users
    assert 'searchSubjectOfferings' in users
    assert 'getSubjectChapters(headers)' not in users
    assert 'getSubjectOfferings(headers)' not in users
    assert 'getSubjects(headers)' not in users
    assert "q: str | None = Query(None, max_length=120)" in route


def test_class_analytics_recalculate_filters_events_to_class_roster():
    source = (ROOT / 'backend' / 'app' / 'services' / 'learning_analytics' / 'analytics_core_service.py').read_text(encoding='utf-8')
    worker = (ROOT / 'backend' / 'app' / 'worker.py').read_text(encoding='utf-8')
    route = (ROOT / 'backend' / 'app' / 'api' / 'routes' / 'learning_analytics.py').read_text(encoding='utf-8')
    assert 'class_id: str | None = None' in source
    assert 'AnalyticsTrackingEvent.username.in_(target_usernames)' in source
    assert 'class_id=job.class_id' in worker
    assert 'class_id=class_id' in route
