
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding='utf-8')


def test_frontend_reads_business_permissions_from_rbac_me():
    app_context = read('frontend/context/AppContext.tsx')
    assert 'business_permissions?: string[]' in app_context
    assert 'data.business_permissions' in app_context
    assert 'Array.isArray(data.business_permissions)' in app_context


def test_worker_healthcheck_is_fail_closed_not_log_file_based():
    compose = read('docker-compose.prod.yml')
    assert 'celery -A app.worker.celery_app inspect ping' in compose
    assert 'grep -q pong' in compose
    assert 'test -f /tmp/worker-health.log' not in compose


def test_detailed_health_routes_require_auth_permission():
    health = read('backend/app/api/routes/health.py')
    assert "def db_health(user: UserContext = Depends(require_permission('manage_settings')))" in health
    assert "def openedx_connector_config_health(user: UserContext = Depends(require_permission('manage_settings')))" in health
    assert "def analytics_health(user: UserContext = Depends(require_permission('view_jobs')))" in health
    assert "def health():" in health  # lightweight liveness remains public for container healthcheck


def test_bulk_auto_map_worker_freezes_approved_scope_and_rechecks_rbac():
    route = read('backend/app/api/routes/academic.py')
    worker = read('backend/app/worker.py')
    service = read('backend/app/services/academic_service.py')
    assert "'requester_context': _requester_context_json(user)" in route
    assert "request_json['approved_class_ids']" in route
    assert 'dry_run=True' in route
    assert 'approved_class_ids = {' in worker
    assert 'scope_blocked_class_count' in worker
    assert 'service.assert_can_access_class(worker_user, job.class_id)' in worker
    assert 'approved_class_id' in worker
    assert 'dry_run: bool = False' in service


def test_class_sync_enqueue_uses_advisory_lock_and_requester_context():
    route = read('backend/app/api/routes/academic.py')
    worker = read('backend/app/worker.py')
    assert '_advisory_xact_lock_for_key(db, f\'academic-class-sync:{class_id}\')' in route
    assert '_advisory_xact_lock_for_key(db, f\'academic-class-sync:{class_id}\')' in worker
    assert "'approved_class_id': class_id" in route
    assert "'approved_class_id': class_id" in worker
    assert '_worker_user_from_request_json' in worker


def test_analytics_learning_uses_paged_debounced_subject_search():
    page = read('frontend/app/analytics/learning/page.tsx')
    assert 'useDebouncedValue(subjectSearch, 400)' in page
    assert 'SUBJECT_PAGE_SIZE = 50' in page
    assert 'getAcademicTeacherSubjects(headers, { termId, branch, campus, search: debouncedSubjectSearch' in page
    assert 'loadAllSubjects' not in page
    assert 'Trang {subjectPage}' in page
    assert 'Tất cả trạng thái' in page


def test_version_is_synchronized_across_backend_frontend_and_footer():
    config = read('backend/app/core/config.py')
    package = read('frontend/package.json')
    shell = read('frontend/components/layout/AppShell.tsx')
    compose = read('docker-compose.prod.yml')
    assert "app_version: str = '25.9.16.7.2.35'" in config
    assert '"version": "25.9.16.7.2.35"' in package
    assert 'NEXT_PUBLIC_APP_VERSION' in shell
    assert 'NEXT_PUBLIC_APP_VERSION: ${APP_VERSION:-25.9.16.7.2.35}' in compose


def test_user_facing_vietnamese_replaces_auto_map_and_enrollment_in_management_pages():
    student = read('frontend/app/student-management/page.tsx')
    classes = read('frontend/app/student-management/subjects/[subjectId]/classes/page.tsx')
    teacher = read('frontend/app/teacher-management/page.tsx')
    assert 'Tự động ghép Course CMS' in student
    assert 'Ghi danh CMS' in classes
    assert 'Ghi danh CMS' in teacher
    assert 'Auto map tất cả' not in student
    assert 'Enrollment' not in classes
