from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
VERSION = '25.9.16.7.2.64.12'


def text(path: str) -> str:
    return (ROOT / path).read_text(encoding='utf-8')


def test_v62_version_and_docs_sync():
    assert f"app_version: str = '{VERSION}'" in text('backend/app/core/config.py')
    assert f'"version": "{VERSION}"' in text('frontend/package.json')
    assert f'NEXT_PUBLIC_APP_VERSION: ${{APP_VERSION:-{VERSION}}}' in text('docker-compose.prod.yml')
    assert 'Question Bank Quiz Creation/Auto-map Workflow Split' in text('README.md')
    assert 'question-bank-quiz-creation-automap-workflow-split.zip' in text('RUN_CURRENT.md')
    assert text('CHANGELOG.md').startswith('## v25.9.16.7.2.64.12 — Question Bank Quiz Creation/Auto-map Workflow Split')


def test_v62_jobs_batch_summary_uses_aggregate_not_n_plus_one():
    jobs = text('backend/app/api/routes/jobs.py')
    assert 'func.count(GenerationBatch.id)' in jobs
    assert '.group_by(GenerationBatch.job_id, GenerationBatch.status, GenerationBatch.phase)' in jobs
    assert 'batch_summaries' in jobs
    assert 'for j in jobs:\n        estimated_raw' in jobs
    old = "db.query(GenerationBatch).filter(GenerationBatch.job_id == j.id).all()"
    assert old not in jobs


def test_v62_question_and_topic_stats_use_sql_aggregate():
    questions = text('backend/app/api/routes/questions.py')
    courses = text('backend/app/api/routes/courses.py')
    assert 'with_entities(Question.status, func.count(Question.id)).group_by(Question.status)' in questions
    assert 'with_entities(Question.draft_error_reason, func.count(Question.id)).group_by(Question.draft_error_reason)' in questions
    assert 'return query.limit(min(max(limit, 1), 300)).all()' in questions
    assert 'func.count(ContentChunk.id).label(\'chunk_count\')' in courses
    assert '.group_by(ContentChunk.topic_id)' in courses
    topic_block = courses.split("def list_topics", 1)[1]
    assert 'for chunk in db.query(ContentChunk).filter(ContentChunk.course_id == course_id).all()' not in topic_block


def test_v62_request_timing_and_audit_window_caps():
    main = text('backend/app/main.py')
    audit = text('backend/app/api/routes/audit.py')
    assert "response.headers['X-Process-Time-Ms']" in main
    assert 'time.perf_counter()' in main
    assert 'min(500, max(100, page * page_size * 5))' in audit
    assert 'max(1000, page * page_size * 10)' not in audit


def test_v62_query_hotspot_gate_and_scripts():
    service = text('backend/app/services/query_hotspot.py')
    health = text('backend/app/api/routes/health.py')
    script = text('scripts/query-hotspot-report.sh')
    runtime = text('scripts/uat-runtime-verify.sh')
    build_gate = text('scripts/uat-build-gate.sh')
    assert 'class QueryHotspotService' in service
    assert 'static_source_scan_no_db_no_mutation' in service
    assert "/health/query-hotspots" in health and "QueryHotspotReport" in health
    assert 'QueryHotspotService().report' in health
    assert '/health/query-hotspots' in script
    assert 'QUERY_HOTSPOT_SUMMARY.md' in script
    assert 'QUERY_HOTSPOTS /health/query-hotspots' in runtime
    assert 'scripts/query-hotspot-report.sh' in build_gate


def test_v62_no_new_migration():
    assert (ROOT / 'backend/alembic/versions/0052_v25_9_16_7_2_27_learning_behavior_logic_calibration.py').exists()
    assert not list((ROOT / 'backend/alembic/versions').glob('0053*.py'))
