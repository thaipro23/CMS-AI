from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[3]
VERSION = '25.9.16.7.2.64.16.5.7.2.18'


def test_release_version_is_synchronized_across_core_build_files():
    assert VERSION in (ROOT / 'backend/app/core/config.py').read_text()
    assert json.loads((ROOT / 'frontend/package.json').read_text())['version'] == VERSION
    assert json.loads((ROOT / 'e2e/package.json').read_text())['version'] == VERSION
    assert VERSION in (ROOT / 'Jenkinsfile').read_text()
    assert VERSION in (ROOT / 'deploy/k8s/base/kustomization.yaml').read_text()
    assert VERSION in (ROOT / 'scripts/build-k8s-images.sh').read_text()


def test_course_id_parser_accepts_multiple_physical_orgs_and_rejects_bad_values():
    from app.services.academic.helpers import _parse_openedx_course_id

    for org in ('FPL', 'FPS', 'FBS', 'ORG-2'):
        parsed = _parse_openedx_course_id(f'course-v1:{org}+WEB107+SU26')
        assert parsed and parsed['org'] == org and parsed['course'] == 'WEB107' and parsed['run'] == 'SU26'
    for bad in ('FPL+WEB107+SU26', 'course-v1:+WEB107+SU26', 'course-v1:F PL+WEB107+SU26', 'course-v1:FPL+WEB107+'):
        assert _parse_openedx_course_id(bad) is None


def test_mapped_multiple_is_treated_as_mapped_by_backend_filter():
    from app.services.academic_service import AcademicService, COURSE_MAPPING_MAPPED_STATUSES

    service = AcademicService.__new__(AcademicService)
    assert 'mapped_multiple' in COURSE_MAPPING_MAPPED_STATUSES
    entry = {'course_mapping_status': 'mapped_multiple', 'openedx_course_id': None}
    assert service._entry_matches_learning_list_filter(entry, 'no_course_map') is False


def test_branch_org_mapping_is_optional_and_never_falls_back_to_fpt(monkeypatch):
    from app.core.config import settings
    from app.services.academic_service import AcademicService

    term = SimpleNamespace(id='t1', branch='poly', term_code='SU26', term_name='Summer 2026')
    subject = SimpleNamespace(id='s1', branch='poly', subject_code='WEB107')

    class FakeDB:
        def get(self, model, key):
            return term if key == 't1' else subject if key == 's1' else None

    service = AcademicService(FakeDB())
    monkeypatch.setattr(settings, 'academic_openedx_org_by_branch', '')
    monkeypatch.setattr(settings, 'academic_default_openedx_course_org', None)
    assert service.suggested_course_id_for_scope('t1', 's1').startswith('course-v1:ORG+WEB107+')

    monkeypatch.setattr(settings, 'academic_openedx_org_by_branch', '{"poly":"FPL","ptcd":"FPS"}')
    assert service.suggested_course_id_for_scope('t1', 's1').startswith('course-v1:FPL+WEB107+')


def test_env_contract_has_shared_library_internal_route_retry_and_no_auto_create():
    prod = (ROOT / '.env.production.example').read_text()
    expected = [
        'OPENEDX_LIBRARY_ORG=FPT',
        'OPENEDX_CMS_INTERNAL_BASE_URL=http://cms.openedx.svc.cluster.local:8000',
        'OPENEDX_CMS_HOST_HEADER=scms.fpl.edu.vn',
        'OPENEDX_RETRY_MAX_ATTEMPTS=4',
        'OPENEDX_RETRY_BASE_SECONDS=2',
        'OPENEDX_RETRY_MAX_SECONDS=60',
        'ACADEMIC_OPENEDX_ORG_BY_BRANCH=',
        'ACADEMIC_DEFAULT_OPENEDX_COURSE_ORG=',
        'AI_CONNECTOR_LIBRARY_ORG=FPT',
        'AI_CONNECTOR_AUTO_CREATE_ORG=false',
    ]
    for value in expected:
        assert value in prod


def test_connector_plugin_candidate_is_018_and_reports_missing_org_structurally():
    setup = (ROOT / 'openedx-connector-plugin/setup.py').read_text()
    studio = (ROOT / 'openedx-connector-plugin/openedx_ai_connector/studio.py').read_text()
    tutor = (ROOT / 'tutor-plugins/ai_learning_connector_env.py').read_text()
    assert 'version="0.1.8"' in setup
    assert "'error_code': 'openedx_library_org_missing'" in studio
    assert "_setting_or_env('AI_CONNECTOR_LIBRARY_ORG', 'FPT')" in studio
    assert '("AI_CONNECTOR_LIBRARY_ORG", "FPT")' in tutor
    assert '("AI_CONNECTOR_AUTO_CREATE_ORG", "false")' in tutor


def test_release_publish_is_decoupled_from_physical_course_org():
    source = (ROOT / 'backend/app/services/question_bank/release_publish.py').read_text()
    assert "return f'lib:{self._canonical_library_org()}:{key_slug}'" in source
    assert "return f'course-v1:{org}+{course_token}+BANK'" in source
    assert "'shared_across_courses': True" in source
    assert "'requested_physical_course_id'" in source
    assert 'course-v1:FPT+' not in source


def test_release_publish_requires_verification_before_published_and_quiz():
    publish = (ROOT / 'backend/app/services/question_bank/release_publish.py').read_text()
    quiz = (ROOT / 'backend/app/services/question_bank/quiz_creation.py').read_text()
    assert "'verification_complete': True" in publish
    assert 'component chưa được Open edX verify' in publish
    assert "get('verification_complete')" in quiz
    assert 'Release chưa có bằng chứng verify đầy đủ từ Open edX' in quiz


def test_duplicate_open_release_is_guarded_before_database_unique_error():
    source = (ROOT / 'backend/app/services/question_bank/release_publish.py').read_text()
    assert "'existing_open_release'" in source
    assert 'Bank Version đã có Release' in source
    assert 'except IntegrityError as exc:' in source


def test_term_inference_does_not_use_arbitrary_version_code():
    source = (ROOT / 'backend/app/services/question_bank/release_publish.py').read_text()
    start = source.index('def _release_offering_term_slug')
    end = source.index('def release_library_key', start)
    term_function = source[start:end]
    assert 'version.version_code' not in term_function
    assert 'term_pattern = re.compile' in term_function


def test_analytics_direct_mapping_wins_over_subject_mapping():
    source = (ROOT / 'backend/app/services/learning_analytics/analytics_core_service.py').read_text()
    assert 'direct_override_class_ids' in source
    assert 'str(class_id) not in direct_override_class_ids' in source
    assert 'AcademicService(self.db).effective_course_mapping_for_class(cls)' in source


def test_student_teacher_sync_fail_closed_on_unverified_physical_course():
    sync = (ROOT / 'backend/app/services/academic/sync_enrollment.py').read_text()
    assert 'def _assert_live_course_for_mutation' in sync
    assert 'verify_course_exists(course_id)' in sync
    assert sync.count('self._assert_live_course_for_mutation(course_id)') >= 2


def test_course_remap_has_explicit_cleanup_and_shared_reference_guard():
    service = (ROOT / 'backend/app/services/academic_service.py').read_text()
    plugin = (ROOT / 'openedx-connector-plugin/openedx_ai_connector/student_insight.py').read_text()
    urls = (ROOT / 'openedx-connector-plugin/openedx_ai_connector/urls.py').read_text()
    assert 'cleanup_previous_course' in service
    assert '_other_class_uses_course_for_student' in service
    assert '_other_class_uses_course_for_teacher' in service
    assert '_cleanup_previous_course_access_for_class' in service
    assert 'student_insight_course_enrollment_remove' in plugin
    assert 'course-enrollment/remove' in urls


def test_teacher_metadata_keeps_course_specific_role_history():
    source = (ROOT / 'backend/app/services/academic/sync_enrollment.py').read_text()
    assert "'course_staff_by_course'" in source
    assert 'by_course[course_id] = staff_record' in source


def test_bank_operation_jobs_do_not_expose_raw_tracebacks():
    source = (ROOT / 'backend/app/services/bank_operation_jobs.py').read_text()
    assert "'traceback_tail'" in source  # explicitly filtered
    assert "safe_result.update({'ok': False, 'error_code': error_code" in source
    assert 'traceback.format_exc' not in source


def test_all_bank_worker_failure_paths_re_raise_after_job_fail():
    source = (ROOT / 'backend/app/worker.py').read_text()
    assert 'return ops.fail' not in source
    assert source.count('ops.fail(job, error=exc') >= 5


@pytest.mark.asyncio
async def test_internal_cms_connector_headers_are_hmac_only_and_keep_public_host(monkeypatch):
    from app.core.config import settings
    from app.modules.openedx_connector.real import RealOpenEdXConnector

    monkeypatch.setattr(settings, 'openedx_cms_base_url', 'https://scms.fpl.edu.vn')
    monkeypatch.setattr(settings, 'openedx_cms_internal_base_url', 'http://cms.openedx.svc.cluster.local:8000')
    monkeypatch.setattr(settings, 'openedx_cms_host_header', 'scms.fpl.edu.vn')
    monkeypatch.setattr(settings, 'openedx_connector_hmac_secret', 'x' * 64)
    connector = RealOpenEdXConnector()
    called = {'token': 0}

    async def fail_if_token_called():
        called['token'] += 1
        raise AssertionError('OAuth should not be needed for connector headers')

    monkeypatch.setattr(connector, '_get_token', fail_if_token_called)
    url = 'http://cms.openedx.svc.cluster.local:8000/api/ai-connector/v1/x'
    headers = await connector._json_request_headers('POST', url, b'{}')
    assert called['token'] == 0
    assert headers['Host'] == 'scms.fpl.edu.vn'
    assert headers['X-AI-Connector-Signature']
    assert 'Authorization' not in headers


@pytest.mark.asyncio
async def test_retry_transient_502_then_success(monkeypatch):
    from app.core.config import settings
    from app.modules.openedx_connector import real
    from app.modules.openedx_connector.real import RealOpenEdXConnector

    calls, sleeps = [], []

    class Response:
        def __init__(self, status, payload):
            self.status_code, self._payload, self.text = status, payload, json.dumps(payload)
            self.headers = {}
        def json(self): return self._payload

    responses = [Response(502, {'error_name': 'origin_bad_gateway'}), Response(200, {'ok': True})]

    class Client:
        def __init__(self, timeout=None): pass
        async def __aenter__(self): return self
        async def __aexit__(self, *args): return False
        async def post(self, url, content=None, headers=None):
            calls.append(url); return responses.pop(0)

    async def fake_sleep(delay): sleeps.append(delay)
    monkeypatch.setattr(real.httpx, 'AsyncClient', Client)
    monkeypatch.setattr(real.asyncio, 'sleep', fake_sleep)
    monkeypatch.setattr(real.random, 'uniform', lambda *args: 0.0)
    monkeypatch.setattr(settings, 'openedx_retry_max_attempts', 3)
    monkeypatch.setattr(settings, 'openedx_retry_base_seconds', 2.0)
    connector = RealOpenEdXConnector()
    result = await connector._post_connector_json(url='https://scms.fpl.edu.vn/x', body=b'{}', step='ensure_library', retry_safe=True)
    assert result == {'ok': True}
    assert len(calls) == 2 and sleeps == [2.0]


@pytest.mark.asyncio
async def test_non_idempotent_mutation_does_not_retry_502(monkeypatch):
    from app.core.config import settings
    from app.modules.openedx_connector import real
    from app.modules.openedx_connector.real import RealOpenEdXConnector

    calls = []
    class Response:
        status_code = 502
        text = 'bad gateway'
        headers = {}
        def json(self): return {'error_name': 'origin_bad_gateway'}
    class Client:
        def __init__(self, timeout=None): pass
        async def __aenter__(self): return self
        async def __aexit__(self, *args): return False
        async def post(self, url, content=None, headers=None): calls.append(url); return Response()
    monkeypatch.setattr(real.httpx, 'AsyncClient', Client)
    monkeypatch.setattr(settings, 'openedx_retry_max_attempts', 4)
    connector = RealOpenEdXConnector()
    with pytest.raises(RuntimeError):
        await connector._post_connector_json(url='https://scms.fpl.edu.vn/x', body=b'{}', step='create_quiz_node', retry_safe=False)
    assert len(calls) == 1


def test_frontend_contract_handles_multi_course_subjects_and_physical_org():
    student_ui = (ROOT / 'frontend/app/student-management/StudentManagementPlatformPage.tsx').read_text()
    analytics_ui = (ROOT / 'frontend/app/analytics/learning/page.tsx').read_text()
    types = (ROOT / 'frontend/types/index.ts').read_text()
    assert 'mapped_multiple' in student_ui
    assert 'openedx_course_ids?: string[]' in types
    assert 'openedx_orgs?: string[]' in types
    assert "item.openedx_org || 'ORG'" in analytics_ui
