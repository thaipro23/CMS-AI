from pathlib import Path

import sys
import types

# The focused SQLite test does not call OpenAI; keep collection independent from
# optional runtime SDK availability in lightweight CI environments.
if 'openai' not in sys.modules:
    openai_stub = types.ModuleType('openai')
    class _AsyncOpenAI:  # pragma: no cover - import shim only
        pass
    openai_stub.AsyncOpenAI = _AsyncOpenAI
    sys.modules['openai'] = openai_stub

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from app.db.session import Base
from app.models import course, question, question_bank, job  # noqa: F401
from app.models.question import Question, QuestionReviewLog
from app.services.question_bank_service import VersionedQuestionBankService


ROOT = Path(__file__).resolve().parents[3]


def make_session():
    engine = create_engine('sqlite+pysqlite:///:memory:')
    Base.metadata.create_all(bind=engine)
    return engine, sessionmaker(bind=engine)()


def make_bank(db):
    svc = VersionedQuestionBankService(db)
    dept = svc.create_department(code='IT', name='CNTT')
    subject = svc.create_subject(department_id=dept.id, code='WEB107', name='WEB107')
    chapter = svc.create_chapter(subject_id=subject.id, chapter_no=1, title='Bài 1')
    version = svc.create_bank_version(subject_id=subject.id, chapter_id=chapter.id, version_code='v1.0', title='WEB107 B1')
    return svc, subject, chapter, version


def make_question(subject, chapter, version, *, qid: str, status: str):
    return Question(
        id=qid,
        course_id='bank:WEB107',
        subject_id=subject.id,
        subject_chapter_id=chapter.id,
        bank_version_id=version.id,
        difficulty='easy',
        question_text=f'Câu {qid}?',
        option_a='A', option_b='B', option_c='C', option_d='D',
        correct_answer='A',
        status=status,
        question_family_id=f'fam-{qid}',
    )


def test_bulk_review_canonicalizes_legacy_selection_and_is_idempotent():
    engine, db = make_session()
    try:
        svc, subject, chapter, version = make_bank(db)
        q1 = make_question(subject, chapter, version, qid='q1', status='needs_review')
        q2 = make_question(subject, chapter, version, qid='q2', status='pending_review')
        q3 = make_question(subject, chapter, version, qid='q3', status='approved')
        db.add_all([q1, q2, q3])
        db.commit()

        result = svc.bulk_review_bank_questions(
            bank_version_id=version.id,
            action='approve',
            question_ids=['q1', 'q2', 'q3', 'missing', 'q2'],
            actor='reviewer',
        )

        assert result['changed_count'] == 2
        assert set(result['changed_question_ids']) == {'q1', 'q2'}
        skipped = {item['question_id']: item['reason'] for item in result['skipped']}
        assert skipped['q3'] == 'already_in_target_status'
        assert skipped['missing'] == 'question_not_found_in_bank_version'
        assert db.get(Question, 'q1').status == 'approved'
        assert db.get(Question, 'q2').status == 'approved'
        assert db.query(QuestionReviewLog).filter(QuestionReviewLog.question_id.in_(['q1', 'q2'])).count() == 2
    finally:
        db.close()
        engine.dispose()


def test_bulk_review_savepoint_keeps_good_rows_when_one_legacy_row_fails_db_flush():
    engine, db = make_session()
    try:
        svc, subject, chapter, version = make_bank(db)
        good1 = make_question(subject, chapter, version, qid='good1', status='pending_review')
        bad = make_question(subject, chapter, version, qid='bad', status='pending_review')
        good2 = make_question(subject, chapter, version, qid='good2', status='pending_review')
        db.add_all([good1, bad, good2])
        db.commit()

        # Simulate a legacy DB-level problem attached to one historical row.
        db.execute(text("""
            CREATE TRIGGER fail_bad_review_log
            BEFORE INSERT ON ai_question_review_logs
            WHEN NEW.question_id = 'bad'
            BEGIN
              SELECT RAISE(ABORT, 'legacy review-log failure');
            END;
        """))
        db.commit()

        result = svc.bulk_review_bank_questions(
            bank_version_id=version.id,
            action='approve',
            question_ids=['good1', 'bad', 'good2'],
            actor='reviewer',
        )

        assert result['changed_count'] == 2
        assert set(result['changed_question_ids']) == {'good1', 'good2'}
        assert any(item['question_id'] == 'bad' and item['reason'] == 'database_row_error' and item.get('error_type') == 'IntegrityError' for item in result['skipped'])
        assert db.get(Question, 'good1').status == 'approved'
        assert db.get(Question, 'good2').status == 'approved'
        assert db.get(Question, 'bad').status == 'pending_review'
    finally:
        db.close()
        engine.dispose()


def test_release_readiness_blocks_unknown_legacy_question_status():
    engine, db = make_session()
    try:
        svc, subject, chapter, version = make_bank(db)
        approved = make_question(subject, chapter, version, qid='approved', status='approved')
        legacy = make_question(subject, chapter, version, qid='legacy', status='legacy_weird_state')
        db.add_all([approved, legacy])
        db.commit()

        readiness = svc.release_readiness(bank_version_id=version.id)
        assert readiness['can_create_release'] is False
        assert readiness['stats']['unknown_status_count'] == 1
        assert readiness['stats']['unresolved_count'] == 1
        check = next(item for item in readiness['checks'] if item['code'] == 'legacy_question_status')
        assert check['status'] == 'fail'
    finally:
        db.close()
        engine.dispose()


def test_deploy_readiness_and_legacy_hygiene_contract_are_shipped():
    health = (ROOT / 'backend/app/api/routes/health.py').read_text(encoding='utf-8')
    backend_yaml = (ROOT / 'deploy/k8s/base/backend.yaml').read_text(encoding='utf-8')
    migration = (ROOT / 'backend/alembic/versions/0059_v25_9_16_7_2_64_37_question_bank_legacy_hygiene.py').read_text(encoding='utf-8')
    script = (ROOT / 'scripts/question-bank-data-health.py').read_text(encoding='utf-8')
    uat_gate = (ROOT / 'scripts/uat-build-gate.sh').read_text(encoding='utf-8')
    review_pack = (ROOT / 'scripts/claude-code-review-pack.sh').read_text(encoding='utf-8')

    dockerfile = (ROOT / 'backend/Dockerfile.prod').read_text(encoding='utf-8')

    assert "@router.get('/health/ready')" in health
    assert 'DATABASE_SCHEMA_MISMATCH' in health
    assert "_EXPECTED_ALEMBIC_REVISION = '0061_v25_9_16_7_2_64_39'" in health
    assert 'path: /api/health/ready' in backend_yaml
    assert "revision = '0059_v25_9_16_7_2_64_37'" in migration
    assert "status = 'pending_review'" in migration
    assert 'published_lifecycle_status_drift_count' in script
    assert "EXPECTED_ALEMBIC_HEAD='0061_v25_9_16_7_2_64_39'" in uat_gate
    assert "EXPECTED_ALEMBIC_HEAD='0061_v25_9_16_7_2_64_39'" in review_pack
    assert 'alembic -c alembic.ini heads' in uat_gate
    assert 'COPY scripts/question-bank-data-health.py ./scripts/question-bank-data-health.py' in dockerfile


def test_legacy_hygiene_migration_repairs_safe_known_values_without_guessing_unknowns():
    import importlib.util

    engine = create_engine('sqlite+pysqlite:///:memory:')
    try:
        with engine.begin() as conn:
            conn.execute(text('''
                CREATE TABLE ai_questions (
                    id TEXT PRIMARY KEY,
                    bank_version_id TEXT,
                    status TEXT,
                    openedx_publish_status TEXT,
                    publish_status TEXT,
                    is_retired BOOLEAN,
                    is_duplicate BOOLEAN,
                    question_revision_no INTEGER,
                    repair_attempt_count INTEGER,
                    openedx_manual_action_required BOOLEAN
                )
            '''))
            conn.execute(text('''
                CREATE TABLE ai_question_review_logs (
                    id TEXT PRIMARY KEY,
                    question_id TEXT,
                    old_status TEXT,
                    new_status TEXT
                )
            '''))
            conn.execute(text('''
                CREATE TABLE ai_question_search_documents (
                    question_id TEXT PRIMARY KEY,
                    status TEXT
                )
            '''))
            conn.execute(text('''
                INSERT INTO ai_questions
                  (id, bank_version_id, status, openedx_publish_status, publish_status,
                   is_retired, is_duplicate, question_revision_no, repair_attempt_count,
                   openedx_manual_action_required)
                VALUES
                  ('q-needs', 'v1', ' needs_review ', NULL, NULL, NULL, NULL, NULL, -1, NULL),
                  ('q-error', 'v1', 'ERROR', NULL, NULL, 0, 0, 1, 0, 0),
                  ('q-approved', 'v1', ' Approved ', NULL, NULL, 0, 0, 1, 0, 0),
                  ('q-published', 'v1', 'approved', 'verified', NULL, 0, 0, 1, 0, 0),
                  ('q-unknown', 'v1', 'legacy_custom_state', NULL, NULL, 0, 0, 1, 0, 0)
            '''))
            conn.execute(text("INSERT INTO ai_question_review_logs VALUES ('r1','q-needs','',NULL)"))
            conn.execute(text("INSERT INTO ai_question_search_documents VALUES ('q-needs','needs_review')"))

        migration_path = ROOT / 'backend/alembic/versions/0059_v25_9_16_7_2_64_37_question_bank_legacy_hygiene.py'
        spec = importlib.util.spec_from_file_location('migration_0059_test', migration_path)
        module = importlib.util.module_from_spec(spec)
        assert spec and spec.loader
        spec.loader.exec_module(module)

        class _Op:
            def __init__(self, bind):
                self._bind = bind
            def get_bind(self):
                return self._bind

        with engine.begin() as conn:
            module.op = _Op(conn)
            module.upgrade()

        with engine.connect() as conn:
            statuses = dict(conn.execute(text('SELECT id, status FROM ai_questions')).all())
            assert statuses['q-needs'] == 'pending_review'
            assert statuses['q-error'] == 'draft_error'
            assert statuses['q-approved'] == 'approved'
            assert statuses['q-published'] == 'published'
            assert statuses['q-unknown'] == 'legacy_custom_state'

            row = conn.execute(text("SELECT is_retired, is_duplicate, question_revision_no, repair_attempt_count, openedx_manual_action_required FROM ai_questions WHERE id='q-needs'" )).one()
            assert tuple(row) == (0, 0, 1, 0, 0)

            review = conn.execute(text("SELECT old_status, new_status FROM ai_question_review_logs WHERE id='r1'" )).one()
            assert tuple(review) == ('legacy_unknown', 'legacy_unknown')
            search_status = conn.execute(text("SELECT status FROM ai_question_search_documents WHERE question_id='q-needs'" )).scalar_one()
            assert search_status == 'pending_review'
    finally:
        engine.dispose()
