from app.services import ap_academic_sync


class _FakeResponse:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self._payload


class _FakeHttpClient:
    requests = []

    def __init__(self, *args, **kwargs):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def get(self, endpoint, *, headers=None, params=None):
        type(self).requests.append({
            "endpoint": endpoint,
            "headers": headers or {},
            "params": params or {},
        })
        product = (params or {}).get("product")
        return _FakeResponse({
            "status": 1,
            "code": 200,
            "data": [
                {"campus_code": "ph", "campus_name": f"Campus {product}"},
            ],
        })


def _client(monkeypatch):
    _FakeHttpClient.requests = []
    monkeypatch.setattr(ap_academic_sync.settings, "academic_ap_sync_enabled", True)
    monkeypatch.setattr(ap_academic_sync.settings, "academic_ap_api_base_url", "https://api_v2.poly.edu.vn")
    monkeypatch.setattr(ap_academic_sync.settings, "academic_ap_cms_api_base_url", "http://apitest.poly.edu.vn")
    monkeypatch.setattr(ap_academic_sync.settings, "academic_ap_cms_product_poly", "POLY")
    monkeypatch.setattr(ap_academic_sync.settings, "academic_ap_cms_product_ptcd", "POLY9")
    monkeypatch.setattr(ap_academic_sync.settings, "academic_ap_api_key", "x" * 16)
    monkeypatch.setattr(ap_academic_sync.httpx, "Client", _FakeHttpClient)
    return ap_academic_sync.APAcademicClient()


def test_get_campuses_uses_correct_ap_product_mapping(monkeypatch):
    client = _client(monkeypatch)

    poly = client.get_campuses(branch="poly")
    ptcd = client.get_campuses(branch="ptcd")

    assert poly[0]["product"] == "POLY"
    assert ptcd[0]["product"] == "POLY9"
    assert _FakeHttpClient.requests[0]["params"] == {"product": "POLY"}
    assert _FakeHttpClient.requests[1]["params"] == {"product": "POLY9"}
