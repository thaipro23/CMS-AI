from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]


def test_class_detail_actions_are_equal_width_without_forcing_vertical_toolbar():
    css = (ROOT / 'frontend/app/globals.css').read_text()
    assert 'v25.9.16.7.2.33 — class-detail actions are equal-size but not forced into one vertical column' in css
    assert '.class-detail-flow .class-action-row.compact-sync-action-strip .toolbar-actions' in css
    assert 'flex-direction: row !important' in css
    assert 'flex: 0 0 174px' in css
    assert 'grid-template-columns: repeat(2, minmax(0, 1fr))' in css


def test_learning_behavior_rows_use_class_roster_fallback_when_snapshots_missing():
    source = (ROOT / 'backend/app/services/learning_analytics/analytics_core_service.py').read_text()
    assert 'def _class_student_roster(' in source
    assert 'must never show "0 sinh viên" just because the' in source
    assert "'classification': 'INSUFFICIENT_DATA'" in source
    assert "'reason_codes': ['NO_BEHAVIOR_SNAPSHOT']" in source
    assert "'HAS_LEARNING_ACTIVITY'" in source
    assert "'roster_fallback': class_id is not None" in source


def test_learning_behavior_summary_counts_missing_snapshot_roster_as_insufficient_data():
    source = (ROOT / 'backend/app/services/learning_analytics/analytics_core_service.py').read_text()
    assert 'missing_roster_count = len([item for item in roster' in source
    assert "counts['INSUFFICIENT_DATA'] += missing_roster_count" in source
    assert "'missing_snapshot_count': missing_roster_count" in source
    assert "data_status = 'ready' if snapshot_count >= student_count" in source


def test_analytics_table_can_show_student_name_and_code_from_fallback_row():
    page = (ROOT / 'frontend/app/analytics/learning/page.tsx').read_text()
    types = (ROOT / 'frontend/types/index.ts').read_text()
    assert 'student_code?: string | null' in types
    assert 'full_name?: string | null' in types
    assert '{row.student_code || row.username}' in page
    assert '{row.full_name || row.username}' in page
