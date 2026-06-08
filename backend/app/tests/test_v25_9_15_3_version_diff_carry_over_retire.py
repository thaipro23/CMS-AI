from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.session import Base
from app.models import course, question, question_bank  # noqa: F401
from app.models.question import Question
from app.models.question_bank import LearningMaterialVersion, MaterialChunk
from app.services.question_bank_service import VersionedQuestionBankService


def make_session():
    engine = create_engine('sqlite+pysqlite:///:memory:')
    Base.metadata.create_all(bind=engine)
    return sessionmaker(bind=engine)()


def seed_versions(db):
    svc = VersionedQuestionBankService(db)
    dept = svc.create_department(code='DESIGN', name='Bộ môn Thiết kế')
    subject = svc.create_subject(department_id=dept.id, code='DOM123', name='Thiết kế nhận diện thương hiệu')
    chapter = svc.create_chapter(subject_id=subject.id, chapter_no=4, title='Bài 4')
    v1 = svc.create_bank_version(subject_id=subject.id, chapter_id=chapter.id, version_code='v1.0', title='DOM123 B4 v1.0')
    v2 = svc.create_bank_version(subject_id=subject.id, chapter_id=chapter.id, version_code='v2.0', title='DOM123 B4 v2.0', based_on_version_id=v1.id)
    m1 = LearningMaterialVersion(id='mat-v1', subject_id=subject.id, chapter_id=chapter.id, bank_version_id=v1.id, title='slide v1', file_name='slide-v1.txt', file_type='txt', storage_path='x', content_hash='hash-v1', version_no=1, change_type='initial', status='indexed')
    m2 = LearningMaterialVersion(id='mat-v2', subject_id=subject.id, chapter_id=chapter.id, bank_version_id=v2.id, title='slide v2', file_name='slide-v2.txt', file_type='txt', storage_path='x', content_hash='hash-v2', version_no=1, change_type='updated', status='indexed')
    db.add_all([m1, m2])
    db.add(MaterialChunk(id='chunk-v1', material_version_id=m1.id, bank_version_id=v1.id, subject_id=subject.id, chapter_id=chapter.id, chunk_index=1, content='Logo số cần tối giản và tương phản cao.', token_count=20, content_hash='chunk-a'))
    db.add(MaterialChunk(id='chunk-v2', material_version_id=m2.id, bank_version_id=v2.id, subject_id=subject.id, chapter_id=chapter.id, chunk_index=1, content='Logo số cần tối giản, tương phản cao và thêm phần responsive.', token_count=25, content_hash='chunk-b'))
    q = Question(course_id=f'bank:{v1.id}', subject_id=subject.id, subject_chapter_id=chapter.id, bank_version_id=v1.id, difficulty='easy', question_text='Khi thiết kế favicon, yếu tố nào quan trọng nhất?', option_a='Tối giản', option_b='Nhiều chữ nhỏ', option_c='Nhiều chi tiết', option_d='Gradient phức tạp', correct_answer='A', status='approved', question_family_id='fam-logo-easy', concept_key='logo-so', concept_title='Logo số', topic='Logo số', question_hash='hash-question-logo')
    db.add(q)
    db.commit()
    return svc, v1, v2, q


def test_diff_preview_creates_carry_over_candidates_without_mutating_questions():
    db = make_session()
    try:
        svc, v1, v2, q = seed_versions(db)
        result = svc.preview_bank_version_diff(from_bank_version_id=v1.id, to_bank_version_id=v2.id, actor='admin')
        assert result['ok'] is True
        assert result['diff_id']
        assert result['summary']['source_approved_question_count'] == 1
        assert q.id in result['carry_over_candidates'] or q.id in result['review_candidates']
        assert db.get(Question, q.id).bank_version_id == v1.id
    finally:
        db.close()


def test_carry_over_creates_new_question_with_lineage_and_approved_status():
    db = make_session()
    try:
        svc, v1, v2, q = seed_versions(db)
        result = svc.carry_over_questions(from_bank_version_id=v1.id, to_bank_version_id=v2.id, question_ids=[q.id], require_review=True, actor='admin')
        assert result['created_count'] == 1
        new_q = db.get(Question, result['created_question_ids'][0])
        assert new_q.bank_version_id == v2.id
        assert new_q.previous_question_id == q.id
        assert new_q.lineage_root_question_id == q.id
        assert new_q.question_revision_no == 2
        assert new_q.is_carry_over is True
        assert new_q.status == 'approved'
        assert db.get(Question, q.id).status == 'approved'
    finally:
        db.close()


def test_retire_marks_question_without_deleting_it():
    db = make_session()
    try:
        svc, v1, _v2, q = seed_versions(db)
        result = svc.retire_questions(bank_version_id=v1.id, question_ids=[q.id], reason='Concept không còn trong tài liệu mới', actor='admin')
        assert result['retired_count'] == 1
        retired = db.get(Question, q.id)
        assert retired.is_retired is True
        assert retired.status == 'retired'
        assert retired.retired_reason == 'Concept không còn trong tài liệu mới'
    finally:
        db.close()


def test_retire_from_diff_excludes_source_question_without_cloning_or_mutating_source():
    db = make_session()
    try:
        svc, v1, v2, q = seed_versions(db)
        result = svc.retire_questions(bank_version_id=v2.id, question_ids=[q.id], reason='Không còn phù hợp ở v2', actor='admin')
        assert result['retired_count'] == 0
        assert result['excluded_count'] == 1
        assert result['excluded_question_ids'] == [q.id]
        source = db.get(Question, q.id)
        assert source.bank_version_id == v1.id
        assert source.status == 'approved'
        assert source.is_retired is False
        clones = db.query(Question).filter(Question.bank_version_id == v2.id).all()
        assert clones == []
        assert q.id in (db.get(type(v2), v2.id).metadata_json or {}).get('excluded_source_question_ids', [])
    finally:
        db.close()


def test_subject_offering_sits_between_subject_and_chapter():
    db = make_session()
    try:
        svc = VersionedQuestionBankService(db)
        dept = svc.create_department(code='DESIGN2', name='Bộ môn Thiết kế 2')
        subject = svc.create_subject(department_id=dept.id, code='DOM999', name='Môn test')
        offering = svc.create_subject_offering(subject_id=subject.id, code='DOM999_SU26', term='SU26', version_code='v1.0', actor='admin')
        chapter = svc.create_chapter(subject_id=subject.id, subject_offering_id=offering.id, chapter_no=1, title='Bài 1')
        version = svc.create_bank_version(subject_id=subject.id, chapter_id=chapter.id, subject_offering_id=offering.id, version_code='v1.0', title='DOM999 SU26 Bài 1')
        assert chapter.subject_offering_id == offering.id
        assert version.subject_offering_id == offering.id
    finally:
        db.close()


def test_subject_offering_term_code_sp_su_fa_normalization():
    db = make_session()
    try:
        svc = VersionedQuestionBankService(db)
        dept = svc.create_department(code='DESIGN3', name='Bộ môn Thiết kế 3')
        subject = svc.create_subject(department_id=dept.id, code='DOM321', name='Môn test term')
        sp = svc.create_subject_offering(subject_id=subject.id, term='SP25', actor='admin')
        su = svc.create_subject_offering(subject_id=subject.id, term='SU26', actor='admin')
        fa = svc.create_subject_offering(subject_id=subject.id, term='FA27', actor='admin')
        assert sp.code == 'DOM321_SP25'
        assert su.code == 'DOM321_SU26'
        assert fa.code == 'DOM321_FA27'
        assert sp.term == 'SP25'
        assert su.metadata_json['term']['year'] == 2026
        assert fa.metadata_json['term']['season'] == 'FA'
    finally:
        db.close()


def test_clone_subject_offering_creates_new_rows_for_chapters_materials_and_approved_questions():
    db = make_session()
    try:
        svc = VersionedQuestionBankService(db)
        dept = svc.create_department(code='DESIGN4', name='Bộ môn Thiết kế 4')
        subject = svc.create_subject(department_id=dept.id, code='DOM654', name='Môn clone term')
        sp = svc.create_subject_offering(subject_id=subject.id, term='SP25', actor='admin')
        chapter = svc.create_chapter(subject_id=subject.id, subject_offering_id=sp.id, chapter_no=1, title='Bài 1')
        version = svc.create_bank_version(subject_id=subject.id, subject_offering_id=sp.id, chapter_id=chapter.id, version_code='v1.0', title='SP25 Bài 1')
        mat = LearningMaterialVersion(id='term-mat-sp25', subject_id=subject.id, chapter_id=chapter.id, subject_offering_id=sp.id, bank_version_id=version.id, title='slide sp25', file_name='slide.txt', file_type='txt', storage_path='/same/file.txt', content_hash='same-hash', version_no=1, change_type='initial', status='indexed')
        db.add(mat)
        db.add(MaterialChunk(id='term-chunk-sp25', material_version_id=mat.id, bank_version_id=version.id, subject_id=subject.id, chapter_id=chapter.id, subject_offering_id=sp.id, chunk_index=1, content='Nội dung dùng lại', token_count=10, content_hash='chunk-same'))
        q = Question(course_id=f'bank:{version.id}', subject_id=subject.id, subject_chapter_id=chapter.id, bank_version_id=version.id, material_version_id=mat.id, difficulty='easy', question_text='Câu hỏi dùng lại?', option_a='A', option_b='B', option_c='C', option_d='D', correct_answer='A', status='approved', question_family_id='fam-reuse-easy', concept_key='reuse', concept_title='Reuse', topic='Reuse', question_hash='hash-reuse')
        db.add(q)
        db.commit()

        su = svc.create_subject_offering(subject_id=subject.id, term='SU25', clone_from_offering_id=sp.id, actor='admin')
        assert su.code == 'DOM654_SU25'
        result = su.metadata_json.get('clone_result') or {}
        assert result['chapters'] == 1
        assert result['materials'] == 1
        assert result['chunks'] == 1
        assert result['questions'] == 1

        cloned_chapter = db.query(type(chapter)).filter(type(chapter).subject_offering_id == su.id).one()
        assert cloned_chapter.id != chapter.id
        cloned_version = db.query(type(version)).filter(type(version).subject_offering_id == su.id).one()
        assert cloned_version.id != version.id
        cloned_mat = db.query(LearningMaterialVersion).filter(LearningMaterialVersion.bank_version_id == cloned_version.id).one()
        assert cloned_mat.id != mat.id
        assert cloned_mat.storage_path == mat.storage_path
        cloned_q = db.query(Question).filter(Question.bank_version_id == cloned_version.id).one()
        assert cloned_q.id != q.id
        assert cloned_q.previous_question_id == q.id
        assert cloned_q.status == 'approved'
        assert cloned_q.openedx_library_problem_id is None
    finally:
        db.close()


def test_subject_version_is_direct_child_of_subject_and_chapters_are_under_that_version():
    db = make_session()
    try:
        svc = VersionedQuestionBankService(db)
        dept = svc.create_department(code='DESIGN5', name='Bộ môn Thiết kế 5')
        subject = svc.create_subject(department_id=dept.id, code='DOM777', name='Môn version tree')
        sp25 = svc.create_subject_offering(subject_id=subject.id, term='SP25', actor='admin')
        su25 = svc.create_subject_offering(subject_id=subject.id, term='SU25', clone_from_offering_id=sp25.id, actor='admin')

        assert sp25.subject_id == subject.id
        assert su25.subject_id == subject.id
        assert sp25.code == 'DOM777_SP25'
        assert su25.code == 'DOM777_SU25'
        assert sp25.metadata_json['architecture'] == 'subject_version_tree'
        assert su25.based_on_offering_id == sp25.id

        chapter = svc.create_chapter(subject_id=subject.id, subject_offering_id=sp25.id, chapter_no=1, title='Bài 1')
        assert chapter.subject_id == subject.id
        assert chapter.subject_offering_id == sp25.id
    finally:
        db.close()
