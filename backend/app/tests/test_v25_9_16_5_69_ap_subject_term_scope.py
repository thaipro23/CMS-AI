from app.services import ap_academic_sync


class _FakeResponse:
    def raise_for_status(self):
        return None

    def json(self):
        return {
            'status': 1,
            'code': 200,
            'data': [
                {'course_code': 'ACC106', 'course_name': 'Quản trị tài chính'},
                {'subject_code': 'WEB3023', 'subject_name': 'Thiết kế Web'},
            ],
        }


class _FakeHttpClient:
    last_request = None

    def __init__(self, *args, **kwargs):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def get(self, endpoint, *, headers=None, params=None):
        type(self).last_request = {
            'endpoint': endpoint,
            'headers': headers or {},
            'params': params or {},
        }
        return _FakeResponse()


def _client(monkeypatch):
    monkeypatch.setattr(ap_academic_sync.settings, 'academic_ap_sync_enabled', True)
    monkeypatch.setattr(ap_academic_sync.settings, 'academic_ap_api_base_url', 'https://api_v2.poly.edu.vn')
    monkeypatch.setattr(ap_academic_sync.settings, 'academic_ap_get_course_endpoint', '/get-course')
    monkeypatch.setattr(ap_academic_sync.settings, 'academic_ap_api_key', 'api-secret-123456')
    monkeypatch.setattr(ap_academic_sync.settings, 'academic_ap_get_course_file_cache_enabled', False)
    monkeypatch.setattr(ap_academic_sync.httpx, 'Client', _FakeHttpClient)
    return ap_academic_sync.APAcademicClient()


def test_get_subjects_uses_get_course_poly_term_and_ignores_campus(monkeypatch):
    subjects = _client(monkeypatch).get_subjects(branch='ptcd', term_name='Summer 2026', campus='ps')

    assert [item['subject_code'] for item in subjects] == ['ACC106', 'WEB3023']
    assert subjects[0]['subject_name'] == 'Quản trị tài chính'
    assert subjects[0]['discovery_branch'] == 'poly'
    assert subjects[0]['requested_branch'] == 'ptcd'
    assert subjects[0]['_catalog_source'] == 'ap.get-course'

    request = _FakeHttpClient.last_request
    assert request['endpoint'] == 'https://api_v2.poly.edu.vn/get-course'
    assert request['params'] == {'branch': 'poly', 'term_name': 'Summer 2026'}
    assert 'campus' not in request['headers']
    assert request['headers']['Authorization'] == 'Bearer api-secret-123456'


def test_get_subjects_omits_only_blank_term_name(monkeypatch):
    _client(monkeypatch).get_subjects(branch='poly', term_name='  ', campus='ph')

    assert _FakeHttpClient.last_request['params'] == {'branch': 'poly'}
