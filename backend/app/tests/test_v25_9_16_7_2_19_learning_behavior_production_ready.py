from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
PAGE = ROOT / 'frontend/app/analytics/learning/page.tsx'
API = ROOT / 'frontend/lib/api.ts'
ROUTE = ROOT / 'backend/app/api/routes/learning_analytics.py'
SERVICE = ROOT / 'backend/app/services/learning_analytics/analytics_core_service.py'
TEACHER_CLASSES = ROOT / 'frontend/app/teacher-management/teachers/[teacherId]/classes/page.tsx'
SCRIPT = ROOT / 'scripts/learning-behavior-production-verify.sh'


def test_learning_behavior_page_supports_direct_teacher_class_links_and_pagination():
    text = PAGE.read_text(encoding='utf-8')
    assert "useSearchParams" in text
    assert "querySubjectId" in text
    assert "queryClassId" in text
    assert "exactClassId" in text
    assert "CLASS_OVERVIEW_PAGE_SIZE = 200" in text
    assert "classOverviewPage" in text
    assert "Xem lớp" in text
    assert "limit: CLASS_OVERVIEW_PAGE_SIZE" in text
    assert "offset: step === 'classes' ? (classOverviewPage - 1) * CLASS_OVERVIEW_PAGE_SIZE : 0" in text
    assert "CLASS_OVERVIEW_LIMIT = 500" not in text


def test_subject_class_overview_accepts_optional_class_id_for_direct_drilldown():
    route = ROUTE.read_text(encoding='utf-8')
    service = SERVICE.read_text(encoding='utf-8')
    api = API.read_text(encoding='utf-8')
    assert "class_id: str | None = None" in route
    assert "class_id=class_id" in route
    assert "class_id: str | None = None" in service
    assert "AcademicClass.id == class_id" in service
    assert "classId?: string | null" in api
    assert "params.set('class_id', filters.classId.trim())" in api
    assert "filters.limit || 200" in api


def test_teacher_class_page_links_to_learning_behavior_result_flow():
    text = TEACHER_CLASSES.read_text(encoding='utf-8')
    assert "function learningBehaviorHref" in text
    assert "params.set('subject_id', cls.subject_id)" in text
    assert "params.set('class_id', cls.class_id)" in text
    assert "return `/analytics/learning?${params.toString()}`" in text
    assert "Hành vi học" in text


def test_production_verify_script_guards_against_422_and_policy_wording():
    text = SCRIPT.read_text(encoding='utf-8')
    assert "page_size=200" in text
    assert "limit=200" in text
    assert "CLASS_ID" in text
    assert "signals_only_not_violation" in text
    assert "forbidden wording" in text
