from app.services import ap_academic_sync


class _FakeResponse:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self._payload


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
            "endpoint": endpoint,
            "headers": headers or {},
            "params": params or {},
        }
        return _FakeResponse({
            "status": 1,
            "code": 200,
            "data": [
                {"subject_code": "ACC106", "skill_code": "ACC106", "subject_name": "Quản trị tài chính"},
            ],
        })


def _client(monkeypatch):
    monkeypatch.setattr(ap_academic_sync.settings, "academic_ap_sync_enabled", True)
    monkeypatch.setattr(ap_academic_sync.settings, "academic_ap_api_base_url", "https://api_v2.poly.edu.vn")
    monkeypatch.setattr(ap_academic_sync.settings, "academic_ap_cms_api_base_url", "http://apitest.poly.edu.vn")
    monkeypatch.setattr(ap_academic_sync.settings, "academic_ap_api_key", "x" * 16)
    monkeypatch.setattr(ap_academic_sync.settings, "academic_ap_get_course_file_cache_enabled", False)
    monkeypatch.setattr(ap_academic_sync.httpx, "Client", _FakeHttpClient)
    return ap_academic_sync.APAcademicClient()


def test_get_subjects_uses_term_name_not_campus_code(monkeypatch):
    client = _client(monkeypatch)

    subjects = client.get_subjects(branch="poly", term_name="Summer 2026", campus="ph")

    assert subjects[0]["subject_code"] == "ACC106"
    request = _FakeHttpClient.last_request
    assert request["endpoint"].startswith("http://apitest.poly.edu.vn/api/cms/get-subject-cms")
    assert "term_name=Summer+2026" in request["endpoint"]
    assert request["params"] == {}
    assert "campus_code" not in request["endpoint"]
    assert "campus" not in request["headers"]


def test_get_subjects_supports_endpoint_template_with_static_campus_code(monkeypatch):
    monkeypatch.setattr(
        ap_academic_sync.settings,
        "academic_ap_cms_get_subject_endpoint",
        "/api/cms/get-subject-cms?campus_code=ph&term_name=",
    )
    client = _client(monkeypatch)

    subjects = client.get_subjects(branch="poly", term_name="Summer 2026", campus="hn")

    assert subjects[0]["subject_code"] == "ACC106"
    request = _FakeHttpClient.last_request
    assert request["endpoint"].startswith("http://apitest.poly.edu.vn/api/cms/get-subject-cms?")
    assert "campus_code=ph" in request["endpoint"]
    assert "term_name=Summer+2026" in request["endpoint"]
    assert "term_name=&" not in request["endpoint"]
    assert request["endpoint"].count("term_name=") == 1
    assert request["params"] == {}
    assert "campus" not in request["headers"]


def test_get_subjects_supports_endpoint_template_with_blank_term_name_only(monkeypatch):
    monkeypatch.setattr(
        ap_academic_sync.settings,
        "academic_ap_cms_get_subject_endpoint",
        "/api/cms/get-subject-cms?term_name=",
    )
    client = _client(monkeypatch)

    client.get_subjects(branch="poly", term_name="Summer 2026", campus="ph")

    request = _FakeHttpClient.last_request
    assert request["endpoint"].startswith("http://apitest.poly.edu.vn/api/cms/get-subject-cms?")
    assert "term_name=Summer+2026" in request["endpoint"]
    assert request["endpoint"].count("term_name=") == 1
    assert request["params"] == {}
