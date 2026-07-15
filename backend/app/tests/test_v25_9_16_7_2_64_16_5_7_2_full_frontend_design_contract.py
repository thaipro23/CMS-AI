from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from app.schemas.rbac import RoleAssignmentBatchCreate

ROOT = Path(__file__).resolve().parents[3]
VERSION = '25.9.16.7.2.64.16.5.7.2'


def source(path: str) -> str:
    return (ROOT / path).read_text(encoding='utf-8')


def test_release_version_is_current_across_runtime_metadata():
    assert VERSION in source('backend/app/core/config.py')
    assert f'"version": "{VERSION}"' in source('frontend/package.json')
    assert VERSION in source('docker-compose.prod.yml')


def test_sidebar_and_content_breadcrumb_contract_is_closed():
    shell = source('frontend/components/layout/AppShell.tsx')
    breadcrumbs = source('frontend/components/navigation/Breadcrumbs.tsx')
    css = source('frontend/styles/full-frontend-design-contract.css')
    assert "href: '/bank/search'" not in shell
    assert 'return null' in breadcrumbs
    assert '.enterprise-breadcrumbs { display: none !important; }' in css
    assert 'overflow-y: auto;' in css


def test_semester_page_has_single_section_header_and_exact_columns():
    page = source('frontend/app/semesters/page.tsx')
    assert 'OperationsKpiStrip' not in page
    assert 'title="Danh sách học kỳ"' in page
    for heading in ('STT', 'Học kỳ', 'Lịch Block 1', 'Lịch Block 2', 'Trạng thái', 'Thao tác'):
        assert f"header: '{heading}'" in page
    assert 'showSummary={false}' in page


def test_bank_dashboard_and_chapter_use_compact_action_contracts():
    dashboard = source('frontend/app/bank/_components/pages/BankDashboardPage.tsx')
    chapter = source('frontend/app/bank/_components/pages/ChapterWorkspacePage.tsx')
    assert 'dashboard-control-bar' in dashboard
    assert 'dashboard-scope-strip' not in dashboard
    assert 'Đi tới danh sách bộ môn' in dashboard
    assert chapter.count('chapter-inline-stats') <= 1
    assert 'Tạo câu hỏi (còn' in chapter
    assert 'Duyệt câu hỏi (' in chapter


def test_optional_question_columns_remain_user_selectable():
    table = source('frontend/app/bank/_components/BankQuestionEnterpriseTable.tsx')
    assert "key: 'concept', header: 'Concept'" in table
    assert "key: 'source', header: 'Nguồn'" in table
    assert table.count('defaultVisible: false') >= 2


def test_student_pages_use_contextual_actions_and_standard_table():
    subjects = source('frontend/app/student-management/page.tsx')
    detail = source('frontend/app/student-management/classes/[classId]/page.tsx')
    assert 'title="Danh sách môn"' in subjects
    assert 'Tự động ghép Course CMS' in subjects
    assert '<EnterpriseDataTable' in detail
    assert 'student-grade-table' not in detail
    assert 'Quay lại danh sách lớp' in detail


def test_role_assignment_batch_schema_deduplicates_scopes():
    payload = RoleAssignmentBatchCreate(
        user_id='user-1',
        email='user@example.com',
        role_code='subject_owner',
        scope_type='subject',
        scope_ids=[' subject-a ', 'subject-a', 'subject-b'],
    )
    assert payload.role_code == 'SUBJECT_OWNER'
    assert payload.scope_type == 'SUBJECT'
    assert payload.scope_ids == ['subject-a', 'subject-b']


def test_legacy_campus_manager_cannot_be_granted_in_batch():
    with pytest.raises(ValidationError):
        RoleAssignmentBatchCreate(
            user_id='user-1',
            role_code='CAMPUS_MANAGER',
            scope_type='CAMPUS',
            scope_ids=['ph'],
        )


def test_rbac_ui_and_backend_support_atomic_multi_scope_grant():
    users = source('frontend/app/users/page.tsx')
    route = source('backend/app/api/routes/rbac.py')
    service = source('backend/app/services/business_rbac.py')
    assert '<AccessibleDialog' in users
    assert 'selectedScopeIds' in users
    assert "filter((role) => role.code !== 'CAMPUS_MANAGER')" in users
    assert "TEACHER_ASSIGNED: ['CAMPUS', 'SYSTEM']" in users
    assert "@router.post('/assignments/batch'" in route
    assert 'def create_assignments_batch' in service
    assert 'self.db.commit()' in service
    assert 'self.db.rollback()' in service


def test_uat_frontend_image_skips_duplicate_validation_by_default():
    dockerfile = source('frontend/Dockerfile')
    compose = source('docker-compose.prod.yml')
    assert 'ARG FRONTEND_VALIDATE_IN_IMAGE=false' in dockerfile
    assert 'FRONTEND_VALIDATE_IN_IMAGE: ${FRONTEND_VALIDATE_IN_IMAGE:-false}' in compose
    assert 'npm run build' in dockerfile
    assert 'webpackBuildWorker: false' in source('frontend/next.config.js')
