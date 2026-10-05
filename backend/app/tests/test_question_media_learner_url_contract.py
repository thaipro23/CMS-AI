from pathlib import Path


def _connector_source() -> str:
    root = Path(__file__).resolve().parents[3]
    return (root / 'openedx-connector-plugin' / 'openedx_ai_connector' / 'studio.py').read_text()


def test_question_media_is_authored_as_static_reference_not_studio_asset_url():
    source = _connector_source()

    assert "path = f'static/{path}'" in source
    assert "learner_url = _question_media_learner_ref(static_path)" in source
    assert "final_olx = final_olx.replace(asset['placeholder'], learner_url)" in source

    # static_file.url is useful for diagnostics only. It is a Studio authoring
    # endpoint protected by Content Library permissions and must never be saved
    # into learner-facing OLX.
    assert "studio_url = str(getattr(static_file, 'url', '') or '').strip()" in source
    assert "final_olx = final_olx.replace(asset['placeholder'], studio_url)" not in source
    assert "final_olx = final_olx.replace(asset['placeholder'], url)" not in source
    assert "if '/library_assets/component_versions/' in final_olx:" in source


def test_question_media_upload_uses_the_normalized_static_path():
    source = _connector_source()

    assert "static_path = _question_media_static_path(asset['file_path'])" in source
    assert "usage_key,\n            static_path,\n            asset['content']" in source
    assert "'file_path': static_path" in source
    assert "'url': learner_url" in source


def test_existing_itembank_child_is_resynced_through_studio_core():
    source = _connector_source()

    assert "mode': 'native_sync_library_content_existing_child'" in source
    assert "notices = sync_library_content(existing, publish_request, store)" in source
    assert "import_static_assets_for_library_sync()" in source
