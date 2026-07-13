from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
VERSION = '25.9.16.7.2.64.12'


def _read(path: str) -> str:
    return (ROOT / path).read_text(encoding='utf-8')


def test_v55_version_sync_and_docs() -> None:
    assert f"app_version: str = '{VERSION}'" in _read('backend/app/core/config.py')
    assert f'"version": "{VERSION}"' in _read('frontend/package.json')
    assert f'ARG NEXT_PUBLIC_APP_VERSION={VERSION}' in _read('frontend/Dockerfile')
    assert _read('CHANGELOG.md').startswith(f'## v{VERSION} — Bank Release Publish Reliability + Rollback QA')
    assert 'Bank Release Publish Reliability + Rollback QA' in _read('README.md')
    assert 'RUN v25.9.16.7.2.64.12' in _read('RUN_V25_9_16_7_2_56.md')
    assert 'Bank Release Publish Reliability + Rollback QA' in _read('docs/RELEASE_v25.9.16.7.2.64.12_BANK_RELEASE_PUBLISH_RELIABILITY_ROLLBACK_QA.md')


def test_v55_mapping_reliability_endpoint_is_read_only() -> None:
    routes = _read('backend/app/api/routes/learning_analytics.py')
    service = _read('backend/app/services/learning_analytics/analytics_core_service.py')
    assert "@router.get('/ops/course-class-mapping')" in routes
    assert 'analytics_course_class_mapping_reliability_report' in routes
    assert "action='analytics.course_class_mapping_reliability.view'" in routes
    assert 'def analytics_course_class_mapping_reliability_report' in service
    assert "'dry_run': True" in service
    assert "'mutation_performed': False" in service
    assert 'Không tạo/sửa/xóa course mapping.' in service
    assert 'analytics_class_recalculate_task.delay' not in service.split('def analytics_course_class_mapping_reliability_report', 1)[1].split('def class_result_doctor', 1)[0]


def test_v55_mapping_statuses_and_orphan_courses_are_explicit() -> None:
    service = _read('backend/app/services/learning_analytics/analytics_core_service.py')
    for token in [
        'NO_ROSTER',
        'NO_COURSE_MAPPING',
        'AMBIGUOUS_MAPPING',
        'MAPPED_NO_EVENTS',
        'MAPPED_HAS_ACTIVITY_NO_SNAPSHOT',
        'PARTIAL_SNAPSHOT',
        'courses_with_events_without_class_mapping',
        'không tự map nếu có nhiều lớp có thể khớp',
    ]:
        assert token in service


def test_v55_frontend_surfaces_mapping_reliability_panel() -> None:
    page = _read('frontend/app/analytics/learning/page.tsx')
    api = _read('frontend/lib/api.ts')
    types = _read('frontend/types/index.ts')
    css = _read('frontend/app/globals.css')
    assert 'getAnalyticsCourseClassMappingReport' in api
    assert 'AnalyticsCourseClassMappingReport' in types
    assert 'Độ tin cậy mapping Course/Lớp' in page
    assert 'mappingReliabilityTone' in page
    assert 'analytics-mapping-reliability-panel' in css


def test_v55_report_script_exports_json_and_markdown() -> None:
    script = _read('scripts/analytics-course-class-mapping-report.sh')
    assert '/analytics/ops/course-class-mapping' in script
    assert 'analytics-course-class-mapping.json' in script
    assert 'COURSE_CLASS_MAPPING_SUMMARY.md' in script
    assert 'curl -fsS' in script
    assert 'POST' not in script and 'DELETE' not in script
