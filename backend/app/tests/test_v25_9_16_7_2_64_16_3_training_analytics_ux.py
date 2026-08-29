import json
import os
from pathlib import Path

os.environ.setdefault('DATABASE_URL', 'sqlite+pysqlite:///:memory:')

ROOT = Path(__file__).resolve().parents[3]
VERSION = '25.9.16.7.2.64.16.3'


def text(path: str) -> str:
    return (ROOT / path).read_text(encoding='utf-8')


def test_v64_16_3_version_and_database_boundary():
    package = json.loads(text('frontend/package.json'))
    assert f"app_version: str = '{VERSION}'" in text('backend/app/core/config.py')
    assert package['version'] == VERSION
    assert f'APP_VERSION={VERSION}' in text('.env.production.example')
    assert f'NEXT_PUBLIC_APP_VERSION: ${{APP_VERSION:-{VERSION}}}' in text('docker-compose.prod.yml')
    assert f'ARG NEXT_PUBLIC_APP_VERSION={VERSION}' in text('frontend/Dockerfile')
    assert not list((ROOT / 'backend/alembic/versions').glob('0053*.py'))
    assert (ROOT / 'backend/alembic/versions/0052_v25_9_16_7_2_27_learning_behavior_logic_calibration.py').exists()


def test_v64_16_3_shared_training_workspace_contract_is_loaded():
    component = text('frontend/components/training/TrainingWorkspace.tsx')
    css = text('frontend/styles/training-analytics-ux.css')
    layout = text('frontend/app/layout.tsx')
    for token in ('TrainingWorkflowSteps', 'TrainingContextChips', 'TrainingKpiStrip', 'TrainingMappingEmptyState'):
        assert token in component
    assert "import '../styles/training-analytics-ux.css'" in layout
    for token in ('.training-workflow-steps', '.training-kpi-strip', '.training-mapping-empty-state', '.training-compact-filter'):
        assert token in css


def test_v64_16_3_student_subject_classes_use_url_state_and_enterprise_table():
    page = text('frontend/app/student-management/subjects/[subjectId]/classes/page.tsx')
    assert 'useAcademicTableState' in page
    assert '<PageHeader' in page
    assert '<TrainingContextChips' in page
    assert '<TrainingKpiStrip' in page
    assert 'tableId="student-subject-classes"' in page
    assert '<EnterpriseDataTable' in page
    assert '<table' not in page
    assert "key: 'students'" in page and "kind: 'number'" in page
    assert "key: 'learning'" in page and 'defaultVisible: false' in page


def test_v64_16_3_teacher_classes_remove_wide_grade_matrix():
    page = text('frontend/app/teacher-management/teachers/[teacherId]/classes/page.tsx')
    assert '<PageHeader' in page
    assert 'tableId="teacher-classes"' in page
    assert '<EnterpriseDataTable' in page
    assert 'training-class-grade-table' not in page
    assert '<table' not in page
    assert "key: 'assessment'" in page and 'defaultVisible: false' in page
    assert "key: 'eligibility'" in page and 'defaultVisible: false' in page


def test_v64_16_3_analytics_is_three_step_enterprise_workflow():
    page = text('frontend/app/analytics/learning/page.tsx')
    assert '<TrainingWorkflowSteps' in page
    assert 'Chọn môn' in page and 'Chọn lớp' in page and 'Xem kết quả' in page
    for table_id in ('analytics-subjects', 'analytics-classes', 'analytics-results'):
        assert f'tableId="{table_id}"' in page
    assert '<TrainingMappingEmptyState' in page
    assert 'Không kết nối được API phân tích học tập.' in page
    assert '<div className="analytics-stepper"' not in page


def test_v64_16_3_class_detail_is_read_only_for_assignment_and_mapping_aware():
    page = text('frontend/app/student-management/classes/[classId]/page.tsx')
    assert '<PageHeader' in page
    assert '<TrainingKpiStrip' in page
    assert '<TrainingMappingEmptyState' in page
    assert 'Assignment: đọc từ hệ thống ngoài' in page
    assert 'Lưu workflow Assignment' not in page
    assert 'Workflow bảo vệ Assignment' not in page


def test_v64_16_3_training_main_pages_share_compact_kpis():
    student = text('frontend/app/student-management/page.tsx')
    teacher = text('frontend/app/teacher-management/page.tsx')
    assert '<TrainingKpiStrip' in student
    assert '<TrainingKpiStrip' in teacher
    assert 'Thiếu dữ liệu xét thi' in teacher
    assert 'Course CMS' in student


def test_v64_16_3_academic_url_state_includes_block_filter():
    hook = text('frontend/hooks/useAcademicTableState.ts')
    assert 'blockId: string' in hook
    assert "searchParams.get('block_id')" in hook
    assert "['block_id', merged.blockId, '']" in hook


def test_v64_16_3_keeps_business_and_production_boundaries():
    package = text('frontend/package.json').lower()
    assert 'bootstrap' not in package
    assert 'react-bootstrap' not in package
    assignment = text('backend/app/services/academic/assignment_external.py')
    assert 'ASSIGNMENT_SCORE_EXTERNALIZED' in assignment and 'status_code=410' in assignment
    rbac = text('backend/app/services/business_rbac.py')
    for role in ('SYSTEM_ADMIN', 'DEPARTMENT_HEAD', 'SUBJECT_OWNER', 'QUESTION_REVIEWER', 'CAMPUS_OWNER', 'TEACHER_ASSIGNED'):
        assert role in rbac
    runtime = text('frontend/lib/runtime.ts')
    assert 'SHOW_DIAGNOSTICS_UI = !IS_PRODUCTION_UI' in runtime
