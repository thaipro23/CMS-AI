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


def test_native_itembank_sync_fails_closed_on_core_static_asset_notices():
    source = _connector_source()

    assert "def _require_clean_static_file_notices(" in source
    assert "conflicting_files" in source
    assert "error_files" in source
    assert "_require_clean_static_file_notices(notices, upstream_ref)" in source


def test_core_sync_verifies_persisted_course_asset_bytes():
    source = _connector_source()

    assert "def _verify_core_synced_static_assets(" in source
    assert "build_components_import_path" in source
    assert "course_key.make_asset_key('asset', import_path.replace('/', '_'))" in source
    assert "contentstore().find(asset_key)" in source
    assert "source_md5 = hashlib.md5(bytes(source_data)).hexdigest()" in source
    assert "stored_md5 = hashlib.md5(bytes(stored_data)).hexdigest()" in source
    assert "asset_verification = _verify_core_synced_static_assets(existing, upstream_ref, user)" in source
    assert "asset_verification = _verify_core_synced_static_assets(child, upstream_ref, user)" in source


def test_core_sync_rejects_legacy_or_authoring_urls_in_downstream():
    source = _connector_source()

    assert "'/library_assets/component_versions/'" in source
    assert "'scms.fpl.edu.vn/library_assets/'" in source
    assert "'/static/acms-legacy/'" in source
    assert "Downstream còn reference không hợp lệ sau core sync" in source


def test_question_media_path_is_core_static_acms_and_staging_safe():
    source = _connector_source()

    assert "if not path.startswith('static/acms/'):" in source
    assert "staged_name = f'staged-content-temp/{path}'" in source
    assert "if len(staged_name) > 100:" in source
    assert "path.startswith('static/acms-legacy/')" in source


def test_question_import_uses_core_component_publish_api():
    source = _connector_source()

    assert "publish_component_changes," in source
    assert "publish_component_changes(usage_key, user_id)" in source
    assert "'mode': 'content_libraries.api.blocks.publish_component_changes'" in source
