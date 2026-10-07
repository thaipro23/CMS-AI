"""Opt-in actual Celery probe; deliberately not a production load benchmark."""
import json
import os
import subprocess
import sys
import time
from urllib.parse import urlsplit, urlunsplit
from uuid import uuid4

import pytest
import redis
from celery import Celery

pytestmark = pytest.mark.integration


@pytest.mark.parametrize('initial_concurrency', [2, 10])
def test_single_actual_worker_runs_ten_prefork_tasks_concurrently(tmp_path, initial_concurrency):
    if os.environ.get('RUN_BULK_PREFORK_PROBE') != '1':
        pytest.skip('Set RUN_BULK_PREFORK_PROBE=1 with a disposable Redis')
    url = os.environ.get('REDIS_URL')
    if not url:
        pytest.skip('Disposable Redis URL required')
    parts = urlsplit(url)
    url = urlunsplit((parts.scheme, parts.netloc, '/15', parts.query, parts.fragment))
    token = uuid4().hex
    queue, worker_name = f'ci-bulk10-{token}', f'bulk10-probe@{token}'
    key = f'ci:bulk10:{token}:started'
    client = redis.Redis.from_url(url)
    celery_app = Celery('bulk10-probe-client', broker=url, backend=url)
    env = dict(os.environ, REDIS_URL=url, REDIS_CACHE_URL='',
               DATABASE_URL=f'sqlite+pysqlite:///{tmp_path}/probe.sqlite',
               APP_ENV='dev', LOCAL_STORAGE_PATH=str(tmp_path),
               C_FORCE_ROOT='1')
    log_path = tmp_path / 'worker.log'
    results = []
    with log_path.open('w') as log:
        worker = subprocess.Popen([
            sys.executable, '-m', 'celery', '-A',
            'app.tests.integration.bulk_prefork_probe:celery_app', 'worker',
            '--pool=prefork', f'--concurrency={initial_concurrency}', f'--queues={queue}',
            f'--hostname={worker_name}', '--prefetch-multiplier=1',
            '--without-gossip', '--without-mingle', '--without-heartbeat',
            '--loglevel=WARNING',
        ], env=env, stdout=log, stderr=subprocess.STDOUT)
        try:
            deadline = time.monotonic() + 25
            stats = None
            while time.monotonic() < deadline:
                assert worker.poll() is None, log_path.read_text()
                replies = celery_app.control.inspect(timeout=0.5, destination=[worker_name]).stats()
                if replies and worker_name in replies:
                    stats = replies[worker_name]
                    break
                time.sleep(0.1)
            assert stats is not None, log_path.read_text()
            assert len(stats['pool']['processes']) == initial_concurrency
            if initial_concurrency < 10:
                replies = celery_app.control.pool_grow(
                    10 - initial_concurrency, destination=[worker_name], reply=True, timeout=3)
                assert any('ok' in item.get(worker_name, {}) for item in replies)
                deadline = time.monotonic() + 15
                while time.monotonic() < deadline:
                    replies = celery_app.control.inspect(timeout=0.5, destination=[worker_name]).stats()
                    if replies and len(replies[worker_name]['pool']['processes']) == 10:
                        break
                    time.sleep(0.1)
                assert replies and len(replies[worker_name]['pool']['processes']) == 10
            results = [celery_app.send_task('ci_bulk_prefork_probe', args=[key, 10], queue=queue)
                       for _ in range(10)]
            values = [result.get(timeout=25) for result in results]
            assert len({value['pid'] for value in values}) == 10
            assert client.scard(key) == 10
            assert worker.poll() is None
            print(json.dumps({'single_worker': worker_name, 'initial_concurrency': initial_concurrency,
                              'concurrency': 10,
                              'unique_child_pids': len({v['pid'] for v in values}),
                              'completed': len(values),
                              'min_child_peak_rss_mib': min(v['peak_rss_mib'] for v in values),
                              'max_child_peak_rss_mib': max(v['peak_rss_mib'] for v in values),
                              'real_learning_sync_load': False}))
        finally:
            worker.terminate()
            try:
                worker.wait(timeout=10)
            except subprocess.TimeoutExpired:
                worker.kill()
                worker.wait(timeout=5)
            for result in results:
                result.forget()
            client.delete(key, queue)
            client.close()
    assert worker.returncode == 0, log_path.read_text()
