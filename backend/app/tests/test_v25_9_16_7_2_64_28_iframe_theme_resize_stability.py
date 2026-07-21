from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]


def test_learning_mfe_does_not_guess_iframe_theme_from_operating_system():
    source = (ROOT / "frontend-app-learning-patch/src/courseware/course/sequence/unit-reset/UnitResetButton.jsx").read_text(encoding="utf-8")
    assert "themeVariantFromPersistedPreference" in source
    assert "themeVariantFromRenderedSurface" in source
    assert "initial-theme-settle" in source
    assert "prefers-color-scheme: dark" not in source
    assert "if (themeVariant)" in source


def test_iframe_resize_uses_intrinsic_content_not_viewport_dimensions():
    source = (ROOT / "openedx-unit-reset-plugin/openedx_unit_reset/views.py").read_text(encoding="utf-8")
    runtime = source[source.index('js = r"""'):]
    assert "intrinsicContentHeight" in runtime
    assert "Never observe html/body" in runtime
    assert "document.documentElement.scrollHeight" not in runtime
    assert "document.body.scrollHeight" not in runtime
    assert "resizeObserver.observe(document.documentElement)" not in runtime
    assert "resizeObserver.observe(document.body)" not in runtime
    assert "RESIZE_TOLERANCE_PX = 4" in runtime
    assert "window.requestAnimationFrame" in runtime


def test_unit_reset_plugin_version_is_bumped_for_runtime_cache_busting():
    setup = (ROOT / "openedx-unit-reset-plugin/setup.py").read_text(encoding="utf-8")
    assert "version='0.4.14.7'" in setup
