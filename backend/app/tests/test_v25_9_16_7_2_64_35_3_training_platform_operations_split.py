from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding='utf-8')


def test_sidebar_exposes_four_training_operation_modules():
    shell = read('frontend/components/layout/AppShell.tsx')
    expected = {
        '/student-management/cms': 'Quản lý sinh viên CMS',
        '/teacher-management/cms': 'Quản lý giảng viên CMS',
        '/student-management/udemy': 'Quản lý sinh viên Udemy',
        '/teacher-management/udemy': 'Quản lý giảng viên Udemy',
    }
    for href, label in expected.items():
        assert f"href: '{href}'" in shell
        assert f"label: '{label}'" in shell
    assert "group: 'training'" in shell
    assert "ai-training-platform" in shell


def test_platform_pages_exist_and_legacy_routes_default_to_cms():
    student = read('frontend/app/student-management/StudentManagementPlatformPage.tsx')
    student_route = read('frontend/app/student-management/page.tsx')
    teacher = read('frontend/app/teacher-management/TeacherManagementPlatformPage.tsx')
    teacher_route = read('frontend/app/teacher-management/page.tsx')
    assert 'export function StudentManagementPlatformPage' in student
    assert '<StudentManagementPlatformPage platform="cms" />' in student_route
    assert 'export function TeacherManagementPlatformPage' in teacher
    assert '<TeacherManagementPlatformPage platform="cms" />' in teacher_route
    route_contracts = [
        ('frontend/app/student-management/cms/page.tsx', 'platform="cms"', 'from "../StudentManagementPlatformPage"'),
        ('frontend/app/student-management/udemy/page.tsx', 'platform="udemy"', 'from "../StudentManagementPlatformPage"'),
        ('frontend/app/teacher-management/cms/page.tsx', 'platform="cms"', 'from "../TeacherManagementPlatformPage"'),
        ('frontend/app/teacher-management/udemy/page.tsx', 'platform="udemy"', 'from "../TeacherManagementPlatformPage"'),
    ]
    for path, component, shared_import in route_contracts:
        content = read(path)
        assert component in content
        assert shared_import in content
        assert "from '../page'" not in content
        assert 'from "../page"' not in content


def test_api_propagates_learning_platform_across_subject_class_teacher_and_export_flows():
    api = read('frontend/lib/api.ts')
    routes = read('backend/app/api/routes/academic.py')
    worker = read('backend/app/worker.py')
    assert api.count("params.set(\"learning_platform\", filters.learningPlatform)") >= 5
    assert routes.count("pattern='^(cms|udemy)$'") >= 5
    assert 'learning_platform=learning_platform' in routes
    direct_export = routes[routes.index("@router.get('/training/teachers/export')"):routes.index("@router.get('/terms'")]
    assert 'learning_platform=learning_platform' in direct_export
    assert "learning_platform=request.get('learning_platform')" in worker


def test_backend_filters_actual_class_deliveries_but_keeps_block_scope():
    service = read('backend/app/services/academic_service.py')
    teacher_report = read('backend/app/services/academic/teacher_report.py')
    assert "AcademicSubjectDelivery.block_id == AcademicClass.block_id" in service
    assert "AcademicSubjectDelivery.learning_platform == 'udemy'" in service
    assert service.count("AcademicSubjectDelivery.learning_platform == 'cms'") >= 2
    assert "if block_id:" in service
    assert "AcademicClass.block_id == block_id" in service
    assert "AcademicSubjectDelivery.block_id == AcademicClass.block_id" in teacher_report
    assert "AcademicSubjectDelivery.learning_platform == 'udemy'" in teacher_report


def test_student_management_has_platform_specific_metrics_actions_and_drilldown():
    page = read('frontend/app/student-management/StudentManagementPlatformPage.tsx')
    classes = read('frontend/app/student-management/subjects/[subjectId]/classes/page.tsx')
    detail = read('frontend/app/student-management/classes/[classId]/page.tsx')
    assert 'title={`Quản lý sinh viên ${platformLabel}`}' in page
    assert 'if (!isCms) return;' in page
    assert 'Môn Udemy' in page and 'Course CMS' in page
    assert "learningPlatform: platform" in page
    assert "detailParams.set('platform', platform)" in classes
    assert 'Vẫn chia theo Block' in classes
    assert 'Tiến độ Udemy' in classes and 'Học tập CMS' in classes
    assert "subjectBackParams.set('platform', navigationPlatform)" in detail


def test_teacher_management_has_platform_specific_filters_columns_and_export_jobs():
    page = read('frontend/app/teacher-management/TeacherManagementPlatformPage.tsx')
    classes = read('frontend/app/teacher-management/teachers/[teacherId]/classes/page.tsx')
    assert 'title={`Quản lý giảng viên ${platformLabel}`}' in page
    assert 'learningPlatform: platform' in page
    assert 'String(request.learning_platform || "cms") === platform' in page
    assert 'Có SV Udemy chậm tiến độ' in page
    assert 'Cảnh báo CMS' in page and 'Cảnh báo Udemy' in page
    assert "params.set(\"platform\", platform)" in page
    assert 'learningPlatform: platform' in classes
    assert 'Lớp Udemy' in classes and 'Lớp CMS' in classes


def test_only_subject_management_is_term_level_while_operations_still_offer_block_filter():
    subject_management = read('frontend/app/subject-management/page.tsx')
    student_classes = read('frontend/app/student-management/subjects/[subjectId]/classes/page.tsx')
    service = read('backend/app/services/academic_service.py')
    assert 'Quản lý theo học kỳ' in subject_management or 'theo học kỳ' in subject_management.lower()
    assert '<label className="is-narrow">Block' in student_classes
    assert "blockId," in student_classes
    assert "AcademicClass.block_id == block_id" in service


def test_batch_35_3_does_not_add_database_migration():
    migrations = list((ROOT / 'backend/alembic/versions').glob('*.py'))
    assert any(path.name.startswith('0057_') for path in migrations)
    assert not any(path.name.startswith('0058_') for path in migrations)
