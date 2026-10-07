from datetime import datetime

import pytest
from sqlalchemy import event

from app.core.rbac import UserContext
from app.models.academic import (
    AcademicClass, AcademicClassCourseMapping, AcademicClassStudent,
    AcademicStudent, AcademicStudentLearningSnapshot, AcademicSubject,
    AcademicTeacher, AcademicTeacherAssignment, AcademicTerm, OpenEdXUserMapping,
)
from app.services.academic_service import AcademicService
from app.tests.test_teacher_management_all_cms_regression import _session


def seeded_report(class_count=1, students_per_class=1):
    db = _session()
    db.add_all([
        AcademicTerm(id='term', term_code='FA26', term_name='Fall 2026', branch='poly'),
        AcademicSubject(id='subject', subject_code='SUB', subject_name='Subject', branch='poly'),
    ])
    for i in range(class_count):
        cid, tid = f'class-{i:03}', f'teacher-{i:03}'
        db.add_all([
            AcademicClass(id=cid, term_id='term', subject_id='subject', class_code=cid,
                          class_name=cid, branch='poly', campus='ho'),
            AcademicTeacher(id=tid, username=tid, full_name=tid, branch='poly', campus='ho'),
            AcademicTeacherAssignment(id=f'assignment-{i}', teacher_id=tid, class_id=cid,
                                      term_id='term', subject_id='subject', branch='poly', campus='ho'),
            AcademicClassCourseMapping(id=f'map-{i}', class_id=cid,
                                       openedx_course_id='course-v1:FPL+SUB+FA26'),
        ])
        for j in range(students_per_class):
            sid = f'student-{i}-{j}'
            db.add_all([
                AcademicStudent(id=sid, student_code=sid, username=sid, full_name=sid),
                AcademicClassStudent(id=f'roster-{i}-{j}', class_id=cid, student_id=sid),
                OpenEdXUserMapping(id=f'user-{i}-{j}', student_id=sid, ap_username=sid, match_status='matched'),
                AcademicStudentLearningSnapshot(
                    id=f'snapshot-{i}-{j}', class_id=cid, student_id=sid,
                    openedx_course_id='course-v1:FPL+SUB+FA26', enrollment_status='enrolled',
                    progress_percent=98, grade_percent=60,
                    learning_synced_at=datetime(2026, 10, 6),
                    raw_json={'payload': {'progress': {'percent': 98, 'source': 'course_home'},
                                          'component_scores': [{'name': 'Quiz 1', 'earned': 6, 'possible': 10}]}},
                ),
            ])
    db.commit()
    return db


def report(db, **kwargs):
    return AcademicService(db).training_teacher_report(
        UserContext(user_id='admin', role='admin', permissions={'manage_settings'},
                    raw_claims={'ai_system_admin': True}),
        term_id='term', branch='poly', learning_platform='cms', use_cache=False,
        **kwargs,
    )


def test_overview_query_count_does_not_grow_with_class_count():
    counts = []
    for size in (1, 30):
        with seeded_report(size) as db:
            statements = []
            listener = lambda _c, _cur, statement, _p, _ctx, _many: statements.append(statement)
            event.listen(db.bind, 'before_cursor_execute', listener)
            result = report(db, page_size=30)
            event.remove(db.bind, 'before_cursor_execute', listener)
            assert len(result['items']) == size
            counts.append(len(statements))
    assert counts[1] <= counts[0] + 1, counts


def test_overview_never_loads_snapshot_payload_or_quiz_deadlines():
    with seeded_report(3) as db:
        statements = []
        event.listen(db.bind, 'before_cursor_execute',
                     lambda _c, _cur, statement, _p, _ctx, _many: statements.append(statement))
        result = report(db, page_size=15)
        assert result['items'][0]['learning_avg_grade_percent'] == 60
        assert result['items'][0]['learning_avg_progress_percent'] == 98
        assert not any('academic_student_learning_snapshots.raw_json' in sql for sql in statements)
        assert not any('academic_quiz_deadline_overrides' in sql for sql in statements)


def test_page_of_15_keeps_full_scope_kpis_and_stable_second_page():
    with seeded_report(20) as db:
        first, second = report(db, page_size=15), report(db, page=2, page_size=15)
        assert len(first['items']) == 15
        assert len(second['items']) == 5
        assert first['summary'] == second['summary']
        assert first['summary']['teacher_count'] == first['total'] == 20
        assert first['summary']['student_count'] == 20
        assert not ({x['teacher_id'] for x in first['items']} & {x['teacher_id'] for x in second['items']})


def test_kpi_snapshot_query_uses_class_index_instead_of_ranking_all_snapshots():
    with seeded_report() as db:
        captured = []
        def capture(_conn, _cursor, sql, parameters, _context, _many):
            if 'row_number() OVER' in sql:
                captured.append((sql, parameters))
        event.listen(db.bind, 'before_cursor_execute', capture)
        report(db, page_size=15)
        event.remove(db.bind, 'before_cursor_execute', capture)
        assert len(captured) == 1
        sql, parameters = captured[0]
        plan = db.connection().exec_driver_sql('EXPLAIN QUERY PLAN ' + sql, parameters).all()
        assert any('SEARCH academic_student_learning_snapshots USING INDEX' in row[3] for row in plan)


@pytest.mark.parametrize(('enrollment', 'grade', 'progress', 'matched', 'expected'), [
    ('enrolled', 60, 60, True, 'in_progress'),
    ('enrolled', 10, 98, True, 'low_grade'),
    ('enrolled', 90, 10, True, 'low_progress'),
    ('enrolled', 90, 98, True, 'good'),
    ('enrolled', None, 0, True, 'no_activity'),
    ('enrolled', None, None, True, 'no_activity'),
    ('unknown', None, None, True, 'sync_error'),
    ('not_enrolled', None, None, True, 'not_enrolled'),
    ('enrolled', 90, 98, False, 'cms_not_synced'),
])
def test_lite_status_buckets_keep_existing_priority(enrollment, grade, progress, matched, expected):
    with seeded_report() as db:
        snap = db.get(AcademicStudentLearningSnapshot, 'snapshot-0-0')
        snap.enrollment_status, snap.grade_percent, snap.progress_percent = enrollment, grade, progress
        snap.raw_json = {'payload': {'progress': {'percent': progress, 'source': 'course_home'},
                                    'component_scores': [] if grade is None else [
                                        {'name': 'Quiz 1', 'percent': grade}]}}
        mapping = db.get(OpenEdXUserMapping, 'user-0-0')
        mapping.match_status = 'matched' if matched else 'not_found'
        db.commit()
        assert report(db)['items'][0]['status_counts'] == {expected: 1}


def test_overview_ignores_old_course_snapshots_and_non_roster_learners():
    with seeded_report() as db:
        db.add_all([
            AcademicStudentLearningSnapshot(
                id='old-course', class_id='class-000', student_id='student-0-0',
                openedx_course_id='course-v1:FPL+OLD+FA26', enrollment_status='enrolled',
                grade_percent=100, progress_percent=100, updated_at=datetime(2026, 10, 7)),
            AcademicStudentLearningSnapshot(
                id='outsider', class_id='class-000', student_id='outsider',
                openedx_course_id='course-v1:FPL+SUB+FA26', enrollment_status='enrolled',
                grade_percent=100, progress_percent=100),
        ])
        db.commit()
        item = report(db)['items'][0]
        assert item['learning_synced_count'] == item['learning_enrolled_count'] == 1
        assert item['learning_avg_grade_percent'] == 60
        assert item['status_counts'] == {'good': 1}
