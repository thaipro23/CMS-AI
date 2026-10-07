# Single bulk pod, ten processes: tested trial

This trial uses one `ai-server-worker-bulk` pod with ten prefork processes.
It does not scale bulk to five replicas. Base Kubernetes manifests deliberately
remain one pod/two processes until the operator evaluates production resources.

The daily account/enrollment and score stages now honor
`ACADEMIC_BULK_SYNC_DISPATCH_WINDOW`. Default remains four; supported upper
limit is twenty. Ten is shared across Poly/PTCD rather than ten per branch.
Other daily snapshot/export dispatch paths retain their default four slots.
Existing roots can pick up the new value on their next coordinator tick:
no resume, new root, restart of AP, or reset of completed classes is required.

## Tests before rollout

Regression tests verify ten slots, idempotency, fairness across branches, refill
of exactly the freed slots, and lowering the window without cancelling existing
children. A local isolated Redis/Celery probe ran the actual application worker
with `prefork --concurrency=10`: ten distinct child PIDs reached a barrier
concurrently, completed ten tasks, and the worker shut down normally.

The probe does not contact LMS or write student records. Its child peak RSS was
about 169 MiB each, for application imports and the small probe only; shared
pages make a simple sum of RSS unsuitable for exact pod memory sizing. It ran
without a Kubernetes pod's 2 GiB memory constraint. It does not establish peak
RAM, LMS/database capacity or latency during real learning synchronization.
Do not present this result as proof that production cannot OOM.

Reproduce with disposable Redis only:

```bash
cd backend
RUN_BULK_PREFORK_PROBE=1 REDIS_URL=redis://127.0.0.1:6379/0 \
  pytest -q -s app/tests/integration/test_bulk_prefork_probe.py
```

## Read-only production preflight

Before enabling ten processes, inspect actual resources and recent restarts:

```bash
kubectl -n openedx top pod -l app=ai-server-worker-bulk
kubectl -n openedx get pods -l app=ai-server-worker-bulk \
  -o custom-columns='POD:.metadata.name,RESTARTS:.status.containerStatuses[*].restartCount,LAST_REASON:.status.containerStatuses[*].lastState.terminated.reason'
kubectl -n openedx get deploy ai-server-worker-bulk \
  -o jsonpath='{.spec.replicas}{" replicas\n"}{.spec.template.spec.containers[0].resources}{"\n"}'
```

Capture the pod's aggregate memory and peak while real jobs are running:

```bash
kubectl -n openedx exec -i deploy/ai-server-worker-bulk -- python - <<'PY'
from pathlib import Path
for name in ('memory.current', 'memory.peak', 'memory.max', 'memory.events',
             'memory/memory.usage_in_bytes', 'memory/memory.max_usage_in_bytes',
             'memory/memory.limit_in_bytes', 'memory/memory.failcnt'):
    path = Path('/sys/fs/cgroup') / name
    if path.exists():
        print(name, path.read_text().strip())
PY
```

Also inspect LMS and PostgreSQL resources in the actual deployment before
increasing parallel connector requests. Current manifests limit the bulk pod
to 1.5 CPU / 2 GiB; the resource budget for ten must be chosen from actual
measurements and available node capacity. No fixed RAM value is certified by
the local probe. Keep the bulk worker at two until the preflight is assessed.

## Enable only after resource/load evaluation

Deploy the backend code to backend/workers/beat first. No frontend, CMS-FPT or
migration change is required. Following commands are a planned operator action,
not a report of changes already made to production. Choose suitable pod CPU/RAM
before this step; it intentionally does not silently enlarge limits or switch
the current 2 GiB pod to ten processes.

After the resource preflight has been assessed and suitable limits are already
deployed, change concurrency and replicas in one Deployment patch. This patch
does not change the resource limits:

```bash
kubectl -n openedx patch deploy ai-server-worker-bulk --type=strategic -p '
{"spec":{"replicas":1,"template":{"spec":{"containers":[
{"name":"worker-bulk","env":[{"name":"CELERY_BULK_CONCURRENCY","value":"10"}]}
]}}}}'
kubectl -n openedx rollout status deploy/ai-server-worker-bulk --timeout=180s
kubectl -n openedx set env deploy/ai-server-worker \
  ACADEMIC_BULK_SYNC_DISPATCH_WINDOW=10
kubectl -n openedx rollout status deploy/ai-server-worker --timeout=180s
```

The existing manifest's bulk worker default is two even if the Secret says ten;
the explicit container environment override above is required. The coordinator
runs in the fast worker, whose explicit four-slot override must also be changed.
Inspect worker stats for actual pool max-concurrency; replicas alone do not
prove ten execution slots. Ensure only one bulk pod is alive after rollout.
Observe real job throughput, worker memory/CPU, LMS latency, failed job count
and database/connector timeouts before keeping the setting.

## Revert without restarting the pipeline

First lower the coordinator window. Already submitted children remain intact:

```bash
kubectl -n openedx set env deploy/ai-server-worker \
  ACADEMIC_BULK_SYNC_DISPATCH_WINDOW=4
kubectl -n openedx rollout status deploy/ai-server-worker --timeout=180s
```

Let running jobs drain, then return the single bulk worker to two processes:

```bash
kubectl -n openedx set env deploy/ai-server-worker-bulk CELERY_BULK_CONCURRENCY=2
kubectl -n openedx rollout status deploy/ai-server-worker-bulk --timeout=180s
```

Do not delete jobs, purge Redis or start another daily root for this tuning.
