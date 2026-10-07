# Redis teacher overview

Teacher overview pages and their filtered KPI summary are cached for 45 seconds.
The key contains the authenticated user, current academic access decision,
permissions, course grants and every report argument. The same captured access
decision is used for both the key and computation. Permissions are resolved on
every hit. Pages, Poly/PTCD, campuses, platform and searches cannot share a key.

`fresh=true` bypasses Redis and the existing PostgreSQL materialized report.
Details, student lists, exports and restricted scheduled report builds bypass
this page cache. Mail-send totals are still attached live after the cache read.
`cache.redis_status` is `hit` or `miss` when Redis successfully participates.

Academic ORM writes, ORM insert/update/delete statements, learning snapshots,
course state and materialized report rebuilds invalidate pages after the outer
transaction commits. Rollback does not invalidate them. A generation token
avoids scanning/deleting all keys and prevents an in-flight older computation
from filling the new generation. Old entries expire naturally. If Redis is
unavailable, reads use the existing PostgreSQL path and writes remain usable.
Failed invalidation can leave a cached page stale until its short TTL expires.
Raw SQL and changes made outside the application also rely on that TTL.

The page cache does not rebuild PostgreSQL materialized summaries: their source
freshness is still shown by `cache.built_at`. It reduces repeated computations,
not the work needed for a first cache miss. The existing materialized-summary
branch still projects/filter rows in Python; complicated status filters can
therefore remain expensive on a cold read. The CMS SQL overview improvements
and default 15-item API page are retained.

## Settings and rollout

| Variable | Default | Purpose |
| --- | --- | --- |
| `TEACHER_REPORT_CACHE_TTL_SECONDS` | `45` | Set `0` to disable the teacher page cache |
| `REDIS_SOCKET_TIMEOUT_SECONDS` | `0.5` | Connect/command timeout for direct app Redis commands |
| `REDIS_MAX_CONNECTIONS` | `32` | Maximum connections per process/endpoint; no unbounded pools |
| `REDIS_CACHE_URL` | empty | Optional separate cache server; otherwise uses `REDIS_URL` |
| `REDIS_CACHE_PASSWORD`, `REDIS_CACHE_USER` | empty | Credentials specific to the cache server |

Bank cache and dashboard analytics also use the optional cache endpoint.
Celery, authentication, rate limiting and daily coordinator locks keep using
`REDIS_URL`. Celery owns its original broker/result pools and timeout settings.
Direct application commands share bounded pools per process and endpoint; no
automatic retry prolongs a cache outage. Closing a coordinator client does not
disconnect the shared pool.

Build only the CMS-AI backend image, then update backend, all workers and beat.
No frontend, CMS-FPT, MFE build or migration is required. In Kubernetes these
deployments read `ai-server-env`; configure cache variables consistently there
so worker invalidation and API reads reach the same cache server. Leaving the
new variables unset is compatible with the existing deployment.

If separating cache, use another Redis instance/service rather than only a
different database number on the same server. Cache eviction policy is a server
memory setting. Do not change the broker/security server to `allkeys-lru` or
`allkeys-lfu`: eviction could remove queued jobs, ticket/revocation keys or locks.
A dedicated cache may use an eviction policy, with its own measured RAM limit.
See [Redis key eviction](https://redis.io/docs/latest/develop/reference/eviction/).
This change does not create a Redis service or alter infrastructure policies.

## Read-only production diagnostics

This prints relevant metrics for the configured stores without credentials:

```bash
kubectl -n openedx exec -i deploy/ai-server-backend -- python - <<'PY'
import json
from app.core.config import settings
from app.core.redis_client import get_redis_client

for name, is_cache in [('broker-security', False), ('cache', True)]:
    client = get_redis_client(cache=is_cache)
    result = {'store': name, 'ping': client.ping(),
              'separate_cache_endpoint': bool(settings.redis_cache_url
                  and settings.redis_cache_url != settings.redis_url)}
    for section, keys in {
        'memory': ['used_memory_human', 'maxmemory', 'maxmemory_policy'],
        'clients': ['connected_clients', 'blocked_clients'],
        'stats': ['evicted_keys', 'rejected_connections', 'keyspace_hits',
                  'keyspace_misses', 'instantaneous_ops_per_sec',
                  'total_connections_received'],
    }.items():
        info = client.info(section)
        result[section] = {key: info.get(key) for key in keys}
    print(json.dumps(result, ensure_ascii=False))
PY
```

This diagnoses Redis memory/connection pressure. It does not establish API p95
latency or whether a particular Celery task has been reserved by a worker.
For automatic daily-root discovery/resume, see
[the recovery runbook](ACADEMIC_DAILY_CONTINUATION_RECOVERY.md).

## Verification

Tests cover page/filter isolation, changed access scopes, a mid-request permission
change, committed ORM/bulk updates, outer transaction versus savepoint commits,
rollback, missing-generation eviction, corrupt JSON and Redis failures. Actual
Redis integration verifies TTL expiration, pool reuse after client cleanup,
separate cache/security stores, ticket replay rejection and fail-closed auth.
No production latency or RAM figures have been measured in this workspace.

A local sample with SQLite and real Redis, 30 teachers / 900 students, measured
the report service alone: cold 74.93 ms and 17 SQL statements; warm 0.94 ms and
0 SQL statements. Scope totals were preserved (30 teachers / 900 students).
API authorization and live email-statistics work outside this service are not
included in those times. This is not a production latency measurement.
