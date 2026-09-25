from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding='utf-8')


def test_jobs_loads_visible_creator_labels_once_and_keeps_fallbacks():
    page = read('frontend/app/jobs/page.tsx')
    assert 'getUserIdentityLabels' in page
    assert 'creatorLabels' in page
    assert 'requester_context' in page
    assert 'Người dùng #' in page
    assert 'Hệ thống' in page
    assert 'requestedByLabel(' in page


def test_identity_label_api_is_wired_and_bounded():
    api = read('frontend/lib/api.ts')
    types = read('frontend/types/index.ts')
    users = read('backend/app/api/routes/users.py')
    assert '/users/labels' in api
    assert 'UserIdentityLabel' in types
    assert "@router.get('/labels')" in users
    assert "require_permission('view_jobs')" in users
    assert 'len(keys) > 200' in users
