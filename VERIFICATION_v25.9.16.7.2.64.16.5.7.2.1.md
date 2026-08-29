# Verification — v25.9.16.7.2.64.16.5.7.2.1

## Registry fix

- Frontend internal URLs replaced: **365**.
- E2E internal URLs replaced: **4**.
- Remaining OpenAI internal/private npm URL: **0**.
- Lockfile registry gate: **READY**.
- `.npmrc` public registry contract: **PASS**.
- Docker public registry enforcement: **PASS**.
- CI fail-fast registry prerequisite: **PASS** by source contract.

## Tests and gates

- Backend compileall: PASS.
- Public registry release tests: **6 passed**.
- Claude review pack: **PASS — 33/33**, 0 warning, 0 failure.
- Shell syntax for registry/review/UAT scripts: PASS.

## Frontend public-registry verification

A clean frontend install was executed with the environment registry override removed and explicit npm public registry:

```text
registry: https://registry.npmjs.org/
packages installed: 333
install time: approximately 9 seconds
ESLint: PASS
TypeScript: PASS
Next.js compile: PASS
Static generation: 30/30 PASS
```

The sandbox did not finish Next.js trace collection within the execution limit, so a newly generated `.next/standalone/server.js` is not asserted for this hotfix. The direct predecessor `.64.16.5.7.2` had a successful standalone build, and frontend application source is unchanged except version and npm registry configuration.

## E2E

- E2E lockfile source contract: PASS, all four resolved URLs use npm public.
- E2E/browser install execution did not complete within the sandbox tool limit.
- CI/browser execution is owned separately and is not part of the immediate frontend roadmap.

## Database

- No migration added.
- Alembic head remains `0053_v25_9_16_7_2_64_16_5_4_diff_idempotency.py`.
