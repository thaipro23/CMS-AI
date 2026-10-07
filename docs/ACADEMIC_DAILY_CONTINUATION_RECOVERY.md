# Daily pipeline continuation recovery

A successfully published coordinator message waiting in the bulk queue used to
consume the same five-attempt budget as a failed broker publish. The watchdog
could therefore fail an otherwise valid root while leaving its scope parents
running.

The fix separates `publish_failure_count` from dispatch attempts. Only five
consecutive broker publish failures exhaust dispatch recovery; a successful
publish or worker acceptance resets that counter. The root still has a 24-hour
runtime limit, independent of its message lease and class-stage retry rounds.

Daily start, coordinator and continuation watchdog tasks use the existing
`sync-fast` queue. Class synchronization stays on `sync-bulk`, with the existing
four-job dispatch window. Published root messages get a confirmation lease no
shorter than Celery's visibility timeout before the watchdog republishes them.

Scheduler, coordinator, watchdog and operator resume share a Redis lease with
an owner token and a 240-second TTL. PostgreSQL advisory locking remains the
authoritative fallback and uses a dedicated connection held across commits.
The configured coordinator hard time limit remains 180 seconds. Failed roots
propagate their status/error to unfinished scope parents; completed child work
remains completed. Each watchdog scan also reconciles unfinished scopes of
already failed roots, repairing older failures and crashes between commits.
Late messages do not overwrite terminal diagnostics.

## Deploy and resume

Build the CMS-AI backend image and deploy it to backend, all workers and beat.
No frontend change, database migration or CMS-FPT build is needed for this fix.
Ensure the fast worker consumes `interactive,sync-fast`, as in the existing
production manifests.

After deployment, this discovers the root for the current Vietnam calendar day
and resumes it from its saved stage. No UUID is required. To select a specific
day, add `run_date_vn="2026-10-07"` to the function call.

```bash
kubectl -n openedx exec -i deploy/ai-server-backend -- python - <<'PY'
import json
from app.worker import celery_app
from app.services.academic.daily_academic_pipeline import resume_daily_academic_pipeline

result = resume_daily_academic_pipeline(
    celery_app,
    actor='kubectl-operator',
)
print(json.dumps(result, ensure_ascii=False))
if not result.get('ok'):
    raise SystemExit(1)
PY
```

`ambiguous_daily_root` refuses multiple roots for the selected day and returns
their IDs/statuses without changing any jobs. `root_job_not_found` means there
is no exact daily root for that date. Scope parents are never selected.

`resumed` means the same root was queued from its saved stage. `already_running`
means another call already resumed it; no second message is published.
`coordinator_busy` means another coordinator holds the lease; repeat after it
finishes. `dispatch_pending` means the durable resume intent is saved but the
broker publish failed; the watchdog can retry it.

Resume refuses business/stage failures, roots older than 24 hours and roots
superseded by an active or newer daily run. It preserves frozen scope, child
IDs, completed work, retry rounds and saved artifacts. It does not restart AP,
course matching or enrollment when the saved stage is score update.

## Verification

Regression tests cover successful messages exceeding five dispatches, bounded
broker failures, queue leases, runtime expiry, scope failure propagation,
resume idempotency/refusals, and preservation of child results and artifacts.
CI integration tests use actual Redis and PostgreSQL to verify lease ownership
and advisory-lock lifetime across commits.
