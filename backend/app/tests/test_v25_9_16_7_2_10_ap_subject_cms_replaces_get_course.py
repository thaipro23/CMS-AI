from __future__ import annotations

from app.services import ap_academic_sync


class _FakeResponse:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self._payload


class _FakeHttpClient:
    requests: list[dict] = []

    def __init__(self, *args, **kwargs):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def get(self, url, headers=None, params=None):
        self.__class__.requests.append({"url": url, "headers": headers or {}, "params": params or {}})
        return _FakeResponse({
            "status": 1,
            "code": 200,
            "message": 200,
            "data": [
                {
                    "subject_code": "ACC106",
                    "skill_code": "ACC106",
                    "subject_name": "Quản trị tài chính nhà hàng khách sạn",
                    "subject_name_en": "Hotel & Restaurant Financial Administration",
                },
                {
                    "subject_code": "WEB3023",
                    "skill_code": "WEB302",
                    "subject_name": "Thiết kế Web với HTML5&CSS3",
                    "subject_name_en": "Web design with HTML5&CSS3",
                },
            ],
        })


def _prepare(monkeypatch):
    _FakeHttpClient.requests = []
    monkeypatch.setattr(ap_academic_sync.settings, "academic_ap_sync_enabled", True)
    monkeypatch.setattr(ap_academic_sync.settings, "academic_ap_api_base_url", "https://api_v2.poly.edu.vn")
    monkeypatch.setattr(ap_academic_sync.settings, "academic_ap_cms_api_base_url", "https://apitest.poly.edu.vn")
    monkeypatch.setattr(ap_academic_sync.settings, "academic_ap_cms_get_subject_endpoint", "/api/cms/get-subject-cms")
    monkeypatch.setattr(ap_academic_sync.settings, "academic_ap_api_key", None)
    monkeypatch.setattr(ap_academic_sync.settings, "academic_ap_subject_cms_file_cache_enabled", False)
    monkeypatch.setattr(ap_academic_sync.settings, "academic_ap_get_course_file_cache_enabled", None)
    monkeypatch.setattr(ap_academic_sync.httpx, "Client", _FakeHttpClient)


def test_get_subjects_calls_ap_get_subject_cms_without_old_get_course(monkeypatch):
    _prepare(monkeypatch)
    client = ap_academic_sync.APAcademicClient()

    subjects = client.get_subjects(branch="poly", term_name=None, campus="ph")

    assert [item["subject_code"] for item in subjects] == ["ACC106", "WEB3023"]
    assert subjects[1]["skill_code"] == "WEB302"
    assert subjects[1]["subject_name"] == "Thiết kế Web với HTML5&CSS3"

    request = _FakeHttpClient.requests[0]
    assert request["url"] == "https://apitest.poly.edu.vn/api/cms/get-subject-cms"
    assert "get-course" not in request["url"]
    assert "term_name" not in request["url"]
    assert request["params"] == {}
    assert "campus" not in request["headers"]


def test_get_subjects_adds_term_name_only_when_term_selected(monkeypatch):
    _prepare(monkeypatch)
    client = ap_academic_sync.APAcademicClient()

    client.get_subjects(branch="poly", term_name="Summer 2026", campus="ph")

    request = _FakeHttpClient.requests[0]
    assert request["url"].startswith("https://apitest.poly.edu.vn/api/cms/get-subject-cms?")
    assert "term_name=Summer+2026" in request["url"]
    assert "campus_code" not in request["url"]


def test_subject_cache_prefers_new_setting_but_keeps_deprecated_alias(monkeypatch):
    _prepare(monkeypatch)
    monkeypatch.setattr(ap_academic_sync.settings, "academic_ap_subject_cms_file_cache_enabled", None)
    monkeypatch.setattr(ap_academic_sync.settings, "academic_ap_get_course_file_cache_enabled", False)
    client = ap_academic_sync.APAcademicClient()

    assert client._subject_cache_enabled() is False
