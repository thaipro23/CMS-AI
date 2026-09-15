from pathlib import Path
from types import SimpleNamespace

from app.core.privacy import mask_email
from app.schemas.academic import AcademicStudentOut, UdemyProgressStudentOut
from app.schemas.rbac import RoleAssignmentOut
from app.services.academic.progress_email import AcademicProgressEmailService, plain_text_mail_template


def test_mask_email_is_deterministic_and_idempotent():
    assert mask_email('student01@fpt.edu.vn') == 's***1@fpt.edu.vn'
    assert mask_email('s***1@fpt.edu.vn') == 's***1@fpt.edu.vn'
    assert mask_email(None) is None


def test_academic_api_schemas_mask_student_email():
    student = AcademicStudentOut(id='s1', student_code='SV001', username='sv001', email='student01@fpt.edu.vn', full_name='Sinh Vien', active=True)
    assert student.model_dump()['email'] == 's***1@fpt.edu.vn'
    udemy = UdemyProgressStudentOut(
        id='u1', display_name='Sinh Vien', email='student01@fpt.edu.vn', progress_percent=10,
        status='late', status_label='Chậm', match_status='matched_roster', last_import_batch_id='b1',
        source_format='xlsx', last_imported_at='2026-09-15T00:00:00',
    )
    assert udemy.model_dump()['email'] == 's***1@fpt.edu.vn'


def test_progress_reminder_defaults_and_cms_link():
    cls = SimpleNamespace(class_code='GD2101')
    subject = SimpleNamespace(subject_code='COM1091', subject_name='Tin học và ứng dụng AI')
    assert AcademicProgressEmailService._default_subject(cls, subject) == '[CMS Server] Nhắc nhở tiến độ học tập - COM1091 · GD2101'
    body = AcademicProgressEmailService._default_body(cls, subject)
    assert body.startswith('Xin chào {{tên sinh viên}}-{{maHs}},')
    assert 'Deadline Quiz chỉ là mốc' not in body
    rendered = plain_text_mail_template(body)
    assert 'https://edx.cms.fpl.edu.vn/learner-dashboard/' in rendered
    assert '>CMS</a>' in rendered


def test_frontend_known_email_displays_use_mask_helper():
    root = Path(__file__).resolve().parents[3]
    expected = {
        'frontend/app/student-management/classes/[classId]/page.tsx': 'maskEmailForDisplay(student.email)',
        'frontend/app/subject-management/[deliveryId]/udemy/page.tsx': 'maskEmailForDisplay(row.email)',
        'frontend/components/student-management/UdemyClassProgressPanel.tsx': 'maskEmailForDisplay(row.email)',
        'frontend/app/teacher-management/TeacherManagementPlatformPage.tsx': 'maskEmailForDisplay(item.teacher_email)',
        'frontend/app/users/page.tsx': 'maskEmailForDisplay(item.email)',
    }
    for relative, marker in expected.items():
        assert marker in (root / relative).read_text(encoding='utf-8'), relative


def test_rbac_output_masks_email_without_breaking_raw_input_contract():
    row = RoleAssignmentOut(
        id='r1', user_id='teacher01', email='teacher01@fpt.edu.vn', role_code='SYSTEM_ADMIN',
        scope_type='SYSTEM', scope_id='*', created_at='2026-09-15T00:00:00', updated_at='2026-09-15T00:00:00',
    )
    assert row.model_dump()['email'] == 't***1@fpt.edu.vn'
