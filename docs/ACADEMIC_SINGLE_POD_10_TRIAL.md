# Single bulk pod, ten processes: tested trial

This trial uses one `ai-server-worker-bulk` pod with ten prefork processes.
It does not scale bulk to five replicas. After the operator observed a recorded
peak of ten overlapping real learning-sync jobs and approved persistence, base
Kubernetes manifests retain one pod/ten processes and a ten-slot coordinator.
The bulk requests remain 300m CPU / 512 MiB; limits remain 1500m CPU / 2 GiB.
Application and Compose defaults are unchanged; Kubernetes uses explicit env
overrides so older values in `ai-server-env` cannot reset the production setting.

The daily account/enrollment and score stages now honor
`ACADEMIC_BULK_SYNC_DISPATCH_WINDOW`. Application default remains four; supported upper
limit is twenty. Ten is shared across Poly/PTCD rather than ten per branch.
Other daily snapshot/export dispatch paths retain their default four slots.
Existing roots can pick up the new value on their next coordinator tick:
no resume, new root, restart of AP, or reset of completed classes is required.

## Tests before rollout

Regression tests verify ten slots, idempotency, fairness across branches, refill
of exactly the freed slots, and lowering the window without cancelling existing
children. A local isolated Redis/Celery probe ran the actual application worker
both with `prefork --concurrency=10` and starting at two processes followed
by targeted `pool_grow(8)`: ten distinct child PIDs reached a barrier
concurrently, completed ten tasks, and the worker shut down normally.
After a live grow, count `pool.processes`; `pool.max-concurrency` may still
report the original startup value.

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

## Temporary trial with current production resources

The operator supplied one bulk pod using 149m CPU / 329 MiB at a point in time,
with requests 300m CPU / 512 MiB and limits 1500m CPU / 2 GiB. This is not a
peak measurement or proof that ten learning-sync jobs fit within 2 GiB. The
requested trial keeps those resources, the bulk Deployment and its running
pod unchanged. No automatic resource increase is performed.

Deploy backend/worker code containing commit `382f7e3` first. No frontend,
CMS-FPT or migration change is needed. From a checkout containing this script:

```bash
bash scripts/try-academic-bulk-10.sh
```

The script first checks the fast coordinator supports ten slots and confirms
one bulk replica and one responding bulk worker. It uses targeted Celery
`pool_grow(8)` to grow the existing two-process worker to ten without replacing
the bulk pod or stopping current tasks. It verifies ten live child PIDs before
setting `ACADEMIC_BULK_SYNC_DISPATCH_WINDOW=10` on the fast Deployment. That
last step rolls the fast coordinator, whose next tick continues the same root.
The ten-slot window is shared across Poly/PTCD; no completed jobs are reset.

The grow is temporary: if the bulk pod restarts, its original two-process
Deployment configuration returns. The coordinator's ten-slot setting remains;
in that case queued jobs execute with two processes until the window is lowered
or another deliberate trial is run. A failed acknowledgement/verification may
leave a partly grown pool; inspect worker stats before retrying. A failed fast
rollout may already have changed the coordinator setting. The script makes no
claim of transactional rollback or production execution by Codex.

Observe real throughput, pod restarts, LMS latency and database/connector
errors. During the trial, use a second terminal:

```bash
watch -n 2 'kubectl -n openedx top pod -l app=ai-server-worker-bulk; kubectl -n openedx get pods -l app=ai-server-worker-bulk -o custom-columns="POD:.metadata.name,RESTARTS:.status.containerStatuses[*].restartCount,LAST_REASON:.status.containerStatuses[*].lastState.terminated.reason"'
```

If memory approaches 2 GiB, restarts increase, `OOMKilled` appears or LMS/DB
latency/errors rise, lower the coordinator window before reassessing resources.
Growing a pool under a Kubernetes limit can OOM the pod before an operator
sees the next metrics sample; this is a real-load experiment, not a guarantee
that production cannot fail.

## Persist after the approved production trial

The production trial recorded ten overlapping learning-sync job intervals in a
five-minute window containing 166 job intervals. A subsequent point sample was
173m CPU / 1199 MiB; an earlier sample reported zero container restarts. These
samples are not a certified peak-memory bound. The operator approved retaining
ten processes with the existing CPU/RAM limits.

Run `bash scripts/persist-academic-bulk-10.sh` on the authorized K8s host. It
stops new bulk deliveries, waits for accepted active/reserved/scheduled tasks
to drain, then saves both explicit bulk env values as ten. Only after draining
does it roll the bulk Deployment and verify ten live child processes. It also
retains the fast coordinator's ten-slot value. CPU/RAM and replicas are not
modified. RollingUpdate may briefly have an old idle pod alongside the new pod;
the steady-state replica count remains one.

A shared operator Redis lease serializes acquisition, draining, rollout and
consumer restoration with other pool trials. Only its owner restores queues
or releases the lease; the lease is refreshed before setting changes and during
draining. An EXIT handler restores the known bulk queues if draining or rollout fails.
A failed rollout can leave the desired setting saved but incompletely applied;
inspect rollout state rather than assuming rollback. The script refuses an
already-paused Deployment and never resets job records or purges queues. Repo
Kubernetes manifests use the same explicit overrides, preserving the setting
on subsequent manifest applications. No backend image rebuild is necessary
solely for this environment/manifest setting change.

## Revert without restarting the bulk pod or pipeline

First lower the coordinator window; already submitted children remain intact:

```bash
kubectl -n openedx set env deploy/ai-server-worker ACADEMIC_BULK_SYNC_DISPATCH_WINDOW=4
kubectl -n openedx rollout status deploy/ai-server-worker --timeout=180s
```

After the current burst finishes, shrink only idle processes on the existing
worker. Celery refuses to shrink enough when too many processes are busy;
wait for them to finish and retry instead of killing tasks:

```bash
kubectl -n openedx exec -i deploy/ai-server-backend -- python - <<'PY'
from app.worker import celery_app
stats = celery_app.control.inspect(timeout=3).stats() or {}
workers = [name for name in stats if name.startswith('worker-bulk@')]
if len(workers) != 1:
    raise SystemExit(f'Expected one bulk worker, found {workers}')
worker = workers[0]
count = len(stats[worker].get('pool', {}).get('processes', []))
if count < 2:
    raise SystemExit(f'Unexpected pool size: {count}')
if count > 2:
    replies = celery_app.control.pool_shrink(count - 2, destination=[worker], reply=True, timeout=5)
    if not any('ok' in item.get(worker, {}) for item in (replies or [])):
        raise SystemExit(f'Shrink not acknowledged; wait for busy tasks and inspect before retry: {replies}')
print('Requested idle pool shrink to two; verify live process count with worker stats.')
PY
```

Do not delete jobs, purge Redis or start another daily root for this tuning.
