import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.db.session import Base
from app.models.academic import (
    AcademicClass, AcademicTeacher, AcademicTeacherAssignment, AcademicTeacherReportSummary,
)
from app.services.academic.ap_importer import AcademicImportService
from app.services.academic.report_snapshot import validate_campus_report
from app.services.academic.teacher_report import TeacherReportBranchScopeError
from app.services.academic_service import AcademicService
from app.tests.test_academic_teacher_report_branch_isolation import _scheduler_user
from app.tests.test_ap_platform_resync_integration import _payload
from app.tests.test_teacher_cms_list_performance import seeded_report, report


def _ap_engine():
    engine = create_engine('sqlite:///:memory:')
    for table in Base.metadata.tables.values():
        if table.name.startswith(('academic_', 'openedx_', 'udemy_')):
            table.create(engine)
    return engine


@pytest.mark.parametrize('order', [('poly', 'ptcd'), ('ptcd', 'poly')])
def test_ap_sync_keeps_one_teacher_and_reports_each_branch_separately(order):
    engine = _ap_engine()
    with Session(engine) as db:
        importer = AcademicImportService(db)
        for branch in (*order, order[0]):
            result = importer.import_payload(
                _payload(teacher='teacher.shared', username=f'student.{branch}',
                         student_name=f'Student {branch}'),
                campus='hn' if branch == 'poly' else 'dn', branch=branch,
            )
            assert result.errors == 0
            db.commit()
        teacher = db.query(AcademicTeacher).one()
        assert teacher.branch is None  # No single system owns this person.
        assert teacher.campus is None
        assert db.query(AcademicTeacherAssignment).count() == 2
        for branch in ('poly', 'ptcd'):
            cls = db.query(AcademicClass).filter_by(branch=branch).one()
            # Also exercise already-existing, last-write-wins teacher profiles.
            teacher.branch = 'ptcd' if branch == 'poly' else 'poly'
            teacher.campus = 'ho' if cls.campus == 'hn' else 'hn'
            db.flush()
            result = AcademicService(db).training_teacher_report(
                _scheduler_user(), term_id=cls.term_id, branch=branch,
                campus=cls.campus, include_all=True, include_students=True,
                use_cache=False, allowed_class_ids={cls.id},
                enforce_branch_integrity=True,
            )
            item = result['items'][0]
            assert item['teacher_id'] == teacher.id
            assert item['branch'] == branch
            assert item['campus'] == cls.campus
            assert {row['class_id'] for row in item['classes']} == {cls.id}
            assert {row['student_username'] for row in result['student_watch_rows']} == {f'student.{branch}'}
            assert validate_campus_report(result, campus=cls.campus, branch=branch)['teacher_count'] == 1
    engine.dispose()


def test_ap_sync_refreshes_shared_teacher_before_merging_another_workers_scope():
    engine = _ap_engine()
    payload = _payload(teacher='teacher.shared', username='student.one', student_name='One')
    with Session(engine) as first, Session(engine) as second:
        importer = AcademicImportService(first)
        assert importer.import_payload(payload, campus='hn', branch='poly').errors == 0
        teacher = first.query(AcademicTeacher).one()  # Keep a stale identity-map object.
        assert AcademicImportService(second).import_payload(payload, campus='dn', branch='ptcd').errors == 0
        assert importer.import_payload(payload, campus='ct', branch='poly').errors == 0
        first.refresh(teacher)
        assert teacher.branch is None
        assert teacher.metadata_json['ap_branch_campuses'] == {'poly': ['ct', 'hn'], 'ptcd': ['dn']}
    engine.dispose()


def test_ap_subject_correction_reconciles_old_assignment_before_scheduled_report():
    engine = _ap_engine()
    with Session(engine) as db:
        importer = AcademicImportService(db)
        payload = _payload(teacher='teacher.shared', username='student.one', student_name='One')
        assert importer.import_payload(payload, campus='hn', branch='poly').errors == 0
        teacher = db.query(AcademicTeacher).one()
        teacher.metadata_json = {'cms_display_name': 'Shared Teacher'}
        db.commit()
        payload['class'][0]['psubject_code'] = 'AUT2132'
        assert importer.import_payload(payload, campus='hn', branch='poly').errors == 0
        cls = db.query(AcademicClass).one()
        assignments = db.query(AcademicTeacherAssignment).all()
        assert len(assignments) == 1
        assert assignments[0].subject_id == cls.subject_id
        assert teacher.metadata_json['cms_display_name'] == 'Shared Teacher'
        result = AcademicService(db).training_teacher_report(
            _scheduler_user(), term_id=cls.term_id, branch='poly', campus='hn',
            include_all=True, include_students=True, use_cache=False,
            allowed_class_ids={cls.id}, enforce_branch_integrity=True,
        )
        assert validate_campus_report(result, campus='hn', branch='poly')['class_count'] == 1
    engine.dispose()


@pytest.mark.parametrize('detailed', [False, True])
def test_existing_shared_teacher_profile_does_not_override_report_scope(detailed):
    with seeded_report() as db:
        teacher = db.get(AcademicTeacher, 'teacher-000')
        teacher.branch, teacher.campus = 'ptcd', 'hn'
        db.commit()
        result = report(db, campus='ho', include_all=detailed, include_students=detailed,
                        enforce_branch_integrity=detailed)
        assert result['items'][0]['branch'] == 'poly'
        assert result['items'][0]['campus'] == 'ho'


@pytest.mark.parametrize('detailed', [False, True])
def test_teacher_aggregate_across_campuses_has_no_single_campus_label(detailed):
    with seeded_report(2) as db:
        assignment = db.get(AcademicTeacherAssignment, 'assignment-1')
        assignment.teacher_id, assignment.campus = 'teacher-000', 'hn'
        db.get(AcademicClass, 'class-001').campus = 'hn'
        db.commit()
        result = report(db, include_all=detailed, include_students=detailed)
        assert len(result['items']) == 1
        assert result['items'][0]['branch'] == 'poly'
        assert result['items'][0]['class_count'] == 2
        assert result['items'][0]['campus'] is None


@pytest.mark.parametrize(('field', 'value'), [
    ('branch', 'ptcd'), ('term_id', 'foreign-term'),
    ('subject_id', 'foreign-subject'), ('campus', 'hn'),
])
def test_scheduled_report_rejects_assignment_context_outside_its_class(field, value):
    with seeded_report() as db:
        assignment = db.get(AcademicTeacherAssignment, 'assignment-0')
        setattr(assignment, field, value)
        db.commit()
        with pytest.raises(TeacherReportBranchScopeError, match='assignment'):
            report(db, campus='ho', include_all=True, include_students=True,
                   allowed_class_ids={'class-000'}, enforce_branch_integrity=True)


def test_empty_frozen_class_scope_does_not_validate_unrelated_assignments():
    with seeded_report() as db:
        db.get(AcademicTeacherAssignment, 'assignment-0').branch = 'ptcd'
        db.get(AcademicClass, 'class-000').branch = 'ptcd'
        db.commit()
        result = report(db, campus='ho', include_all=True, include_students=True,
                        allowed_class_ids=set(), enforce_branch_integrity=True)
        assert result['items'] == []


def test_pre_fix_materialized_teacher_profile_is_not_served_after_deploy():
    with seeded_report() as db:
        db.add(AcademicTeacherReportSummary(
            id='old-summary', term_id='term', branch='poly', campus='ho',
            scope_key='v2|term:term|branch:poly|campus:ho', teacher_id='teacher-000',
            teacher_username='teacher-000', teacher_name='teacher-000',
            report_json={'teacher_id': 'teacher-000', 'branch': 'ptcd', 'campus': 'hn',
                         'class_count': 1, 'cms_class_count': 1},
        ))
        db.commit()
        result = AcademicService(db).training_teacher_report(
            _scheduler_user(), term_id='term', branch='poly', campus='ho',
            learning_platform='cms', use_cache=True,
        )
        assert result['items'][0]['branch'] == 'poly'
        assert result['items'][0]['campus'] == 'ho'
