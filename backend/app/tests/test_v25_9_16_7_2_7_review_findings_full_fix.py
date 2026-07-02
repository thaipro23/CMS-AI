from pathlib import Path


def _root() -> Path:
    return Path(__file__).resolve().parents[3]


def test_empty_bank_version_delete_removes_diff_items_before_diffs():
    service = (_root() / 'backend' / 'app' / 'services' / 'question_bank_service.py').read_text(encoding='utf-8')
    method = service.split('def _delete_empty_bank_versions_for_chapter', 1)[1].split('def delete_chapter', 1)[0]
    assert 'diff_ids = [' in method
    assert 'BankVersionDiffItem.diff_id.in_(diff_ids)' in method
    assert method.index('BankVersionDiffItem.diff_id.in_(diff_ids)') < method.index('BankVersionDiff.id.in_(diff_ids)')


def test_ingest_api_uses_pydantic_body_and_configured_tracking_log_only():
    route = (_root() / 'backend' / 'app' / 'api' / 'routes' / 'learning_analytics.py').read_text(encoding='utf-8')
    assert 'class AnalyticsIngestRequest(BaseModel):' in route
    assert '@model_validator(mode=\'after\')' in route
    assert "OPENEDX_TRACKING_LOG_PATH" in route
    assert 'payload: AnalyticsIngestRequest | None = None' in route
    assert 'analytics_ingest_task.delay(payload.file_path, safe_max_lines)' in route
    assert 'file_path: str | None = None,\n    max_lines' not in route


def test_ingest_uses_advisory_lock_and_checkpoint_for_update():
    service = (_root() / 'backend' / 'app' / 'services' / 'learning_analytics' / 'analytics_core_service.py').read_text(encoding='utf-8')
    assert 'ANALYTICS_INGEST_LOCK_ID' in service
    assert 'pg_try_advisory_lock' in service
    assert 'pg_advisory_unlock' in service
    assert '.with_for_update()' in service
    assert "status': 'skipped_locked'" in service


def test_learning_behavior_does_not_mix_other_classes_and_avoids_n_plus_one():
    service = (_root() / 'backend' / 'app' / 'services' / 'learning_analytics' / 'analytics_core_service.py').read_text(encoding='utf-8')
    usernames_method = service.split('def _student_usernames_for_class', 1)[1].split('def _learning_snapshots_by_username', 1)[0]
    assert 'return sorted({str(row[0]) for row in rows if row and row[0]})' in usernames_method
    assert 'video_users =' in usernames_method
    assert usernames_method.index('return sorted({str(row[0]) for row in rows if row and row[0]})') < usernames_method.find('video_users =')
    recalculate = service.split('def recalculate_learning_behavior', 1)[1].split('@staticmethod\n    def _safe_label', 1)[0]
    assert '_events_count_by_username' in recalculate
    assert '_video_progress_by_username' in recalculate
    assert '_session_progress_by_username' in recalculate
    assert 'video_rows = video_q.all()' not in recalculate
    assert 'events_count = self.db.query(AnalyticsTrackingEvent)' not in recalculate
    assert 'snap.display_label = self._safe_label' in recalculate


def test_frontend_review_targets_no_any_and_body_ingest_contract():
    files = [
        _root() / 'frontend' / 'components' / 'ui' / 'CostEstimateSummary.tsx',
        _root() / 'frontend' / 'app' / 'jobs' / 'page.tsx',
        _root() / 'frontend' / 'app' / 'semesters' / 'page.tsx',
    ]
    for path in files:
        source = path.read_text(encoding='utf-8')
        assert 'Record<string, any>' not in source
        assert ': any' not in source
        assert ' as any' not in source
    api = (_root() / 'frontend' / 'lib' / 'api.ts').read_text(encoding='utf-8')
    assert 'enqueueAnalyticsIngestJob' in api
    assert "`${API}/analytics/ingest/jobs`" in api
    assert 'body: JSON.stringify({' in api
    assert 'file_path: payload.filePath?.trim() || null' in api


def test_css_removes_important_and_keeps_accessible_fixed_sidebar_stt():
    css = (_root() / 'frontend' / 'app' / 'globals.css').read_text(encoding='utf-8')
    assert '!important' not in css
    assert 'v25.9.16.7.2.7 — review fix' in css
    assert '.product-shell a:focus-visible' in css
    assert 'position: fixed;' in css
    assert '.responsive-table-wrap .stt-cell' in css
    assert 'position: sticky;' in css
