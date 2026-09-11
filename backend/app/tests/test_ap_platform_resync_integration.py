from __future__ import annotations

import os

os.environ.setdefault('DATABASE_URL', 'sqlite+pysqlite:///:memory:')

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.models.academic import (
    AcademicBlock,
    AcademicClass,
    AcademicClassStudent,
    AcademicStudent,
    AcademicSubject,
    AcademicSubjectDelivery,
    AcademicTeacher,
    AcademicTeacherAssignment,
    AcademicTerm,
)
from app.services.academic.ap_importer import AcademicImportService
from app.services.academic.subject_delivery import AcademicSubjectDeliveryService


def _session():
    engine = create_engine('sqlite:///:memory:')
    for model in [
        AcademicTerm,
        AcademicBlock,
        AcademicSubject,
        AcademicClass,
        AcademicTeacher,
        AcademicTeacherAssignment,
        AcademicStudent,
        AcademicClassStudent,
        AcademicSubjectDelivery,
    ]:
        model.__table__.create(engine)
    return sessionmaker(bind=engine)()


def _payload(*, teacher: str, username: str, student_name: str):
    return {
        'term': {
            'id': 65,
            'term_name': 'Summer 2026',
            'block': [
                {
                    'id': 132,
                    'term_id': 65,
                    'block_name': 'Block 1',
                    'start_day': '2026-05-10',
                    'end_day': '2026-06-27',
                }
            ],
        },
        'class': [
            {
                'id': 101328,
                'group_name': 'AE21306',
                'psubject_name': 'Năng lượng tái tạo',
                'pterm_name': 'Summer 2026',
                'teacher': teacher,
                'psubject_code': 'AUT2131',
                'skill_code': 'AUT213',
                'pterm_id': 65,
                'block_id': 132,
                'start_date': '2026-05-10',
                'end_date': '2026-06-18',
                'student': [
                    {
                        'name': student_name,
                        'email': f'{username}@fpt.edu.vn',
                        'username': username,
                        'user_code': username.upper(),
                        'total_relearn': 0,
                    }
                ],
            }
        ],
    }


def test_udemy_then_cms_second_ap_import_reloads_class_teacher_and_roster_and_clears_marker():
    db = _session()
    importer = AcademicImportService(db)

    first = importer.import_payload(
        _payload(teacher='teacher.old', username='student.old', student_name='Student Old'),
        campus='hn',
        branch='poly',
    )
    assert first.errors == 0

    term = db.query(AcademicTerm).filter(AcademicTerm.term_name == 'Summer 2026').one()
    block = db.query(AcademicBlock).filter(AcademicBlock.term_id == term.id).one()
    subject = db.query(AcademicSubject).filter(AcademicSubject.subject_code == 'AUT2131').one()
    cls = db.query(AcademicClass).filter(AcademicClass.ap_class_id == '101328').one()
    delivery = AcademicSubjectDelivery(
        id='delivery-aut2131',
        subject_id=subject.id,
        term_id=term.id,
        block_id=block.id,
        branch='poly',
        learning_platform='udemy',
        active=True,
        metadata_json={},
    )
    db.add(delivery)
    db.commit()

    delivery_service = AcademicSubjectDeliveryService(db)
    delivery_service.set_platform(delivery.id, 'cms', actor='admin-test')
    db.refresh(delivery)
    assert delivery.learning_platform == 'cms'
    assert delivery.metadata_json['platform_history'][-1]['from'] == 'udemy'
    assert delivery.metadata_json['platform_history'][-1]['to'] == 'cms'
    assert delivery.metadata_json['ap_reconcile_required'] is True

    second = importer.import_payload(
        _payload(teacher='teacher.new', username='student.new', student_name='Student New'),
        campus='hn',
        branch='poly',
    )
    assert second.errors == 0

    assignments = db.query(AcademicTeacherAssignment).filter(
        AcademicTeacherAssignment.class_id == cls.id,
        AcademicTeacherAssignment.source == 'ap',
    ).all()
    assert len(assignments) == 1
    teacher = db.get(AcademicTeacher, assignments[0].teacher_id)
    assert teacher.username == 'teacher.new'

    links = db.query(AcademicClassStudent).filter(
        AcademicClassStudent.class_id == cls.id,
        AcademicClassStudent.source == 'ap',
    ).all()
    assert len(links) == 1
    student = db.get(AcademicStudent, links[0].student_id)
    assert student.username == 'student.new'

    cleared = delivery_service.mark_ap_reconciled(
        term_name='Summer 2026',
        branch='poly',
        subject_codes=['AUT2131'],
        actor='ap-sync-test',
    )
    assert cleared == 1
    db.refresh(delivery)
    assert delivery.metadata_json['ap_reconcile_required'] is False
    assert delivery.metadata_json['ap_reconciled_at']
    assert delivery.metadata_json['ap_reconciled_by'] == 'ap-sync-test'
