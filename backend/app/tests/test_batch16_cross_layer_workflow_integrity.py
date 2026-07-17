from __future__ import annotations

import sys
import types
from pathlib import Path
from types import SimpleNamespace

# The focused workflow tests do not exercise JWT signing/verification, but the
# application security module imports python-jose during test collection. Keep
# collection isolated from optional auth dependencies in this execution image.
if "jose" not in sys.modules:
    jose_stub = types.ModuleType("jose")

    class JWTError(Exception):
        pass

    class _JWTStub:
        @staticmethod
        def decode(*args, **kwargs):
            return {}

        @staticmethod
        def encode(*args, **kwargs):
            return "test-token"

        @staticmethod
        def get_unverified_claims(*args, **kwargs):
            return {}

    jose_stub.JWTError = JWTError
    jose_stub.jwt = _JWTStub()
    sys.modules["jose"] = jose_stub

import pytest

from app.core.openedx_ids import normalize_openedx_course_id, openedx_course_id_candidates
from app.schemas.academic import AcademicAPSyncIn
from app.services.academic.ap_sync import AcademicAPSyncWorkflowService
from app.services.academic.helpers import _parse_openedx_course_id
from app.services.question_bank.helpers import parse_openedx_course_id


ROOT = Path(__file__).resolve().parents[2]


def test_course_id_is_canonical_across_bank_and_academic_helpers():
    expected = 'course-v1:FPT+COM1071+SU26'
    inputs = [
        expected,
        expected + '/',
        'course-v1%3AFPT%2BCOM1071%2BSU26%2F',
        f'https://studio.example.edu/course/{expected}/course',
        f'https://studio.example.edu/courses/{expected}/settings/details',
    ]
    for value in inputs:
        assert normalize_openedx_course_id(value, required=True) == expected
        assert parse_openedx_course_id(value)['normalized_course_id'] == expected
        assert _parse_openedx_course_id(value)['raw'] == expected
    assert openedx_course_id_candidates(expected) == (expected, expected + '/')


def test_invalid_course_id_is_rejected_instead_of_forwarded_to_openedx():
    assert normalize_openedx_course_id('COM1071-SU26') == ''
    with pytest.raises(ValueError):
        normalize_openedx_course_id('COM1071-SU26', required=True)


def test_ap_request_normalization_is_deterministic_and_scope_safe():
    payload = AcademicAPSyncIn(
        term_name=' Summer 2026 ',
        sync_scope='subject',
        campus='PS',
        campuses=['ps', 'PH', 'ps'],
        branch='POLY',
        subject_codes=[' com1071 ', 'COM1071', 'aut1041'],
        max_subjects=25,
        dry_run=True,
    )
    normalized = AcademicAPSyncWorkflowService._normalized_ap_request(payload)
    assert normalized == {
        'term_name': 'Summer 2026',
        'sync_scope': 'subject',
        'campus': 'ps',
        'campuses': ['ph', 'ps'],
        'branch': 'poly',
        'subject_codes': ['AUT1041', 'COM1071'],
        'max_subjects': 25,
        'dry_run': True,
    }
    assert AcademicAPSyncWorkflowService._ap_request_fingerprint(normalized) == AcademicAPSyncWorkflowService._ap_request_fingerprint(dict(reversed(list(normalized.items()))))

    legacy_payload = AcademicAPSyncIn(term_name='Summer 2026', sync_scope='all', branch='poly')
    with pytest.raises(Exception):
        AcademicAPSyncWorkflowService._normalized_ap_request(legacy_payload)
    legacy_normalized = AcademicAPSyncWorkflowService._normalized_ap_request(
        legacy_payload,
        require_explicit_targets=False,
    )
    assert legacy_normalized['campuses'] == []
    ap_source = (ROOT / 'app/services/academic/ap_sync.py').read_text()
    assert 'pg_advisory_xact_lock' in ap_source
    assert '_acquire_enqueue_scope_lock(term_name=term_name, branch=branch)' in ap_source


@pytest.mark.asyncio
async def test_course_blocks_retries_with_canonical_id_and_reduced_fields(monkeypatch):
    from app.core.config import settings
    from app.modules.openedx_connector import real
    from app.modules.openedx_connector.real import RealOpenEdXConnector

    calls = []

    class DummyResponse:
        def __init__(self, status_code, payload):
            self.status_code = status_code
            self._payload = payload
            self.text = str(payload)

        def json(self):
            return self._payload

    class DummyClient:
        def __init__(self, timeout=None):
            self.timeout = timeout

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def get(self, url, params=None, headers=None):
            calls.append({'url': url, 'params': list(params or []), 'headers': headers})
            if len(calls) == 1:
                return DummyResponse(400, {'detail': 'requested_fields not supported by this deployment'})
            return DummyResponse(200, {
                'blocks': {
                    'block-v1:FPT+COM1071+SU26+type@chapter+block@bai-1': {
                        'type': 'chapter',
                        'display_name': 'Bài 1',
                        'children': [],
                    }
                }
            })

    monkeypatch.setattr(real.httpx, 'AsyncClient', DummyClient)
    monkeypatch.setattr(settings, 'openedx_prefer_studio_content', False)
    connector = RealOpenEdXConnector()
    connector.lms_base_url = 'http://lms.example.edu'

    async def fake_headers(*args, **kwargs):
        return {'Accept': 'application/json'}

    monkeypatch.setattr(connector, '_headers', fake_headers)
    blocks = await connector.get_course_blocks('course-v1:FPT+COM1071+SU26/')

    assert len(calls) == 2
    assert ('course_id', 'course-v1:FPT+COM1071+SU26') in calls[0]['params']
    assert not any(key == 'student_view_data' for key, _ in calls[1]['params'])
    assert blocks[0]['type'] == 'chapter'
    assert blocks[0]['display_name'] == 'Bài 1'


@pytest.mark.asyncio
async def test_quiz_creation_compensates_partial_openedx_creation(monkeypatch):
    from app.models.question_bank import (
        EdxCourseChapterMapping,
        EdxCourseMapping,
        QuestionBankRelease,
        Subject,
        SubjectChapter,
    )
    from app.services.question_bank import quiz_creation
    from app.services.question_bank.quiz_creation import QuestionBankQuizCreationWorkflowService

    chapter_mapping = SimpleNamespace(
        id='chapter-map-1',
        course_mapping_id='course-map-1',
        bank_release_id='release-1',
        openedx_parent_node_id='block-v1:FPT+COM1071+SU26+type@chapter+block@bai-1',
        subject_chapter_id='chapter-1',
    )
    course_mapping = SimpleNamespace(
        id='course-map-1',
        openedx_course_id='course-v1:FPT+COM1071+SU26/',
        updated_at=None,
    )
    release = SimpleNamespace(
        id='release-1',
        status='published',
        subject_id='subject-1',
        chapter_id='chapter-1',
        subject_offering_id='offering-1',
        release_code='COM1071-SU26-bai-1-v1.0',
        openedx_library_key='lib:FPT:com1071-su26-bai-1-v1-0',
    )
    subject = SimpleNamespace(id='subject-1', code='COM1071')
    chapter = SimpleNamespace(id='chapter-1', title='Bài 1', chapter_no='1')

    class FakeDB:
        def __init__(self):
            self.added = []
            self.commits = 0

        def get(self, model, key):
            return {
                (EdxCourseChapterMapping, 'chapter-map-1'): chapter_mapping,
                (EdxCourseMapping, 'course-map-1'): course_mapping,
                (QuestionBankRelease, 'release-1'): release,
                (Subject, 'subject-1'): subject,
                (SubjectChapter, 'chapter-1'): chapter,
            }.get((model, key))

        def add(self, item):
            self.added.append(item)

        def commit(self):
            self.commits += 1

    class FakeParentService:
        def __init__(self):
            self.db = FakeDB()

        def _chapter_mapping_validation(self, **kwargs):
            return {'checks': [], 'ok': True}

        def _build_release_quiz_plan(self, **kwargs):
            return {'slots': [{'slot_no': 1, 'library_key': release.openedx_library_key, 'openedx_problem_ids': ['p1']}], 'total_questions': 1}

        @staticmethod
        def _chapter_quiz_suffix(_chapter):
            return '1'

    calls = {'delete': []}

    class FakeConnector:
        async def create_quiz_node(self, **kwargs):
            return {
                'ok': True,
                'created_nodes': [
                    {'usage_key': 'block-v1:FPT+COM1071+SU26+type@sequential+block@quiz-1', 'block_type': 'sequential'},
                    {'usage_key': 'block-v1:FPT+COM1071+SU26+type@vertical+block@quiz-1-unit', 'block_type': 'vertical'},
                ],
                'leaf_unit_node_id': 'block-v1:FPT+COM1071+SU26+type@vertical+block@quiz-1-unit',
            }

        async def upsert_quiz_timer_config(self, **kwargs):
            return {'ok': True}

        async def insert_problem_banks(self, **kwargs):
            raise RuntimeError('simulated itembank failure')

        async def delete_quiz_node(self, **kwargs):
            calls['delete'].append(kwargs)
            return {'ok': True, 'deleted': True}

    monkeypatch.setattr(quiz_creation, 'get_openedx_connector', lambda: FakeConnector())
    workflow = QuestionBankQuizCreationWorkflowService(FakeParentService())
    monkeypatch.setattr(workflow, '_build_release_quiz_plan', FakeParentService()._build_release_quiz_plan)

    with pytest.raises(RuntimeError, match='simulated itembank failure'):
        await workflow.create_quiz_from_release(
            course_chapter_mapping_id='chapter-map-1',
            quiz_title='Quiz 1',
            expected_bank_release_id='release-1',
        )

    assert course_mapping.openedx_course_id == 'course-v1:FPT+COM1071+SU26'
    assert calls['delete'][0]['course_id'] == 'course-v1:FPT+COM1071+SU26'
    instance = next(item for item in workflow.db.added if item.__class__.__name__ == 'CourseQuizInstance')
    assert instance.status == 'failed'
    assert instance.metadata_json['manual_cleanup_required'] is False
    assert instance.metadata_json['course_chapter_mapping_id'] == 'chapter-map-1'


def test_release_and_worker_sources_keep_frozen_and_failure_guards():
    release_source = (ROOT / 'app/services/question_bank/release_publish.py').read_text()
    worker_source = (ROOT / 'app/worker.py').read_text()
    academic_route = (ROOT / 'app/api/routes/academic.py').read_text()

    assert '_load_frozen_release_snapshot' in release_source
    assert 'membership_sha256' in release_source
    assert "item.status not in {'approved', 'published'}" in release_source
    assert 'compensating_rollback_result' in (ROOT / 'app/services/question_bank/quiz_creation.py').read_text()
    assert worker_source.count("if not result.get('ok'):") >= 2
    assert 'AP_SYNC_REQUEST_INTEGRITY_FAILED' in worker_source
    assert 'ACADEMIC_CAMPUS_IDENTITY_IN_USE' in academic_route
    assert 'def _require_academic_catalog_admin' in academic_route
    for marker in (
        "@router.post('/campuses'",
        "@router.patch('/campuses/{campus_id}'",
        "@router.post('/campuses/sync-from-ap'",
        "@router.post('/sync/ap/jobs'",
    ):
        section = academic_route[academic_route.index(marker):]
        assert 'Depends(_require_academic_catalog_admin)' in section.split('):', 1)[0]
    app_shell_source = (ROOT.parent / 'frontend/components/layout/AppShell.tsx').read_text()
    assert "href: '/ap-sync'" in app_shell_source and "permission: 'manage_settings'" in app_shell_source
    assert "href: '/premises'" in app_shell_source and "permission: 'manage_settings'" in app_shell_source
    course_routes = (ROOT / 'app/api/routes/courses.py').read_text()
    assert course_routes.index('normalize_openedx_course_id(payload.course_id, required=True)') < course_routes.index('ensure_course_access(user, course_id)')
    bank_routes = (ROOT / 'app/api/routes/question_bank_v2.py').read_text()
    assert 'CourseQuizInstance.openedx_course_id.in_(course_id_candidates)' in bank_routes


@pytest.mark.asyncio
async def test_quiz_preview_reports_one_course_tree_blocker_not_one_per_chapter(monkeypatch):
    from app.models.question_bank import Department, EdxCourseChapterMapping, EdxCourseMapping, Subject, SubjectChapter
    from app.services.question_bank.quiz_creation import QuestionBankQuizCreationWorkflowService

    subject = SimpleNamespace(id='subject-1', code='COM1071', name='Tin học 1', department_id='department-1')
    department = SimpleNamespace(id='department-1', name='Công nghệ thông tin')
    offering = SimpleNamespace(id='offering-1', code='COM1071_SU26', name='Summer 2026', term='SU26', version_code='v1', status='active')
    chapters = [
        SimpleNamespace(id='chapter-1', title='Bài 1', chapter_no='1', sort_order=1, status='active'),
        SimpleNamespace(id='chapter-2', title='Bài 2', chapter_no='2', sort_order=2, status='active'),
    ]

    class FakeQuery:
        def __init__(self, model):
            self.model = model

        def filter(self, *args, **kwargs):
            return self

        def order_by(self, *args, **kwargs):
            return self

        def first(self):
            if self.model is Subject:
                return subject
            if self.model is EdxCourseMapping:
                return None
            return None

        def all(self):
            if self.model is Subject:
                return [subject]
            if self.model is SubjectChapter:
                return chapters
            if self.model is EdxCourseChapterMapping:
                return []
            return []

    class FakeDB:
        def query(self, model):
            return FakeQuery(model)

        def get(self, model, key):
            return department if model is Department and key == department.id else None

    class FakeParent:
        def __init__(self):
            self.db = FakeDB()

        @staticmethod
        def _chapter_display_name(chapter):
            return chapter.title

        @staticmethod
        def _quiz_action_for_chapter_title(_title):
            return 'quiz'

        @staticmethod
        def _quiz_action_requires_release(action):
            return action in {'quiz', 'final_test'}

        @staticmethod
        def _quiz_action_label(action):
            return 'Tạo Final test' if action == 'final_test' else 'Tạo Quiz'

        @staticmethod
        def _chapter_quiz_suffix(chapter):
            return str(chapter.chapter_no)

        @staticmethod
        def _quiz_production_status_for_mapping(*, action, section, release_info):
            missing = []
            if action in {'quiz', 'final_test'} and not section:
                missing.append('SECTION')
            if action in {'quiz', 'final_test'} and not release_info.get('ready'):
                missing.append('RELEASE')
            return {
                'production_ready': not missing,
                'status_code': 'ready' if not missing else 'blocked',
                'status_label': 'Sẵn sàng' if not missing else 'Thiếu điều kiện',
                'severity': 'success' if not missing else 'warning',
                'missing_requirements': missing,
                'recommended_action': None,
            }

    workflow = QuestionBankQuizCreationWorkflowService(FakeParent())
    monkeypatch.setattr(workflow, '_select_offering_for_course', lambda **kwargs: (offering, [], []))
    monkeypatch.setattr(workflow, '_offering_published_release_status', lambda _offering: {
        'all_ready': True,
        'chapter_count': 2,
        'ready_chapter_count': 2,
        'details': [
            {'chapter_id': 'chapter-1', 'ready': True, 'release_id': 'release-1', 'release_code': 'r1', 'openedx_library_key': 'lib:FPT:r1'},
            {'chapter_id': 'chapter-2', 'ready': True, 'release_id': 'release-2', 'release_code': 'r2', 'openedx_library_key': 'lib:FPT:r2'},
        ],
    })

    async def unavailable(_course_id):
        return [], ['Open edX trả HTTP 400 khi đọc cây course.'], {
            'source': 'unavailable',
            'course_id': 'course-v1:FPT+COM1071+SU26',
            'error_code': 'OPENEDX_COURSE_TREE_HTTP_400',
            'direct_error': 'Open edX trả HTTP 400 khi đọc cây course.',
            'cached_block_count': 0,
        }

    monkeypatch.setattr(workflow, '_load_openedx_sections_for_quiz_detailed', unavailable)
    result = await workflow.preview_quiz_auto_map(openedx_course_id='course-v1:FPT+COM1071+SU26/')

    assert result['ok'] is False
    assert result['course_tree']['error_code'] == 'OPENEDX_COURSE_TREE_HTTP_400'
    assert len(result['blocking_errors']) == 1
    assert 'Không đọc được cây Course CMS/Open edX' in result['blocking_errors'][0]
    assert not any('chưa tìm thấy Section cùng tên' in item for item in result['blocking_errors'])
    assert all('COURSE_TREE' in item['missing_requirements'] for item in result['mappings'])
    assert all('SECTION' not in item['missing_requirements'] for item in result['mappings'])
    assert all(item['status_code'] == 'COURSE_TREE_UNAVAILABLE' for item in result['mappings'])


def test_release_snapshot_is_frozen_and_rejects_invalid_membership():
    from app.models.question import Question
    from app.models.question_bank import BankReleaseQuestion
    from app.services.question_bank.release_publish import QuestionBankReleasePublishWorkflowService

    rows = [
        SimpleNamespace(id='row-1', question_id='q1'),
        SimpleNamespace(id='row-2', question_id='q2'),
    ]
    questions = [
        SimpleNamespace(id='q1', status='approved', is_retired=False, is_duplicate=False),
        SimpleNamespace(id='q2', status='published', is_retired=False, is_duplicate=False),
    ]

    class FakeQuery:
        def __init__(self, model):
            self.model = model

        def filter(self, *args, **kwargs):
            return self

        def order_by(self, *args, **kwargs):
            return self

        def all(self):
            if self.model is BankReleaseQuestion:
                return rows
            if self.model is Question:
                return questions
            return []

    class FakeDB:
        def query(self, model):
            return FakeQuery(model)

    workflow = QuestionBankReleasePublishWorkflowService(SimpleNamespace(db=FakeDB()))
    membership_hash = workflow._release_membership_hash(['q1', 'q2'])
    release = SimpleNamespace(id='release-1', metadata_json={'membership_sha256': membership_hash})

    loaded_rows, loaded_questions = workflow._load_frozen_release_snapshot(release)
    assert [item.question_id for item in loaded_rows] == ['q1', 'q2']
    assert [item.id for item in loaded_questions] == ['q1', 'q2']

    questions[1].status = 'rejected'
    with pytest.raises(ValueError, match='không còn hợp lệ'):
        workflow._load_frozen_release_snapshot(release)


@pytest.mark.asyncio
async def test_all_real_connector_mutations_canonicalize_course_id(monkeypatch):
    from app.modules.openedx_connector import real
    from app.modules.openedx_connector.real import RealOpenEdXConnector

    requests = []

    class DummyResponse:
        status_code = 200
        text = '{}'

        @staticmethod
        def json():
            return {'ok': True, 'deleted': True}

    class DummyClient:
        def __init__(self, timeout=None):
            self.timeout = timeout

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def post(self, url, content=None, headers=None):
            requests.append((url, content.decode('utf-8') if isinstance(content, bytes) else str(content)))
            return DummyResponse()

    monkeypatch.setattr(real.httpx, 'AsyncClient', DummyClient)
    connector = RealOpenEdXConnector()
    connector.cms_base_url = 'http://studio.example.edu'
    connector.lms_base_url = 'http://lms.example.edu'

    async def fake_headers(*args, **kwargs):
        return {'Content-Type': 'application/json'}

    monkeypatch.setattr(connector, '_json_request_headers', fake_headers)
    legacy = 'course-v1:FPT+COM1071+SU26/'
    canonical = 'course-v1:FPT+COM1071+SU26'

    await connector.create_quiz_node(legacy, 'block-v1:FPT+COM1071+SU26+type@chapter+block@bai-1', 'Quiz 1', 'Quiz')
    await connector.delete_quiz_node(legacy, 'block-v1:FPT+COM1071+SU26+type@sequential+block@quiz-1')
    await connector.insert_problem_banks(legacy, 'block-v1:FPT+COM1071+SU26+type@vertical+block@quiz-1', [])

    assert len(requests) == 3
    assert all(canonical in body for _url, body in requests)
    assert all(f'{canonical}/' not in body for _url, body in requests)
