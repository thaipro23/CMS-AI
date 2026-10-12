from datetime import datetime
from types import SimpleNamespace

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
