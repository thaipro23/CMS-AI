from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding='utf-8')


def test_teacher_cms_list_shows_sent_mail_total_in_teacher_identity():
    source = read('frontend/app/teacher-management/TeacherManagementPlatformPage.tsx')
    assert 'Đã gửi {item.progress_email_sent_count || 0} mail' in source
    assert 'isCms ? <small' in source


def test_teacher_class_list_has_cms_only_mail_sent_column():
    source = read('frontend/app/teacher-management/teachers/[teacherId]/classes/page.tsx')
    assert "key: 'progress-email'" in source
    assert "header: 'Mail đã gửi'" in source
    assert 'cls.progress_email_sent_count' in source
    assert 'platformColumns: EnterpriseTableColumn<AcademicTrainingClassReport>[] = isCms' in source


def test_class_student_list_has_cms_only_mail_sent_count_and_latest_time():
    source = read('frontend/app/student-management/classes/[classId]/page.tsx')
    assert "key: 'progress-email'" in source
    assert "header: 'Mail đã gửi'" in source
    assert 'student.progress_email_sent_count' in source
    assert 'student.progress_email_last_sent_at' in source
    assert '...(!isUdemyClass ? [' in source
    assert 'Mail đã đọc' not in source
    assert 'Mail đã nhận' not in source


def test_frontend_types_expose_mail_statistics_at_all_three_levels():
    source = read('frontend/types/index.ts')
    assert source.count('progress_email_sent_count?: number') >= 3
    assert 'progress_email_last_sent_at?: string | null' in source
