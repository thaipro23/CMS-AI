# Immutable default for Quiz constraint context

Use `None` as the ContextVar default rather than a shallow dictionary copy.
The previous default and worker fallback shared nested question-type weights
with the module's default configuration. Mutating a raw default could therefore
poison another context's normalized defaults.

The existing public read paths already call `normalize_quiz_constraint_config`,
which accepts None and returns a fresh dictionary including new nested weights.
No lazy getter cache is needed. Explicit request binding still normalizes its
payload, and middleware still restores the token in finally. The non-quiz or
missing-job worker fallback now binds None as well.

This corrects a latent mutable-default risk; it is not evidence that production
requests previously changed each other's quiz settings through public getters.
Default ratios, planner behavior and explicit request/job settings are unchanged.

Verification: two new reproductions failed against the previous implementation;
10 focused tests pass after the fix. Coverage includes separate unbound contexts,
worker fallback, nested bindings restored after errors, concurrent tasks, caller
payload mutations and returned snapshot mutations. F401/F821/E9 and whitespace
checks pass. No migration, frontend or CMS-FPT rebuild is required; deploy the
CMS-AI backend and workers. Production deployment was not performed.

Full backend suite: 1193 passed, 15 skipped, 311 failed. Failed test names
exactly match the documented baseline in QUIZ_COLUMNS_TEST_BASELINE_2026-10-13.txt
minus the two obsolete null-teacher-branch cases corrected by the earlier
teacher-scope fix. No new failures; the full suite is not green. Independent
review found no production-change blockers and confirmed all None reads safely
normalize into fresh dictionaries.

Commit message: `fix: Avoid shared mutable quiz constraint defaults`.
