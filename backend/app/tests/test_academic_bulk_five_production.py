from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]


def _read(relative_path: str) -> str:
    return (ROOT / relative_path).read_text(encoding="utf-8")


def test_kubernetes_bulk_worker_runs_five_processes_and_dispatches_five_jobs():
    bulk_worker = _read("deploy/k8s/base/worker-bulk.yaml")

    assert 'name: CELERY_BULK_CONCURRENCY\n              value: "5"' in bulk_worker
    assert 'name: ACADEMIC_BULK_SYNC_DISPATCH_WINDOW\n              value: "5"' in bulk_worker


def test_production_env_defaults_to_five_bulk_processes_and_dispatch_slots():
    production_env = _read(".env.production.example")

    assert "CELERY_BULK_CONCURRENCY=5" in production_env
    assert "ACADEMIC_BULK_SYNC_DISPATCH_WINDOW=5" in production_env


def test_fast_coordinator_and_backend_share_the_five_job_window():
    fast_worker = _read("deploy/k8s/base/worker.yaml")
    backend = _read("deploy/k8s/base/backend.yaml")

    expected = 'name: ACADEMIC_BULK_SYNC_DISPATCH_WINDOW\n              value: "5"'
    assert expected in fast_worker
    assert expected in backend


def test_all_connector_runtimes_use_four_attempts_and_minute_retry_schedule():
    manifests = [
        _read("deploy/k8s/base/backend.yaml"),
        _read("deploy/k8s/base/worker.yaml"),
        _read("deploy/k8s/base/worker-bulk.yaml"),
        _read("deploy/k8s/base/worker-heavy.yaml"),
        _read("deploy/k8s/base/worker-analytics.yaml"),
    ]

    for manifest in manifests:
        assert "OPENEDX_CONNECTOR_READ_RETRY_MAX_ATTEMPTS" in manifest
        assert 'value: "4"' in manifest
        assert "OPENEDX_CONNECTOR_READ_RETRY_DELAYS_SECONDS" in manifest
        assert 'value: "60,120,300"' in manifest
