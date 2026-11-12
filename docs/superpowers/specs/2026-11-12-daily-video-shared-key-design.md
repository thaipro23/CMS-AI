# Shared AP key and isolated daily/video corrections

User requests one common AP key, dependent-target-only daily failures, and accurate
video review signals with readable Vietnamese reason labels. Keep existing stack
and stable API paths; no schema migration or production mutation.

Use one shared config containing digest and explicit scope pairs; accept one-client
legacy config during migration, reject multi-key ambiguity. Do not reuse outbound
AP credentials implicitly. Preserve existing internal user RBAC.

Use durable per-subject/class bulk results to isolate mapping failure rather than
ignore errors or abort unrelated scopes. Freeze original scope, retain successes
across retries, fail closed on malformed partitions, suppress reports whose required
dependencies failed, and finalize with truthful failure details after independent
work. Existing terminal daily jobs stay terminal under supported recovery guards.

Repeated corroborated high-completion/low-watch videos across multiple sessions get
teacher review independently of whole-course averages. Missing timing is a data
limit. Version-mark historical snapshots as stale without GET mutation. Share reason
labels across both Dash views; neutral deadline/order signals stay neutral. Tests
must cover the supplied35-score reproduction and uncertainty/identity boundaries.
