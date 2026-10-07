#!/usr/bin/env bash
# Save the approved single-pod setting without terminating accepted bulk work.
set -Eeuo pipefail
TASK_NAMESPACE="${TASK_NAMESPACE:-openedx}"
TASK_POOL_TOKEN="$(kubectl -n "$TASK_NAMESPACE" exec deploy/ai-server-backend -- python -c 'from uuid import uuid4; print(uuid4().hex)')"

bulk_control() {
  kubectl -n "$TASK_NAMESPACE" exec -i deploy/ai-server-backend -- python - "$1" "$TASK_POOL_TOKEN" <<'PY'
import sys
import time
from app.worker import celery_app
from app.core.redis_client import get_redis_client

action = sys.argv[1]
token = sys.argv[2]
client = get_redis_client()
key = 'ai-server:operator:bulk-pool-trial'
if action == 'acquire':
    if not client.set(key, token, nx=True, ex=1800):
        raise SystemExit('Another operator pool action is running; no setting applied.')
    raise SystemExit(0)
if action == 'release':
    client.eval("if redis.call('get',KEYS[1]) == ARGV[1] then return redis.call('del',KEYS[1]) else return 0 end", 1, key, token)
    raise SystemExit(0)

def renew():
    owned = client.eval("if redis.call('get',KEYS[1]) == ARGV[1] then return redis.call('expire',KEYS[1],ARGV[2]) else return 0 end", 1, key, token, 1800)
    if not owned:
        raise SystemExit('Operator lease not owned; refusing worker/consumer changes.')

if action == 'restore' and client.get(key) != token:
    print('Lease not owned; consumer restoration skipped.', flush=True)
    raise SystemExit(0)
renew()
if action == 'renew':
    raise SystemExit(0)
stats = celery_app.control.inspect(timeout=3).stats() or {}
workers = [name for name in stats if name.startswith('worker-bulk@')]
queues = ('sync-bulk', 'sync')

def consumer(method, worker, queue):
    replies = getattr(celery_app.control, method)(
        queue, destination=[worker], reply=True, timeout=3)
    if not any('ok' in item.get(worker, {}) for item in (replies or [])):
        raise SystemExit(f'{method} not acknowledged for {worker}/{queue}: {replies}')

if action == 'restore':
    for worker in workers:
        for queue in queues:
            consumer('add_consumer', worker, queue)
    print('Bulk queues restored on:', workers, flush=True)
    raise SystemExit(0 if workers else 1)
if len(workers) != 1:
    raise SystemExit(f'Expected one responding bulk worker, found {workers}.')
worker = workers[0]
if action == 'verify':
    count = len(stats[worker].get('pool', {}).get('processes', []))
    if count != 10:
        raise SystemExit(f'Expected ten live child processes, found {count}.')
    print('Verified persisted ten-process pool:', worker, flush=True)
    raise SystemExit(0)
if action != 'drain':
    raise SystemExit(f'Unknown action: {action}')
for queue in queues:
    consumer('cancel_consumer', worker, queue)
print('Stopped new deliveries; accepted bulk tasks continue.', flush=True)
deadline = time.monotonic() + 600
empty_checks = 0
while time.monotonic() < deadline:
    renew()
    counts = {}
    for kind in ('active', 'reserved', 'scheduled'):
        replies = getattr(celery_app.control.inspect(timeout=3, destination=[worker]), kind)()
        if not replies or worker not in replies:
            raise SystemExit(f'No {kind} reply; refusing to replace the bulk pod.')
        counts[kind] = len(replies[worker])
    print('Drain:', counts, flush=True)
    empty_checks = empty_checks + 1 if not any(counts.values()) else 0
    if empty_checks >= 2:
        break
    time.sleep(3)
else:
    raise SystemExit('Drain timed out; Deployment remains unchanged.')
PY
}

replicas="$(kubectl -n "$TASK_NAMESPACE" get deploy ai-server-worker-bulk -o jsonpath='{.spec.replicas}')"
if [[ "$replicas" != 1 ]]; then
  echo "Expected one bulk replica, found $replicas; no setting applied." >&2
  exit 1
fi
paused="$(kubectl -n "$TASK_NAMESPACE" get deploy ai-server-worker-bulk -o jsonpath='{.spec.paused}')"
if [[ "$paused" == true ]]; then
  echo 'Bulk Deployment is paused; inspect its pending changes before proceeding.' >&2
  exit 1
fi
cleanup() {
  local task_exit_code=$?
  trap - EXIT
  if ! bulk_control restore; then
    echo 'WARNING: queue restoration failed; inspect bulk consumers.' >&2
    task_exit_code=1
  fi
  if ! bulk_control release; then task_exit_code=1; fi
  exit "$task_exit_code"
}
trap cleanup EXIT
bulk_control acquire
bulk_control drain
bulk_control renew
kubectl -n "$TASK_NAMESPACE" set env deploy/ai-server-worker-bulk \
  CELERY_BULK_CONCURRENCY=10 ACADEMIC_BULK_SYNC_DISPATCH_WINDOW=10
kubectl -n "$TASK_NAMESPACE" rollout status deploy/ai-server-worker-bulk --timeout=180s
verified=0
for _attempt in {1..12}; do
  if bulk_control verify; then verified=1; break; fi
  sleep 3
done
if [[ "$verified" != 1 ]]; then
  echo 'Deployment setting was saved, but the new ten-process pool was not verified.' >&2
  exit 1
fi
bulk_control renew
kubectl -n "$TASK_NAMESPACE" set env deploy/ai-server-worker ACADEMIC_BULK_SYNC_DISPATCH_WINDOW=10
kubectl -n "$TASK_NAMESPACE" rollout status deploy/ai-server-worker --timeout=180s
echo 'Saved: one steady-state bulk pod, ten processes and ten dispatch slots; CPU/RAM unchanged.'
