from __future__ import annotations

import os

os.environ.setdefault('DATABASE_URL', 'sqlite+pysqlite:///:memory:')

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.rbac import UserContext
from app.models.academic import (
    AcademicBlock,
    AcademicAssignmentDefenseScore,
    AcademicClass,
    AcademicClassCourseMapping,
    AcademicClassStudent,
    AcademicCourseMapping,
    AcademicQuizDeadlineOverride,
    AcademicStudent,
    AcademicStudentLearningSnapshot,
    AcademicSubject,
    AcademicSubjectDelivery,
    AcademicTeacher,
    AcademicTeacherAssignment,
    AcademicTeacherReportSummary,
    AcademicTerm,
    OpenEdXUserMapping,
)
from app.models.course import CourseSyncState
from app.services.academic_service import AcademicService


def _session():
    engine = create_engine('sqlite:///:memory:')
    for model in [
        AcademicTerm,
        AcademicBlock,
        AcademicSubject,
        AcademicSubjectDelivery,
        AcademicClass,
        AcademicTeacher,
        AcademicTeacherAssignment,
        AcademicStudent,
        AcademicClassStudent,
        AcademicClassCourseMapping,
        AcademicCourseMapping,
        OpenEdXUserMapping,
        AcademicStudentLearningSnapshot,
        AcademicQuizDeadlineOverride,
        AcademicAssignmentDefenseScore,
        AcademicTeacherReportSummary,
        CourseSyncState,
    ]:
        model.__table__.create(engine)
    return sessionmaker(bind=engine)()


def test_all_cms_teachers_includes_legacy_classes_without_delivery_configuration():
    """A missing delivery row means CMS, so it must not hide the teacher."""
    db = _session()
    term = AcademicTerm(
        id='term-fa26', term_code='FA26', term_name='Fall 2026', branch='poly', active=True,
    )
    block = AcademicBlock(
        id='block-1', term_id=term.id, block_code='B1', block_name='Block 1', active=True,
    )
    explicit_subject = AcademicSubject(
        id='subject-explicit', subject_code='EXPLICIT', subject_name='Explicit CMS', branch='poly', active=True,
    )
    legacy_subject = AcademicSubject(
        id='subject-legacy', subject_code='LEGACY', subject_name='Legacy CMS', branch='poly', active=True,
    )
    null_subject = AcademicSubject(
        id='subject-null', subject_code='NULLCMS', subject_name='Null CMS', branch='poly', active=True,
    )
    explicit_class = AcademicClass(
        id='class-explicit', term_id=term.id, block_id=block.id, subject_id=explicit_subject.id,
        class_code='EXPLICIT.01', class_name='EXPLICIT.01', campus='ho', branch='poly', active=True,
    )
    legacy_class = AcademicClass(
        id='class-legacy', term_id=term.id, block_id=block.id, subject_id=legacy_subject.id,
        class_code='LEGACY.01', class_name='LEGACY.01', campus='ho', branch='poly', active=True,
    )
    null_class = AcademicClass(
        id='class-null', term_id=term.id, block_id=block.id, subject_id=null_subject.id,
        class_code='NULLCMS.01', class_name='NULLCMS.01', campus='ho', branch='poly', active=True,
    )
    explicit_teacher = AcademicTeacher(
        id='teacher-explicit', username='teacher.explicit', full_name='Giảng viên Explicit',
        campus='ho', branch='poly', active=True,
    )
    legacy_teacher = AcademicTeacher(
        id='teacher-legacy', username='teacher.legacy', full_name='Giảng viên Legacy',
        campus='ho', branch='poly', active=True,
    )
    null_teacher = AcademicTeacher(
        id='teacher-null', username='teacher.null', full_name='Giảng viên Null',
        campus='ho', branch='poly', active=True,
    )
    db.add_all([
        term,
        block,
        explicit_subject,
        legacy_subject,
        null_subject,
        explicit_class,
        legacy_class,
        null_class,
        explicit_teacher,
        legacy_teacher,
        null_teacher,
        AcademicTeacherAssignment(
            id='assignment-explicit', teacher_id=explicit_teacher.id, class_id=explicit_class.id,
            subject_id=explicit_subject.id, term_id=term.id, block_id=block.id,
            campus='ho', branch='poly', source='ap',
        ),
        AcademicTeacherAssignment(
            id='assignment-legacy', teacher_id=legacy_teacher.id, class_id=legacy_class.id,
            subject_id=legacy_subject.id, term_id=term.id, block_id=block.id,
            campus='ho', branch='poly', source='ap',
        ),
        AcademicTeacherAssignment(
            id='assignment-null', teacher_id=null_teacher.id, class_id=null_class.id,
            subject_id=null_subject.id, term_id=term.id, block_id=block.id,
            campus='ho', branch='poly', source='ap',
        ),
        AcademicSubjectDelivery(
            id='delivery-explicit', subject_id=explicit_subject.id, term_id=term.id,
            block_id=block.id, branch='poly', learning_platform='cms', active=True,
        ),
        AcademicSubjectDelivery(
            id='delivery-null', subject_id=null_subject.id, term_id=term.id,
            block_id=block.id, branch='poly', learning_platform=None, active=True,
        ),
    ])
    db.commit()

    user = UserContext(
        user_id='admin', role='admin', permissions={'manage_settings'},
        raw_claims={'ai_system_admin': True},
    )
    report = AcademicService(db).training_teacher_report(
        user,
        term_id=term.id,
        branch='poly',
        campus='ho',
        learning_status='all',
        learning_platform='cms',
        page=1,
        page_size=50,
        include_classes=False,
        use_cache=False,
    )

    assert report['total'] == 3
    assert {item['teacher_username'] for item in report['items']} == {
        'teacher.explicit',
        'teacher.legacy',
        'teacher.null',
    }

    filtered_report = AcademicService(db).training_teacher_report(
        user,
        term_id=term.id,
        branch='poly',
        campus='ho',
        learning_status='no_course_map',
        learning_platform='cms',
        page=1,
        page_size=50,
        include_classes=False,
        use_cache=False,
    )
    assert filtered_report['total'] == 3
    assert {item['teacher_username'] for item in filtered_report['items']} == {
        'teacher.explicit',
        'teacher.legacy',
        'teacher.null',
    }

    operation_scope = AcademicService(db).auto_map_subject_courses_for_filter(
        user,
        term_id=term.id,
        branch='poly',
        campus='ho',
        max_classes=50,
        dry_run=True,
    )
    assert set(operation_scope['class_ids']) == {
        'class-explicit',
        'class-legacy',
        'class-null',
    }

    # Cache rows built before this regression fix used this unversioned key and
    # may contain only explicitly configured CMS deliveries. They must not keep
    # hiding legacy CMS teachers after deployment.
    db.add(AcademicTeacherReportSummary(
        id='stale-summary',
        term_id=term.id,
        branch='poly',
        campus='ho',
        scope_key='term:term-fa26|branch:poly|campus:ho',
        teacher_id='teacher-explicit',
        teacher_username='teacher.explicit',
        teacher_name='Giảng viên Explicit',
        class_count=1,
        student_count=0,
        unique_student_count=0,
        report_json=report['items'][0],
    ))
    db.commit()
    after_deploy = AcademicService(db).training_teacher_report(
        user,
        term_id=term.id,
        branch='poly',
        campus='ho',
        learning_status='all',
        learning_platform='cms',
        page=1,
        page_size=50,
        include_classes=False,
        use_cache=True,
    )
    assert after_deploy['total'] == 3
