from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.session import Base
from app.models import course, question, question_bank  # noqa: F401
from app.models.question import Question
from app.services.question_bank_service import VersionedQuestionBankService


def make_session():
    engine = create_engine('sqlite+pysqlite:///:memory:')
    Base.metadata.create_all(bind=engine)
    return sessionmaker(bind=engine)()


def test_bank_release_generates_one_openedx_library_key_per_version():
    db = make_session()
    try:
        svc = VersionedQuestionBankService(db)
        dept = svc.create_department(code='DESIGN', name='Bộ môn Thiết kế')
        subject = svc.create_subject(department_id=dept.id, code='DOM123', name='Thiết kế nhận diện thương hiệu')
        chapter = svc.create_chapter(subject_id=subject.id, chapter_no=4, title='Bài 4')
        version = svc.create_bank_version(subject_id=subject.id, chapter_id=chapter.id, version_code='v1.0', title='DOM123 Bài 4 v1.0')
        release = svc.create_release(bank_version_id=version.id, release_code='DOM123-B4-v1.0', actor='admin')
        assert release.openedx_library_key == 'lib:FPT:dom123-bai-4-v1-0'
        assert release.status == 'draft'
        assert svc.summary()['releases'] == 1
    finally:
        db.close()


def test_release_collects_only_approved_and_published_questions_in_bank_version():
    db = make_session()
    try:
        svc = VersionedQuestionBankService(db)
        dept = svc.create_department(code='DESIGN', name='Bộ môn Thiết kế')
        subject = svc.create_subject(department_id=dept.id, code='DOM123', name='Thiết kế nhận diện thương hiệu')
        chapter = svc.create_chapter(subject_id=subject.id, chapter_no=4, title='Bài 4')
        version = svc.create_bank_version(subject_id=subject.id, chapter_id=chapter.id, version_code='v1.0', title='DOM123 Bài 4 v1.0')
        q1 = Question(course_id='bank:DOM123', subject_id=subject.id, subject_chapter_id=chapter.id, bank_version_id=version.id, difficulty='easy', question_text='Câu 1?', option_a='A', option_b='B', option_c='C', option_d='D', correct_answer='A', status='approved', question_family_id='fam-a')
        q2 = Question(course_id='bank:DOM123', subject_id=subject.id, subject_chapter_id=chapter.id, bank_version_id=version.id, difficulty='hard', question_text='Câu 2?', option_a='A', option_b='B', option_c='C', option_d='D', correct_answer='A', status='published', question_family_id='fam-b')
        q3 = Question(course_id='bank:DOM123', subject_id=subject.id, subject_chapter_id=chapter.id, bank_version_id=version.id, difficulty='medium', question_text='Câu 3?', option_a='A', option_b='B', option_c='C', option_d='D', correct_answer='A', status='draft', question_family_id='fam-c')
        db.add_all([q1, q2, q3])
        db.commit()
        release = svc.create_release(bank_version_id=version.id, actor='admin')
        assert release.status == 'published'
        assert release.approved_question_count == 2
        assert release.easy_count == 1
        assert release.hard_count == 1
        assert release.medium_count == 0
        assert release.family_count == 2
        assert q1.bank_release_id == release.id
        assert q2.bank_release_id == release.id
        assert q3.bank_release_id is None
    finally:
        db.close()


def test_course_mapping_points_openedx_course_to_subject_without_owning_questions():
    db = make_session()
    try:
        svc = VersionedQuestionBankService(db)
        dept = svc.create_department(code='IT', name='Công nghệ thông tin')
        subject = svc.create_subject(department_id=dept.id, code='PRN232', name='PRN232')
        mapping = svc.create_course_mapping(openedx_course_id='course-v1:FPT+PRN232+SU26', department_id=dept.id, subject_id=subject.id, term='SU26', actor='admin')
        assert mapping.openedx_course_id == 'course-v1:FPT+PRN232+SU26'
        assert mapping.subject_id == subject.id
        assert svc.summary()['course_mappings'] == 1
    finally:
        db.close()
