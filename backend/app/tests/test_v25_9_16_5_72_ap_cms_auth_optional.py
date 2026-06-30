from __future__ import annotations

import pytest

from app.services import ap_academic_sync


class _FakeResponse:
    def __init__(self, payload, status_code: int = 200):
        self._payload = payload
        self.status_code = status_code

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")

    def json(self):
        return self._payload


class _FakeHttpClient:
    requests = []

    def __init__(self, *args, **kwargs):
        pass

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def get(self, url, headers=None, params=None):
        self.__class__.requests.append({"method": "GET", "url": url, "headers": headers or {}, "params": params or {}})
        if "get-campus" in url:
            return _FakeResponse({"status": 1, "code": 200, "data": [{"campus_code": "ph", "campus_name": "FPoly HCM"}]})
        return _FakeResponse({"status": 1, "code": 200, "data": [{"subject_code": "WEB3023", "subject_name": "Thiết kế Web"}]})


def _prepare(monkeypatch):
    _FakeHttpClient.requests = []
    monkeypatch.setattr(ap_academic_sync.settings, "academic_ap_sync_enabled", True)
    monkeypatch.setattr(ap_academic_sync.settings, "academic_ap_api_base_url", "https://api_v2.poly.edu.vn")
    monkeypatch.setattr(ap_academic_sync.settings, "academic_ap_cms_api_base_url", "http://apitest.poly.edu.vn")
    monkeypatch.setattr(ap_academic_sync.settings, "academic_ap_cms_get_campus_endpoint", "/api/cms/get-campus")
    monkeypatch.setattr(ap_academic_sync.settings, "academic_ap_cms_get_subject_endpoint", "/api/cms/get-subject-cms?campus_code=ph&term_name=")
    monkeypatch.setattr(ap_academic_sync.settings, "academic_ap_cms_product_poly", "POLY")
    monkeypatch.setattr(ap_academic_sync.settings, "academic_ap_cms_product_ptcd", "POLY9")
    monkeypatch.setattr(ap_academic_sync.settings, "academic_ap_api_key", None)
    monkeypatch.setattr(ap_academic_sync.settings, "academic_ap_get_course_file_cache_enabled", False)
    monkeypatch.setattr(ap_academic_sync.httpx, "Client", _FakeHttpClient)


def test_cms_campus_and_subject_catalog_do_not_require_legacy_api_key(monkeypatch):
    _prepare(monkeypatch)
    client = ap_academic_sync.APAcademicClient()

    campuses = client.get_campuses(branch="poly")
    subjects = client.get_subjects(branch="poly", term_name="Summer 2026", campus="ph")

    assert campuses[0]["campus_code"] == "ph"
    assert subjects[0]["subject_code"] == "WEB3023"
    assert _FakeHttpClient.requests[0]["params"] == {"product": "POLY"}
    assert "Authorization" not in _FakeHttpClient.requests[0]["headers"]
    assert "Authorization" not in _FakeHttpClient.requests[1]["headers"]
    assert _FakeHttpClient.requests[1]["url"].endswith("/api/cms/get-subject-cms?campus_code=ph&term_name=Summer+2026")


def test_legacy_get_data_cms_still_requires_api_key(monkeypatch):
    _prepare(monkeypatch)
    client = ap_academic_sync.APAcademicClient()

    with pytest.raises(RuntimeError, match="ACADEMIC_AP_API_KEY"):
        client.get_division(campus="ph", term_name="Summer 2026", subject_code="WEB3023")
