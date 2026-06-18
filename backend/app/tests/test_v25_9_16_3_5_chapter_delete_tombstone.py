from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.session import Base
from app.models import course, question, question_bank  # noqa: F401
from app.models.question_bank import LearningMaterialVersion
from app.services.question_bank_service import VersionedQuestionBankService


def make_session():
    engine = create_engine('sqlite+pysqlite:///:memory:')
    Base.metadata.create_all(bind=engine)
    return sessionmaker(bind=engine)()


def test_empty_chapter_with_deleted_material_tombstone_can_be_deleted():
    db = make_session()
    try:
        svc = VersionedQuestionBankService(db)
        dept = svc.create_department(code='IT', name='Công nghệ thông tin')
        subject = svc.create_subject(department_id=dept.id, code='WEB107', name='Thiết kế trang web')
        offering = svc.create_subject_offering(subject_id=subject.id, code='WEB107_SU25', term='SU25', version_code='v1.0', actor='admin')
        chapter = svc.create_chapter(subject_id=subject.id, subject_offering_id=offering.id, chapter_no=22, title='Bài 2.2')
        version = svc.create_bank_version(subject_id=subject.id, chapter_id=chapter.id, subject_offering_id=offering.id, version_code='v1.0', actor='admin')
        db.add(LearningMaterialVersion(
            id='deleted-mat',
            subject_id=subject.id,
            chapter_id=chapter.id,
            subject_offering_id=offering.id,
            bank_version_id=version.id,
            title='deleted file',
            file_name='deleted.pdf',
            file_type='pdf',
            storage_path='/tmp/deleted.pdf',
            content_hash='hash-deleted',
            status='deleted',
        ))
        db.commit()

        result = svc.delete_chapter(chapter.id)

        assert result['deleted'] is True
        assert db.get(type(chapter), chapter.id) is None
        assert db.get(type(version), version.id) is None
        assert db.get(LearningMaterialVersion, 'deleted-mat') is None
    finally:
        db.close()
