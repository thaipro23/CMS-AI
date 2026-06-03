# v25.4 - Tiktoken Offline Hotfix

## Problem

Worker jobs could fail before calling OpenAI when `tiktoken` tried to download
`cl100k_base.tiktoken` from:

```txt
openaipublic.blob.core.windows.net
```

In offline Docker/restricted DNS environments this raised `NameResolutionError`.
The job showed `Actual Cost = 0` because the failure happened before the model
request.

## Fix

`backend/app/services/token_counter.py` now treats local token counting as a
best-effort fallback only:

1. Try `tiktoken.encoding_for_model(model)`.
2. Try `tiktoken.get_encoding('cl100k_base')`.
3. If tiktoken cannot load the encoding, use a conservative offline heuristic.

Token counting can no longer fail a generation job.

Production estimate still uses:

```txt
POST /v1/responses/input_tokens
```

when `MOCK_LLM=false`, `OPENAI_API_MODE=responses`, and an API key is configured.

## Optional environment/network fix

If you want exact local tiktoken counts too, allow Docker DNS/network access to:

```txt
openaipublic.blob.core.windows.net
```

or run once with internet so tiktoken can cache the encoding under:

```txt
/app/.runtime/tiktoken-cache
```

Because backend and worker share `/app/.runtime`, both containers can reuse the
cache afterward.
