from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]


def test_cms_callback_verifies_rbac_before_redirecting_to_requested_page():
    source = (ROOT / 'frontend/app/auth/cms-callback/page.tsx').read_text(encoding='utf-8')

    apply_index = source.index('applyAuthSession(session)')
    refresh_index = source.index('await refreshAuthSession(session.access_token)')
    redirect_index = source.index('router.replace(target)')

    assert apply_index < refresh_index < redirect_index
    assert 'if (!sessionReady)' in source


def test_app_context_ignores_stale_anonymous_rbac_response():
    source = (ROOT / 'frontend/context/AppContext.tsx').read_text(encoding='utf-8')

    assert 'authRequestSequenceRef' in source
    assert 'sequence !== authRequestSequenceRef.current' in source
    assert 'skipAuthExpiredEvent: true' in source
    assert "cache: 'no-store'" in source
    assert 'refreshAuthSession,' in source
