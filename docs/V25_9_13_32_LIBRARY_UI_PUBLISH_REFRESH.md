# v25.9.13.32 - Library UI Publish Refresh

Fixes Open edX Library UI still showing imported AI problems as `Never published` / `Unpublished changes` after v25.9.13.31.

Root cause: v25.9.13.31 published Learning Core drafts but skipped `content_libraries` post-publish events/index refresh. The Authoring MFE can keep showing stale publish status until those events are emitted.

Change:
- Publish all pending drafts in the AI-managed Library.
- Run `send_events_after_publish` synchronously inside CMS instead of Celery `result.get()`, avoiding the Ulmo `PublishLog.DoesNotExist` worker race.
- Return `library_ui_verification` showing `published`, `modified_since_publish`, and `never_published` counts after publish.

Main file: `openedx-connector-plugin/openedx_ai_connector/views.py`.
