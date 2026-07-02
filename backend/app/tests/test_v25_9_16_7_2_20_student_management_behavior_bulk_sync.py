from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
STUDENT_PAGE = ROOT / 'frontend/app/student-management/page.tsx'
CLASS_DETAIL = ROOT / 'frontend/app/student-management/classes/[classId]/page.tsx'
API = ROOT / 'frontend/lib/api.ts'
TYPES = ROOT / 'frontend/types/index.ts'
ROUTE = ROOT / 'backend/app/api/routes/academic.py'
SCHEMAS = ROOT / 'backend/app/schemas/academic.py'
SERVICE = ROOT / 'backend/app/services/academic_service.py'


def test_student_class_detail_has_direct_learning_behavior_button():
    text = CLASS_DETAIL.read_text(encoding='utf-8')
    assert "const behaviorHref = `/analytics/learning?${behaviorParams.toString()}`" in text
    assert "behaviorParams.set('subject_id', subjectIdForBack)" in text
    assert "behaviorParams.set('class_id', classId)" in text
    assert 'Hành vi học' in text


def test_student_management_has_auto_map_all_button_and_api_call():
    text = STUDENT_PAGE.read_text(encoding='utf-8')
    assert 'autoMapAllAcademicSubjectCoursesAndSync' in text
    assert 'runAutoMapAllAndSync' in text
    assert 'Auto map tất cả' in text
    assert 'syncLearning: true' in text
    assert 'maxClasses: 3000' in text


def test_frontend_api_exposes_bulk_auto_map_sync_endpoint():
    api = API.read_text(encoding='utf-8')
    types = TYPES.read_text(encoding='utf-8')
    assert 'AcademicSubjectAutoMapAllSyncResult' in types
    assert 'autoMapAllAcademicSubjectCoursesAndSync' in api
    assert '/academic/subjects/course-mapping/auto-all-sync/jobs' in api
    assert 'sync_learning: payload.syncLearning !== false' in api
    assert 'max_classes' in api


def test_backend_bulk_auto_map_sync_is_best_effort_and_queues_full_cms_jobs():
    route = ROUTE.read_text(encoding='utf-8')
    service = SERVICE.read_text(encoding='utf-8')
    schemas = SCHEMAS.read_text(encoding='utf-8')
    assert 'class AcademicSubjectAutoMapAllSyncIn' in schemas
    assert 'class AcademicSubjectAutoMapAllSyncOut' in schemas
    assert "@router.post('/subjects/course-mapping/auto-all-sync/jobs'" in route
    assert "job_type='full_cms_sync'" in route
    assert 'auto_map_course=True' in route
    assert 'sync_learning=payload.sync_learning' in route
    assert 'auto_map_subject_courses_for_filter' in service
    assert 'page_size=200' in service
    assert 'class_ids' in service
