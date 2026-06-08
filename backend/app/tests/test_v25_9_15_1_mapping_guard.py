from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.session import Base
from app.models.question_bank import Department, Subject, SubjectChapter, QuestionBankVersion, QuestionBankRelease
from app.services.question_bank_service import VersionedQuestionBankService


def make_session():
    engine = create_engine('sqlite:///:memory:')
    Base.metadata.create_all(bind=engine)
    return sessionmaker(bind=engine)()


def seed_subject(db):
    department = Department(id='dept-design', code='DESIGN', name='Thiết kế')
    subject = Subject(id='sub-dom123', department_id=department.id, code='DOM123', name='Thiết kế nhận diện thương hiệu')
    chapter = SubjectChapter(id='chap-b4', subject_id=subject.id, chapter_no=4, title='Bài 4: Triển khai truyền thông')
    db.add_all([department, subject, chapter])
    db.commit()
    return department, subject, chapter


def test_course_mapping_blocks_wrong_subject_code():
    db = make_session()
    _, subject, _ = seed_subject(db)
    result = VersionedQuestionBankService(db).validate_course_mapping(
        openedx_course_id='course-v1:FPT+MUL211+SU26',
        subject_id=subject.id,
    )
    assert result['risk_level'] == 'high'
    assert result['can_create_mapping'] is False
    assert any(check['code'] == 'course_code_match' and check['status'] == 'fail' for check in result['checks'])


def test_course_mapping_allows_matching_subject_code():
    db = make_session()
    department, subject, _ = seed_subject(db)
    result = VersionedQuestionBankService(db).validate_course_mapping(
        openedx_course_id='course-v1:FPT+DOM123+SU26',
        subject_id=subject.id,
        department_id=department.id,
        term='SU26',
    )
    assert result['risk_level'] == 'low'
    assert result['can_create_mapping'] is True


def test_chapter_mapping_requires_published_release():
    db = make_session()
    department, subject, chapter = seed_subject(db)
    service = VersionedQuestionBankService(db)
    mapping = service.create_course_mapping(
        openedx_course_id='course-v1:FPT+DOM123+SU26',
        subject_id=subject.id,
        department_id=department.id,
    )
    version = QuestionBankVersion(id='bv1', subject_id=subject.id, chapter_id=chapter.id, version_no=1, version_code='v1.0', title='v1')
    release = QuestionBankRelease(id='rel1', bank_version_id=version.id, subject_id=subject.id, chapter_id=chapter.id, release_code='DOM123-B4-v1.0', title='r1', status='ready', openedx_library_key='lib:FPT:dom123-bai-4-v1-0')
    db.add_all([version, release])
    db.commit()
    result = service.validate_course_chapter_mapping(
        course_mapping_id=mapping.id,
        subject_chapter_id=chapter.id,
        bank_release_id=release.id,
        openedx_parent_node_id='block-v1:FPT+DOM123+SU26+type@chapter+block@bai-4',
        openedx_node_title='Bài 4: Triển khai truyền thông',
    )
    assert result['risk_level'] == 'high'
    assert any(check['code'] == 'release_published' and check['status'] == 'fail' for check in result['checks'])
