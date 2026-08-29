from pathlib import Path

import pytest
from fastapi import HTTPException

from app.api.routes.academic import seed_academic_campuses_from_env, sync_academic_campuses_from_ap


@pytest.mark.parametrize('endpoint', [seed_academic_campuses_from_env, sync_academic_campuses_from_ap])
def test_legacy_campus_import_endpoints_are_gone_and_manual_only(endpoint):
    with pytest.raises(HTTPException) as raised:
        endpoint(branch='poly', user=None)

    assert raised.value.status_code == 410
    assert raised.value.detail['code'] == 'ACADEMIC_CAMPUS_MANUAL_ONLY'
    assert '/premises' in raised.value.detail['message']


def test_runtime_has_no_ap_campus_import_service():
    root = Path(__file__).resolve().parents[3]
    client_source = (root / 'backend/app/services/ap_academic_sync.py').read_text(encoding='utf-8')
    frontend_source = (root / 'frontend/app/ap-sync/page.tsx').read_text(encoding='utf-8')

    assert 'def get_campuses(' not in client_source
    assert 'def sync_campuses_from_ap(' not in client_source
    assert 'syncAcademicCampusesFromAp' not in frontend_source
    assert 'Thêm cơ sở thủ công' in (root / 'frontend/app/premises/page.tsx').read_text(encoding='utf-8')
