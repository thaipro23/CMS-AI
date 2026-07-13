from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
VERSION = '25.9.16.7.2.64.13'
TITLE = 'Bank Release Publish Reliability + Rollback QA'


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding='utf-8')


def test_v37_version_and_docs_are_current():
    assert f"app_version: str = '{VERSION}'" in read('backend/app/core/config.py')
    assert f'"version": "{VERSION}"' in read('frontend/package.json')
    assert f'NEXT_PUBLIC_APP_VERSION: ${{APP_VERSION:-{VERSION}}}' in read('docker-compose.prod.yml')
    assert f"process.env.NEXT_PUBLIC_APP_VERSION || '{VERSION}'" in read('frontend/components/layout/AppShell.tsx')
    assert f'APP_VERSION={VERSION}' in read('.env.example')
    assert f'APP_VERSION={VERSION}' in read('.env.production.example')
    assert f'# AI Server Open edX — v{VERSION}' in read('README.md')
    assert f'# v{VERSION} — {TITLE}' in read('RUN_CURRENT.md')
    assert f'# v{VERSION} — {TITLE}' in read('RUN_V25_9_16_7_2_53.md')


def test_v37_backend_class_result_doctor_contract_and_safe_recalculate_route():
    route = read('backend/app/api/routes/learning_analytics.py')
    service = read('backend/app/services/learning_analytics/analytics_core_service.py')
    assert "@router.get('/classes/{class_id}/doctor')" in route
    assert "@router.post('/classes/{class_id}/doctor/recalculate'" in route
    assert 'class AnalyticsClassRecalculateRequest(BaseModel)' in route
    assert 'requested_course_id = payload.course_id or course_id' in route
    assert 'requested_force = bool(payload.force or force)' in route
    assert 'def class_result_doctor' in service
    assert "'data_gap': data_gap" in service
    assert "'roster_count': roster_count" in service
    assert "'tracking_event_count': tracking_event_count" in service
    assert "'video_progress_count': video_progress_count" in service
    assert "'session_progress_count': session_progress_count" in service
    assert "'can_enqueue': can_enqueue" in service
    assert 'AMBIGUOUS_COURSE_MAPPING' in service
    assert 'NO_COURSE_MAPPING' in service
    assert 'HAS_ACTIVITY_NO_SNAPSHOT' in service
    assert 'NO_TRACKING_EVENTS' in service


def test_v37_behavior_summary_rows_return_diagnostics_and_roster_identity():
    service = read('backend/app/services/learning_analytics/analytics_core_service.py')
    types = read('frontend/types/index.ts')
    assert "'diagnostics': diagnostics" in service
    assert "student_identity = roster_identity.get" in service
    assert "'student_code': student_identity.get('student_code')" in service
    assert "'full_name': student_identity.get('full_name')" in service
    assert 'export type AnalyticsClassResultDoctor' in types
    assert 'diagnostics?: AnalyticsClassResultDoctor | null' in types
    assert 'roster_fallback?: boolean' in types


def test_v37_frontend_has_data_status_panel_and_manual_safe_actions():
    page = read('frontend/app/analytics/learning/page.tsx')
    api = read('frontend/lib/api.ts')
    css = read('frontend/app/globals.css')
    assert 'getAnalyticsClassResultDoctor' in api
    assert 'enqueueAnalyticsClassDoctorRecalculate' in api
    assert 'Trạng thái dữ liệu lớp' in page
    assert 'Kiểm tra dữ liệu lớp' in page
    assert 'Tính lại lớp này' in page
    assert 'classDoctor?.roster_count' in page
    assert 'classDoctor?.tracking_event_count' in page
    assert 'classDoctor?.video_progress_count' in page
    assert 'classDoctor?.session_progress_count' in page
    assert 'v25.9.16.7.2.64.13 — bank table production ux' in css


def test_v37_changelog_order_and_no_migration():
    changelog = read('CHANGELOG.md')
    assert changelog.startswith(f'## v{VERSION} — {TITLE}')
    assert changelog.index(f'## v{VERSION} — {TITLE}') < changelog.index('## v25.9.16.7.2.36 — Responsive Sidebar Shell Fix + Analytics Orchestrator QA')
    assert '- No migration.' in changelog.split('## v25.9.16.7.2.36', 1)[0]
