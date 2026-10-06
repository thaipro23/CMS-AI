from datetime import datetime
import importlib.util
from pathlib import Path
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.models.academic import AcademicStudentLearningSnapshot
from app.services.academic_service import AcademicService


def snapshot(components, *, weighted=2.0):
    return SimpleNamespace(
        grade_percent=weighted,
        raw_json={'source': 'openedx_connector', 'payload': {
            'grade_percent': weighted,
            'component_scores': components,
        }},
    )


def test_overall_grade_is_equal_average_of_quizzes_and_optional_final():
    service = AcademicService(None)
    value = service._snapshot_grade_percent(snapshot([
        {'name': 'Quiz 01', 'earned': 10, 'possible': 10, 'weight': 1},
        {'name': 'Quiz 02', 'earned': 6, 'possible': 15, 'weight': 99},
        {'name': 'Final test', 'earned': 4, 'possible': 10, 'weight': 100},
        {'name': 'Assignment', 'earned': 100, 'possible': 100},
    ]))
    assert value == 60.0
    assert service._percent_to_grade10(value) == 6.0


def test_course_without_final_averages_only_its_actual_quizzes():
    service = AcademicService(None)
    assert service._snapshot_grade_percent(snapshot([
        None,
        {'name': 'Quiz 1', 'earned': 8, 'possible': 10},
        {'name': 'Quiz 2', 'earned': 4, 'possible': 10},
    ])) == 60.0


def test_missing_scores_are_zero_and_duplicate_quiz_shells_do_not_double_count():
    service = AcademicService(None)
    assert service._snapshot_grade_percent(snapshot([
        {'name': 'Quiz 01', 'earned': 10, 'possible': 10},
        {'name': 'Quiz 1', 'planned': True},
        {'name': 'Quiz 2', 'planned': True},
        {'name': 'Final test', 'planned': True},
    ])) == 33.33


@pytest.mark.parametrize('components', [None, [], [{'name': 'Assignment', 'percent': 100}]])
def test_missing_assessment_plan_has_no_overall_grade(components):
    assert AcademicService(None)._snapshot_grade_percent(snapshot(components)) is None


def test_full_marks_for_pp03883_ignore_invalid_course_weighted_grade():
    components = [{'name': f'Quiz {i:02}', 'earned': 10, 'possible': 10} for i in range(1, 9)]
    components.append({'name': 'Final test', 'earned': 10, 'possible': 10})
    assert AcademicService(None)._snapshot_grade_percent(snapshot(components)) == 100.0


def test_small_percentage_scores_do_not_become_full_marks():
    service = AcademicService(None)
    value = service._snapshot_grade_percent(snapshot([
        {'name': 'Quiz 1', 'earned': 1, 'possible': 100, 'percent': 1},
        {'name': 'Final test', 'planned': True},
    ]))
    assert value == 0.5
    assert service._percent_to_grade10(value) == 0.05


@pytest.mark.parametrize('percent,expected', [(1, 1), (0.5, 0.5), (float('nan'), 0)])
def test_explicit_component_percent_is_already_in_percent_units(percent, expected):
    value = AcademicService(None)._snapshot_grade_percent(snapshot([
        {'name': 'Quiz 1', 'percent': percent},
    ]))
    assert value == expected


def test_learning_sync_persists_assessment_average_and_preserves_cms_raw_grade():
    engine = create_engine('sqlite+pysqlite:///:memory:')
    AcademicStudentLearningSnapshot.__table__.create(engine)
    with Session(engine) as db:
        service = AcademicService(db)
        payload = snapshot([
            {'name': 'Quiz 1', 'earned': 8, 'possible': 10},
            {'name': 'Final test', 'earned': 4, 'possible': 10},
        ]).raw_json['payload']
        payload.update(progress_percent=98, progress_source='CourseHomeOfficial', enrollment_status='enrolled')
        row = service._upsert_learning_snapshot(
            class_id='class-1', student=SimpleNamespace(id='student-1', username='PP03883'),
            course_id='course-v1:FPL+TEST+FA26', result=payload, source='openedx_connector',
        )
        db.commit()
        assert row.grade_percent == 60.0
        assert row.progress_percent == 98.0
        assert row.raw_json['payload']['grade_percent'] == 2.0
        assert isinstance(row.learning_synced_at, datetime)
    engine.dispose()


def test_grade_backfill_updates_sql_filters_without_touching_completion_or_sync_time(monkeypatch):
    path = Path(__file__).resolve().parents[2] / 'alembic/versions/0073_assessment_average_grade.py'
    spec = importlib.util.spec_from_file_location('assessment_grade_migration', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    engine = create_engine('sqlite+pysqlite:///:memory:')
    AcademicStudentLearningSnapshot.__table__.create(engine)
    old_time = datetime(2026, 10, 5, 1, 0)
    with Session(engine) as db:
        raw = snapshot([
            {'name': 'Quiz 1', 'earned': 8, 'possible': 10},
            {'name': 'Final test', 'earned': 4, 'possible': 10},
        ]).raw_json
        row = AcademicStudentLearningSnapshot(
            id='snapshot-1', class_id='class-1', student_id='student-1',
            openedx_course_id='course-v1:FPL+TEST+FA26', grade_percent=2,
            progress_percent=98, completed_blocks=49, total_blocks=50,
            learning_synced_at=old_time, updated_at=old_time, raw_json=raw,
        )
        db.add(row)
        db.commit()
        monkeypatch.setattr(module.op, 'get_bind', lambda: db.connection())
        module.upgrade()
        db.expire_all()
        assert row.grade_percent == 60
        assert db.query(AcademicStudentLearningSnapshot).filter(
            AcademicStudentLearningSnapshot.grade_percent < 50,
        ).count() == 0
        assert row.progress_percent == 98
        assert (row.completed_blocks, row.total_blocks) == (49, 50)
        assert row.learning_synced_at == old_time
        assert row.updated_at == old_time
        assert row.raw_json == raw
        module.downgrade()
        db.expire_all()
        assert row.grade_percent == 2
    engine.dispose()
