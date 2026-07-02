from __future__ import annotations

from pathlib import Path

from app.services import ap_academic_sync


class _FakeResponse:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self._payload


class _CampusMapHttpClient:
    requests = []

    def __init__(self, *args, **kwargs):
        pass

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def get(self, endpoint, *, headers=None, params=None):
        self.__class__.requests.append({
            'endpoint': endpoint,
            'headers': headers or {},
            'params': params or {},
        })
        product = (params or {}).get('product')
        if product == 'POLY9':
            return _FakeResponse({
                'status': 1,
                'code': 200,
                'message': 200,
                'data': {
                    'th': 'PTCĐ Hà Nội',
                    'ts': 'PTCĐ Hồ Chí Minh',
                },
            })
        return _FakeResponse({
            'status': 1,
            'code': 200,
            'message': 200,
            'data': {
                'ph': 'CĐ Hà Nội',
                'ps': 'CĐ Hồ Chí Minh',
            },
        })


def _prepare(monkeypatch):
    _CampusMapHttpClient.requests = []
    monkeypatch.setattr(ap_academic_sync.settings, 'academic_ap_sync_enabled', True)
    monkeypatch.setattr(ap_academic_sync.settings, 'academic_ap_api_base_url', 'https://api_v2.poly.edu.vn')
    monkeypatch.setattr(ap_academic_sync.settings, 'academic_ap_cms_api_base_url', 'https://apitest.poly.edu.vn')
    monkeypatch.setattr(ap_academic_sync.settings, 'academic_ap_cms_get_campus_endpoint', '/api/cms/get-campus')
    monkeypatch.setattr(ap_academic_sync.settings, 'academic_ap_cms_product_poly', 'POLY')
    monkeypatch.setattr(ap_academic_sync.settings, 'academic_ap_cms_product_ptcd', 'POLY9')
    monkeypatch.setattr(ap_academic_sync.settings, 'academic_ap_api_key', None)
    monkeypatch.setattr(ap_academic_sync.httpx, 'Client', _CampusMapHttpClient)


def test_ap_get_campus_accepts_current_object_map_payload(monkeypatch):
    _prepare(monkeypatch)
    client = ap_academic_sync.APAcademicClient()

    poly = client.get_campuses(branch='poly')
    ptcd = client.get_campuses(branch='ptcd')

    assert [item['campus_code'] for item in poly] == ['ph', 'ps']
    assert poly[0]['campus_name'] == 'CĐ Hà Nội'
    assert poly[0]['branch'] == 'poly'
    assert poly[0]['product'] == 'POLY'

    assert [item['campus_code'] for item in ptcd] == ['th', 'ts']
    assert ptcd[0]['campus_name'] == 'PTCĐ Hà Nội'
    assert ptcd[0]['branch'] == 'ptcd'
    assert ptcd[0]['product'] == 'POLY9'

    assert _CampusMapHttpClient.requests[0]['params'] == {'product': 'POLY'}
    assert _CampusMapHttpClient.requests[1]['params'] == {'product': 'POLY9'}


def test_all_frontend_tables_with_stt_header_render_stt_cell():
    root = Path(__file__).resolve().parents[3] / 'frontend'
    offenders: list[str] = []
    for path in root.rglob('*.tsx'):
        text = path.read_text(encoding='utf-8', errors='ignore')
        start = 0
        while True:
            table_start = text.find('<table', start)
            if table_start < 0:
                break
            table_end = text.find('</table>', table_start)
            if table_end < 0:
                break
            block = text[table_start:table_end + len('</table>')]
            line_no = text[:table_start].count('\n') + 1
            has_stt_header = '<th>STT' in block or '<th className="stt' in block
            if has_stt_header and 'stt-cell' not in block:
                offenders.append(f'{path.relative_to(root.parent)}:{line_no}')
            start = table_end + len('</table>')

    assert offenders == []
