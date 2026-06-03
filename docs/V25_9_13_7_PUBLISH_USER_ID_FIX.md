# v25.9.13.7 - Publish User ID Fix

## Fix

Open edX Ulmo can accept `publish_component_changes(usage_key, user)` at the wrapper level, but the lower `openedx-learning` publish log expects `published_by` to be an integer user id. Passing a Django User object or username can fail with:

```txt
ValidationError({'published_by': ['“admin” value must be an integer.']})
```

This release changes the CMS connector to call publish APIs with integer `user_id` first, then fallback to other signatures for release compatibility.

## Changed file

- `openedx-connector-plugin/openedx_ai_connector/views.py`

## Deploy

If the connector plugin is mounted into CMS, copy the new `views.py` and restart CMS only:

```bash
tutor local restart cms cms-worker
```

No AI Server rebuild is required when only this plugin file changes.

If the connector plugin is baked into the openedx image, rebuild the openedx image:

```bash
tutor images build openedx
tutor local restart cms cms-worker
```

## Verify

```bash
curl http://studio.local.openedx.io/api/ai-connector/v1/health
```

Expected:

```json
{"version":"25.9.13.7"}
```
