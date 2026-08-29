from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
VERSION = '25.9.16.7.2.64.16.5.5'


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding='utf-8')


def test_version_is_synchronized_across_runtime_artifacts():
    for path in (
        'backend/app/core/config.py',
        'frontend/package.json',
        'frontend/package-lock.json',
        'frontend/Dockerfile',
        'docker-compose.prod.yml',
        '.env.example',
        '.env.production.example',
        'README.md',
        'RUN_CURRENT.md',
    ):
        assert VERSION in read(path), path


def test_release_keeps_intentional_0053_alembic_head():
    assert (ROOT / 'backend/alembic/versions/0053_v25_9_16_7_2_64_16_5_4_diff_idempotency.py').exists()
    newer = list((ROOT / 'backend/alembic/versions').glob('0054_*.py'))
    assert newer == []


def test_worker_pool_is_split_by_workload():
    compose = read('docker-compose.prod.yml')
    assert 'worker-heavy:' in compose
    assert 'worker-analytics:' in compose
    assert '--queues=interactive,sync' in compose
    assert '--queues=generation,exports' in compose
    assert '--queues=analytics' in compose


def test_frontend_runtime_has_timeout_cancel_and_backoff():
    api = read('frontend/lib/api.ts')
    assert 'timeoutMs?: number' in api
    assert 'AbortController' in api
    assert 'RETRYABLE_STATUS_CODES' in api
    assert 'backoffMultiplier' in api
    assert 'ai:auth-expired' in api


def test_large_teacher_export_is_background_only_and_error_is_public_safe():
    route = read('backend/app/api/routes/academic.py')
    worker = read('backend/app/worker.py')
    task = worker[worker.index("def academic_teacher_report_job_task"):worker.index("@celery_app.task(name='analytics_ingest_task')")]
    assert 'TEACHER_EXPORT_REQUIRES_BACKGROUND_JOB' in route
    assert '_write_training_teacher_report_xlsx(report, path)' in task
    assert 'ACADEMIC_TEACHER_REPORT_FAILED' in task
    assert 'job.error_message = str(exc)' not in task


def test_performance_reliability_gate_is_integrated_into_review_and_uat():
    for path in ('scripts/claude-code-review-pack.sh', 'scripts/uat-build-gate.sh'):
        source = read(path)
        assert 'performance-worker-reliability-report.sh' in source
        assert 'PERFORMANCE_WORKER_RELIABILITY' in source
