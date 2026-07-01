from pathlib import Path


def _root() -> Path:
    return Path(__file__).resolve().parents[3]


def test_connector_contract_version_and_completion_rule_are_locked_in_plugin():
    text = (_root() / 'openedx-connector-plugin' / 'openedx_ai_connector' / 'student_insight.py').read_text(encoding='utf-8')
    assert "CONNECTOR_VERSION = '25.9.16.5.98'" in text
    assert "CONNECTOR_CONTRACT_VERSION = 'learning-sync/v25.9.16.5.98'" in text
    assert "'denominator': 'reachable_sequential_subsections'" in text
    assert "'numerator': 'studentmodule_sequential_position_rows'" in text
    assert "'itembank'" in text
    assert "module_type='sequential'" in text
    assert "'connector_contract_version': CONNECTOR_CONTRACT_VERSION" in text
    assert "'progress_contract': PROGRESS_CONTRACT" in text


def test_backend_contract_guard_is_present_in_learning_sync_hot_path():
    text = (_root() / 'backend' / 'app' / 'services' / 'academic_service.py').read_text(encoding='utf-8')
    assert "CONNECTOR_MIN_CONTRACT_VERSION = 'learning-sync/v25.9.16.5.98'" in text
    assert "CONNECTOR_MIN_RUNTIME_VERSION = '25.9.16.5.98'" in text
    assert 'def _validate_connector_learning_contract' in text
    assert 'Open edX Connector progress_contract không an toàn' in text
    start = text.index('    def sync_class_learning_insight(')
    end = text.index('    def _try_auto_map_course_for_class', start)
    body = text[start:end]
    assert 'self._validate_connector_learning_contract(analytics_payload, course_id=course_id)' in body


def test_upsert_learning_snapshot_preserves_existing_good_progress_when_payload_is_empty():
    text = (_root() / 'backend' / 'app' / 'services' / 'academic_service.py').read_text(encoding='utf-8')
    start = text.index('    def _upsert_learning_snapshot(')
    end = text.index('    def _upsert_enrollment_snapshot', start)
    body = text[start:end]
    assert 'previous_progress_percent' in body
    assert 'snapshot.progress_percent = previous_progress_percent' in body
    assert 'previous_completed_blocks' in body
    assert 'previous_total_blocks' in body
    assert 'previous_preserved' in body


def test_mapping_change_invalidates_learning_snapshots_and_teacher_report_cache():
    text = (_root() / 'backend' / 'app' / 'services' / 'academic_service.py').read_text(encoding='utf-8')
    start = text.index('    def create_or_update_class_course_mapping(')
    end = text.index('    def mapping_summary_for_class', start)
    body = text[start:end]
    assert 'AcademicStudentLearningSnapshot' in body
    assert 'course_mapping_changed' in body
    assert 'course_mapping_deactivated' in body
    assert '_invalidate_teacher_report_cache_for_class' in body


def test_smoke_test_scripts_are_packaged():
    scripts = _root() / 'scripts'
    assert (scripts / 'production-build-verify.sh').read_text(encoding='utf-8').startswith('#!/usr/bin/env bash')
    smoke = (scripts / 'smoke-test-prod.sh').read_text(encoding='utf-8')
    assert '/api/health/build' in smoke
    assert 'CONNECTOR_VERSION' in smoke
