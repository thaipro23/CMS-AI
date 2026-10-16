from datetime import datetime
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.models.academic import AcademicStudentLearningSnapshot
from app.services.academic_service import AcademicService


def test_score_payload_keeps_all_quizzes_beyond_eighty():
    service = AcademicService(None)
    payload = {'component_scores': [
        {'key': f'q{i}', 'name': f'Quiz {i}', 'earned': 15, 'possible': 15}
        for i in range(1, 91)
    ] + [{'key': 'final', 'name': 'Final test', 'earned': 60, 'possible': 60}]}
    rows = service._component_scores_from_payload(payload)
    assert len(rows) == 91
    assert any(row['name'] == 'Quiz 90' for row in rows)
    assert any(row['name'] == 'Final test' for row in rows)


def test_fresh_seventeen_grades_replace_stale_snapshot_without_using_weighted_200_percent():
    engine = create_engine('sqlite+pysqlite:///:memory:')
    AcademicStudentLearningSnapshot.__table__.create(engine)
    with Session(engine) as db:
        service = AcademicService(db)
        old = AcademicStudentLearningSnapshot(
            class_id='DOM1021.02', student_id='PH56940',
            openedx_course_id='course-v1:FPL+DOM1021+FA26',
            grade_percent=63, raw_json={'payload': {'component_scores': [
                {'name': f'Quiz {i}', 'planned': True} for i in range(1, 17)
            ]}}, learning_synced_at=datetime(2026, 10, 11),
        )
        db.add(old)
        db.commit()
        grades = [
            {'key': f'q{i}', 'name': f'Quiz {i}', 'earned': 15 if i < 16 else 10,
             'possible': 15 if i < 16 else 10, 'source': 'PersistentSubsectionGrade'}
            for i in range(1, 17)
        ] + [{'key': 'final', 'name': 'Final test', 'earned': 60, 'possible': 60}]
        fresh = {'username': 'PH56940', 'grade_percent': 200, 'component_scores': grades,
                 'enrollment_status': 'enrolled', 'progress_percent': 17.2,
                 'progress_source': 'CourseHomeOfficial'}
        plan = service._assessment_plan_from_payloads([fresh, service._payload_from_snapshot(old)])
        result = service._result_with_assessment_plan(fresh, plan)
        row = service._upsert_learning_snapshot(
            class_id=old.class_id, student=SimpleNamespace(id='PH56940', username='PH56940'),
            course_id=old.openedx_course_id, result=result, source='openedx_connector',
        )
        db.commit()
        db.expire_all()
        assert row.id == old.id
        assert row.grade_percent == 100
        assert service._percent_to_grade10(row.grade_percent) == 10
        components = service._component_scores_from_snapshot(row)
        assert len(components) == 17
        assert all(item['percent'] == 100 for item in components)
        assert row.raw_json['payload']['grade_percent'] == 200
        assert row.learning_synced_at > datetime(2026, 10, 11)
    engine.dispose()


@pytest.mark.parametrize('connector_version,plan_complete', [
    ('25.9.16.5.109', True), ('25.9.16.5.108', True),
    ('25.9.16.5.109', False), ('25.9.16.5.109', None),
])
def test_full_learning_sync_removes_old_phantom_quiz_columns(monkeypatch, connector_version, plan_complete):
    from app.models.academic import AcademicClass, AcademicStudent
    from app.services.academic import sync_enrollment

    engine = create_engine('sqlite+pysqlite:///:memory:')
    AcademicStudentLearningSnapshot.__table__.create(engine)
    course_id = 'course-v1:FPL+DOM1021+FA26'
    cls = SimpleNamespace(id='class-dom', class_code='DOM1021.02')
    student = SimpleNamespace(id='student-dom', student_code='PH56940', username='PH56940')
    with Session(engine) as session:
        old = AcademicStudentLearningSnapshot(
            class_id=cls.id, student_id=student.id, openedx_course_id=course_id,
            enrollment_status='enrolled', grade_percent=50, raw_json={'payload': {'component_scores': [
                {'name': f'Quiz {i}', 'planned': True} for i in range(1, 19)
            ]}}, learning_synced_at=datetime(2026, 10, 11),
        )
        session.add(old)
        session.commit()

        # Only roster/class lookups are substituted; production sync, plan
        # merging, grade calculation, snapshot persistence and summary run.
        class RosterQuery:
            def __getattr__(self, name):
                return lambda *args, **kwargs: self

            def scalar(self):
                return 1

            def all(self):
                return [(student, None, old)]

        class Database:
            def get(self, model, key):
                return cls if model is AcademicClass else session.get(model, key)

            def query(self, *models):
                if len(models) == 3 and models[0] is AcademicStudent:
                    return RosterQuery()
                if len(models) == 1 and models[0] is AcademicStudentLearningSnapshot:
                    return session.query(*models)
                return RosterQuery()

            def __getattr__(self, name):
                return getattr(session, name)

        service = AcademicService(Database())
        monkeypatch.setattr(service, 'assert_can_access_class', lambda *args: None)
        monkeypatch.setattr(service, 'effective_course_mapping_for_class', lambda *args: SimpleNamespace(openedx_course_id=course_id))
        monkeypatch.setattr(service, '_cohort_for_class_mapping', lambda *args: cls.class_code)
        monkeypatch.setattr(service, '_validate_connector_learning_contract', lambda *args, **kwargs: None)
        monkeypatch.setattr(service, '_invalidate_teacher_report_cache_for_class', lambda *args, **kwargs: 0)
        monkeypatch.setattr(service, '_learning_summary_for_class_course', lambda *args: {
            'component_summaries': service._component_summary_from_snapshots(session.query(AcademicStudentLearningSnapshot).all()),
        })
        fresh = {
            'username': 'PH56940', 'enrollment_status': 'enrolled', 'grade_percent': 200,
            'assessment_plan_complete': plan_complete,
            'component_scores': [
                {'key': f'q{i}', 'name': f'Quiz {i}', 'earned': 15, 'possible': 15}
                for i in range(1, 17)
            ] + [{'key': 'final', 'name': 'Final test', 'earned': 60, 'possible': 60}],
        }
        monkeypatch.setattr(sync_enrollment, 'OpenEdXConnectorClient', lambda: SimpleNamespace(
            class_analytics_payload=lambda **kwargs: {'connector_version': connector_version, 'results': [fresh]},
        ))
        workflow = sync_enrollment.AcademicSyncEnrollmentWorkflowService(service.db, service)
        monkeypatch.setattr(workflow, '_student_cms_payload', lambda *args, **kwargs: {'username': 'PH56940'})
        if connector_version == '25.9.16.5.108' or plan_complete is not True:
            error = '25.9.16.5.109' if connector_version == '25.9.16.5.108' else 'assessment_plan'
            with pytest.raises(RuntimeError, match=error):
                workflow.sync_class_learning_insight(None, cls.id, force=True)
            session.expire_all()
            assert old.grade_percent == 50
            assert len(service._component_scores_from_snapshot(old)) == 18
            assert old.learning_synced_at == datetime(2026, 10, 11)
        else:
            result = workflow.sync_class_learning_insight(None, cls.id, force=True)
            session.expire_all()
            expected = [*[f'Quiz {i}' for i in range(1, 17)], 'Final test']
            assert result['updated'] == 1
            assert [row['name'] for row in result['component_summaries']] == expected
            assert [row['name'] for row in service._component_scores_from_snapshot(old)] == expected
            assert old.grade_percent == 100
            assert old.raw_json['payload']['grade_percent'] == 200
    engine.dispose()
