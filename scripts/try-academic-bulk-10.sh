#!/usr/bin/env bash
# Temporary operator trial: retain current bulk pod, resources and Deployment.
set -Eeuo pipefail
TASK_NAMESPACE="${TASK_NAMESPACE:-openedx}"

kubectl -n "$TASK_NAMESPACE" exec -i deploy/ai-server-worker -- python - <<'PY'
import inspect
from app.services.academic.daily_academic_pipeline import _run_class_stage
from app.services.academic.daily_pipeline_state import select_global_dispatch_targets
if ('academic_bulk_sync_dispatch_window' not in inspect.getsource(_run_class_stage)
        or len(select_global_dispatch_targets([str(i) for i in range(12)], {},
                                             active_count=0, window=10)) != 10):
    raise SystemExit('Deploy code containing commit 382f7e3 to the fast worker first.')
print('Fast coordinator supports ten shared slots.')
PY

replicas="$(kubectl -n "$TASK_NAMESPACE" get deploy ai-server-worker-bulk -o jsonpath='{.spec.replicas}')"
if [[ "$replicas" != 1 ]]; then
  echo "Expected one bulk replica, found $replicas; no trial applied." >&2
  exit 1
fi
kubectl -n "$TASK_NAMESPACE" top pod -l app=ai-server-worker-bulk
kubectl -n "$TASK_NAMESPACE" get deploy ai-server-worker-bulk \
  -o jsonpath='{.spec.replicas}{" replicas\n"}{.spec.template.spec.containers[0].resources}{"\n"}'

# Target only the one responding bulk worker. Do not restart it or interrupt
# its current tasks. pool_grow is temporary; a pod restart restores its default.
kubectl -n "$TASK_NAMESPACE" exec -i deploy/ai-server-backend -- python - <<'PY'
import time
from app.worker import celery_app
from app.core.redis_client import get_redis_client
client = get_redis_client()
lease = client.lock('ai-server:operator:bulk-pool-trial', timeout=90, blocking=False)
if not lease.acquire(blocking=False):
    raise SystemExit('Another bulk pool trial is running; no change applied.')
try:
    stats = celery_app.control.inspect(timeout=3).stats() or {}
    workers = [name for name in stats if name.startswith('worker-bulk@')]
    if len(workers) != 1:
        raise SystemExit(f'Expected one responding bulk worker, found {workers}; no trial applied.')
    worker = workers[0]
    pool = stats[worker].get('pool', {})
    count = len(pool.get('processes', []))
    if count not in (2, 10):
        raise SystemExit(f'Expected two or ten existing processes, found {count}; no trial applied.')
    if stats[worker].get('autoscaler'):
        raise SystemExit('Autoscale worker detected; pool_grow trial is not applicable.')
    if count == 2:
        replies = celery_app.control.pool_grow(8, destination=[worker], reply=True, timeout=5)
        if not any('ok' in item.get(worker, {}) for item in (replies or [])):
            raise SystemExit(f'Worker did not acknowledge pool_grow: {replies}; window unchanged. Inspect pool before retry.')
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        replies = celery_app.control.inspect(timeout=3, destination=[worker]).stats() or {}
        count = len(replies.get(worker, {}).get('pool', {}).get('processes', []))
        if count == 10:
            print(f'Verified ten live child processes in {worker}; bulk pod/resources unchanged.', flush=True)
            break
        time.sleep(1)
    else:
        raise SystemExit('Ten live processes were not verified; window unchanged. Inspect worker/restarts before retry.')
finally:
    lease.release()
    client.close()
PY

kubectl -n "$TASK_NAMESPACE" set env deploy/ai-server-worker ACADEMIC_BULK_SYNC_DISPATCH_WINDOW=10
kubectl -n "$TASK_NAMESPACE" rollout status deploy/ai-server-worker --timeout=180s
echo 'Trial enabled. Bulk Deployment/resources unchanged; fast coordinator window=10.'
echo 'Monitor: kubectl -n openedx top pod -l app=ai-server-worker-bulk'
echo 'If fast-worker rollout fails, inspect it: its window may already have changed.'
