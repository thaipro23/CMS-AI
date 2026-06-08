from pathlib import Path


def test_native_create_xblock_passes_serialized_parent_locator():
    root = Path(__file__).resolve().parents[3]
    source = (root / 'openedx-connector-plugin' / 'openedx_ai_connector' / 'views.py').read_text()
    assert "parent_locator=_clean_usage_key(getattr(unit_block, 'location', unit_block))" in source
    assert "parent_locator=_clean_usage_key(getattr(bank, 'location', bank))" in source
    assert "parent_locator=getattr(unit_block, 'location', unit_block)" not in source
    assert "parent_locator=getattr(bank, 'location', bank)" not in source
