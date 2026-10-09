import importlib
from datetime import datetime

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.models import learning_analytics as models
from app.services.learning_analytics.quiz_attempt_analyzer import QuizAttemptFeature


def test_item_models_exist():
    assert hasattr(models, 'AnalyticsQuizItemSubmission')
    assert hasattr(models, 'AnalyticsQuizItemReceipt')
    assert hasattr(models, 'AnalyticsQuizIntegrityResult')


def test_materialization_preserves_answers_after_raw_cleanup_and_is_idempotent():
    materializer = importlib.import_module('app.services.learning_analytics.quiz_item_materializer')
    engine = create_engine('sqlite://')
    for name in ('AnalyticsQuizItemSubmission', 'AnalyticsQuizItemReceipt'):
        getattr(models, name).__table__.create(engine)
    feat = QuizAttemptFeature('course', 'sv', '1', None, 'unit', 1)
    feat.raw_submissions = [{
        'event_id': 'e1', 'event_type': 'problem_check', 'event_source': 'server',
        'submitted_at': datetime(2026, 10, 5), 'problem_usage_key': 'q1',
        'context': {'module': {'original_usage_version': 'v1'}},
        'payload': {'attempts': 1, 'submission': {
            'input1': {'answer': ['B', 'A'], 'correct': False, 'variant': '7',
                       'response_type': 'choiceresponse'},
            'input2': {'answer': 'Ab C', 'correct': '', 'variant': '7',
                       'response_type': 'stringresponse'},
        }},
    }]
    with Session(engine) as db:
        materializer.materialize_quiz_items(db, feat, attempt_id='attempt1')
        db.commit()
        materializer.materialize_quiz_items(db, feat, attempt_id='attempt1')
        db.commit()
        items = db.query(models.AnalyticsQuizItemSubmission).order_by(models.AnalyticsQuizItemSubmission.input_id).all()
        assert len(items) == 2
        assert items[0].answer_json == ['A', 'B']
        assert items[0].correct is False
        assert items[0].variant == '7'
        assert items[1].answer_json == 'Ab C'
        assert items[1].correct is None
        assert db.query(models.AnalyticsQuizItemReceipt).count() == 1
        # No foreign key back to staging events: durable answers survive cleanup.
        assert not models.AnalyticsQuizItemSubmission.__table__.foreign_keys


def test_browser_answers_are_not_materialized():
    materializer = importlib.import_module('app.services.learning_analytics.quiz_item_materializer')
    engine = create_engine('sqlite://')
    models.AnalyticsQuizItemSubmission.__table__.create(engine)
    models.AnalyticsQuizItemReceipt.__table__.create(engine)
    feat = QuizAttemptFeature('course', 'sv', '1', None, 'unit', 1)
    feat.raw_submissions = [{'event_id': 'e1', 'event_type': 'problem_check',
                             'event_source': 'browser', 'payload': {'answers': {'a': 'x'}}}]
    with Session(engine) as db:
        materializer.materialize_quiz_items(db, feat, attempt_id='attempt1')
        assert db.query(models.AnalyticsQuizItemSubmission).count() == 0
        assert db.query(models.AnalyticsQuizItemReceipt).count() == 1


def test_new_migration_upgrade_downgrade_and_reupgrade():
    from pathlib import Path
    import importlib.util
    from alembic.migration import MigrationContext
    from alembic.operations import Operations
    from sqlalchemy import inspect
    path = Path(__file__).resolve().parents[2] / 'alembic/versions/0072_quiz_tracking_integrity.py'
    spec = importlib.util.spec_from_file_location('quiz_migration', path)
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    assert migration.down_revision == '0071_analytics_hotpath_identity_indexes'
    engine = create_engine('sqlite://')
    with engine.begin() as connection:
        migration.op = Operations(MigrationContext.configure(connection))
        migration.upgrade()
        assert len(inspect(connection).get_table_names()) == 3
        inspector = inspect(connection)
        for model in (models.AnalyticsQuizItemSubmission, models.AnalyticsQuizItemReceipt,
                      models.AnalyticsQuizIntegrityResult):
            actual = {c['name']: c for c in inspector.get_columns(model.__tablename__)}
            assert set(actual) == set(model.__table__.columns.keys())
            for column in model.__table__.columns:
                assert actual[column.name]['nullable'] == column.nullable
                assert getattr(actual[column.name]['type'], 'length', None) == getattr(column.type, 'length', None)
            assert {i['name'] for i in inspector.get_indexes(model.__tablename__)} == {
                i.name for i in model.__table__.indexes}
        migration.downgrade()
        assert inspect(connection).get_table_names() == []
        migration.upgrade()
        assert len(inspect(connection).get_table_names()) == 3


def test_long_opaque_input_id_fits_postgres_slot_column_without_losing_original_id():
    from app.services.learning_analytics.quiz_item_materializer import materialize_quiz_items
    engine = create_engine('sqlite://')
    models.AnalyticsQuizItemSubmission.__table__.create(engine)
    models.AnalyticsQuizItemReceipt.__table__.create(engine)
    input_id = 'opaque_input_' + 'x' * 200
    feat = QuizAttemptFeature('course', 'sv', '1', None, 'unit', 1)
    feat.raw_submissions = [{'event_id': 'e1', 'event_type': 'problem_check', 'event_source': 'server',
                             'submitted_at': datetime(2026, 10, 5), 'problem_usage_key': 'q1', 'context': {},
                             'payload': {'submission': {input_id: {'answer': 'A', 'correct': False,
                                                                  'response_type': 'multiplechoiceresponse'}}}}]
    with Session(engine, autoflush=False) as db:
        materialize_quiz_items(db, feat, attempt_id='a1')
        item = db.query(models.AnalyticsQuizItemSubmission).one()
        assert item.input_id == input_id
        assert len(item.input_slot) <= models.AnalyticsQuizItemSubmission.__table__.c.input_slot.type.length


def test_server_question_definition_hash_is_preserved_when_legacy_label_is_empty():
    from app.services.learning_analytics.quiz_item_materializer import materialize_quiz_items
    engine = create_engine('sqlite://')
    models.AnalyticsQuizItemSubmission.__table__.create(engine)
    models.AnalyticsQuizItemReceipt.__table__.create(engine)
    feat = QuizAttemptFeature('course', 'sv', '1', None, 'unit', 1)
    feat.raw_submissions = [{'event_id': 'event', 'event_type': 'problem_check', 'event_source': 'server',
        'submitted_at': datetime(2026, 10, 7), 'problem_usage_key': 'q',
        'context': {'module': {'original_usage_version': 'native-version'}},
        'payload': {'content_version': 'sha256:' + 'a' * 64, 'submission': {
            'q_2_1': {'answer': 'A', 'correct': True, 'response_type': 'multiplechoiceresponse',
                      'question': '', 'question_hash': 'b' * 64}}}}]
    with Session(engine) as db:
        materialize_quiz_items(db, feat, attempt_id='attempt')
        item = db.query(models.AnalyticsQuizItemSubmission).one()
        assert item.content_version == 'sha256:' + 'a' * 64
        assert item.question_hash == 'b' * 64
