from __future__ import annotations

from pathlib import Path

from app.services import ap_academic_sync


def _client(monkeypatch, tmp_path, endpoint='/get-course'):
    monkeypatch.setattr(ap_academic_sync.settings, 'academic_ap_sync_enabled', True)
    monkeypatch.setattr(ap_academic_sync.settings, 'academic_ap_api_base_url', 'https://api_v2.poly.edu.vn')
    monkeypatch.setattr(ap_academic_sync.settings, 'academic_ap_get_course_endpoint', endpoint)
    monkeypatch.setattr(ap_academic_sync.settings, 'academic_ap_get_course_file_cache_dir', str(tmp_path))
    return ap_academic_sync.APAcademicClient()


def test_get_course_cache_key_changes_when_endpoint_changes(monkeypatch, tmp_path):
    client = _client(monkeypatch, tmp_path)
    first = client._subject_cache_file(branch='poly', term_name='Summer 2026')

    monkeypatch.setattr(ap_academic_sync.settings, 'academic_ap_get_course_endpoint', '/get-course-v2')
    second = client._subject_cache_file(branch='poly', term_name='Summer 2026')

    assert first != second
    assert first.parent == tmp_path
    assert first.name.startswith('ap_get_course_subjects_poly_Summer_2026_')


def test_deployment_examples_use_only_api_v2_get_course():
    root = Path(__file__).resolve().parents[3]
    for name in ('.env.example', '.env.production.example'):
        text = (root / name).read_text(encoding='utf-8')
        assert 'ACADEMIC_AP_API_BASE_URL=https://api_v2.poly.edu.vn' in text
        assert 'ACADEMIC_AP_GET_COURSE_ENDPOINT=/get-course' in text
        assert 'ACADEMIC_AP_CMS_' not in text
        assert 'ACADEMIC_AP_SUBJECT_CMS_' not in text
        assert 'apitest.poly.edu.vn' not in text

    compose = (root / 'docker-compose.prod.yml').read_text(encoding='utf-8')
    assert 'api_v2.poly.edu.vn' in compose
    assert 'apitest.poly.edu.vn' not in compose
