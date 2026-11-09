# AP learning results API

AP backend reads existing durable learning-behavior snapshots through two versioned GET endpoints: class results (paginated, maximum 200) and one student result. Neither endpoint reads tracking events, calls CMS/AP, publishes jobs, or changes data.

Authentication uses a dedicated client ID and high-entropy API key; only SHA-256 digests are configured. Each client has explicit branch/campus pairs. Missing/malformed configuration fails closed. No Dash session, outbound AP credential, or demo header substitutes for this identity. Responses prohibit caching.

A class is resolved by exact AP class ID, AP term ID, branch, campus and subject code; optional AP block ID disambiguates blocks. Inactive/missing classes return 404 and ambiguous classes return 409. Student codes remain case-sensitive and must belong to the active roster. Existing effective course mapping is authoritative; absent mapping returns 409.

Results whitelist current roster identity, classification, confidence, reasons, explanation/action, quality, calculated/activity timestamps and freshness. Raw answers, evidence, peers, email, secrets and internal diagnostics are excluded. Missing snapshots remain explicitly missing with null scores. Stale snapshots retain their historical classification and show stale status. Summary includes current roster only, across all pages. No grades are inferred from logs. Results are soft signals requiring human verification.

Deployment requires building the backend, configuring integration secrets, and verifying AP identity mapping and PostgreSQL query behavior. No migration or Redis changes are required. AP backend is responsible for authorizing its own viewers; keys never go to the browser.
